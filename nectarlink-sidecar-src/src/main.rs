// SPDX-License-Identifier: MPL-2.0
//! A headless NectarLink mirroring engine, for embedding in another app.
//!
//! It does what the desktop app's mirroring window does, without a window:
//! it asks a paired phone for its screen, decodes the video with Windows'
//! own decoders, and hands the pictures to whoever is listening on a local
//! socket. Touches and keys travel back the other way, so the phone can be
//! played with from the embedding app.
//!
//! Status lines go out as JSON on stdout, one per line, so an embedding app
//! can follow what the engine is doing:
//!
//! ```text
//! {"type":"ready","port":51234}
//! {"type":"config","codec":"h264","width":1080,"height":2340}
//! ```

mod decode;
mod err;
mod link;

use std::path::PathBuf;
use std::sync::Arc;

use err::{Note, Result, fail};
use nectarlink_core::{
    MIRROR_VIEW, DeviceId, DeviceInfo, DeviceKind, MirrorConfig, MirrorInput, MirrorSink, MirrorStart, Node,
    NodeConfig, NodeEvent, PairingEvent, Platform, PowerLevel, TouchAction,
};
use serde_json::json;
use tokio::net::TcpListener;
use tokio::sync::{broadcast, mpsc, watch};
use tracing_subscriber::EnvFilter;

/// The engine's settings.
#[derive(Debug)]
struct Cli {
    /// Where the device key and the paired-device list live.
    data_dir: Option<PathBuf>,
    /// Which paired phone to mirror: an id prefix, or a name.
    device: String,
    /// The local port the pictures come out on (0: any free port).
    port: u16,
    /// The longest side asked of the phone, in pixels.
    max_size: u32,
    /// Frames per second asked of the phone.
    fps: u32,
    /// The video bitrate asked of the phone, in bits per second.
    bitrate: u32,
    /// Pair with a phone first, then mirror it.
    pair: bool,
    /// Don't announce this device on the local network.
    no_lan: bool,
    /// The name this device shows on the phone.
    name: String,
    /// The version this engine reports to the phone.
    app_version: String,
}

impl Default for Cli {
    fn default() -> Self {
        Cli {
            data_dir: None,
            device: String::new(),
            port: 0,
            max_size: 1920,
            fps: 30,
            bitrate: 8_000_000,
            pair: false,
            no_lan: false,
            name: "ok-ww".to_string(),
            app_version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }
}

/// One piece of the phone's stream, on its way to the decoder.
enum Packet {
    /// The stream's format, once the phone has said it.
    Config(MirrorConfig),
    /// One access unit (Annex B).
    Data { time_us: u64, data: Vec<u8> },
    /// The stream ended.
    Ended,
}

/// Where the engine's pictures go: the embedder, over the local socket.
struct FrameSink {
    packets: mpsc::UnboundedSender<Packet>,
}

impl std::fmt::Debug for FrameSink {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("FrameSink")
    }
}

impl MirrorSink for FrameSink {
    fn config(&self, config: MirrorConfig) {
        emit(json!({
            "type": "config",
            "codec": config.codec,
            "width": config.width,
            "height": config.height,
        }));
        let _ = self.packets.send(Packet::Config(config));
    }

    fn packet(&self, _keyframe: bool, time_us: u64, data: Vec<u8>) {
        let _ = self.packets.send(Packet::Data { time_us, data });
    }

    fn ended(&self) {
        emit(json!({"type": "ended"}));
        let _ = self.packets.send(Packet::Ended);
    }
}

/// The services the engine needs from its host: only the video sink.
#[derive(Debug)]
struct SidecarPlatform {
    sink: Arc<FrameSink>,
}

impl Platform for SidecarPlatform {
    fn mirror_sink(&self, _peer: &DeviceId, _session: u32) -> Option<Arc<dyn MirrorSink>> {
        Some(self.sink.clone() as Arc<dyn MirrorSink>)
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = parse_args()?;
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .init();

    let data_dir = cli.data_dir.clone().unwrap_or_else(default_data_dir);
    std::fs::create_dir_all(&data_dir).note("can't make the data directory")?;
    let link_file = data_dir.join("link.json");

    let (packets, incoming) = mpsc::unbounded_channel();
    let platform = Arc::new(SidecarPlatform { sink: Arc::new(FrameSink { packets }) });

    let device = DeviceInfo {
        name: cli.name.clone(),
        kind: DeviceKind::Desktop,
        os: "windows".into(),
        os_ver: String::new(),
        model: None,
        accent: None,
        screen: None,
        install_id: None,
    };
    let mut config = NodeConfig::new(data_dir.clone(), device, cli.app_version.clone());
    config.lan_discovery = !cli.no_lan;
    // Only what this engine does: show a phone's screen. No HEVC (this
    // build decodes H.264 only), so the phone sends H.264.
    config.capabilities = vec![MIRROR_VIEW.to_string()];

    let node = Node::start(config, platform).await.note("can't start the engine")?;
    node.update_power(PowerLevel::NotApplicable, vec![MIRROR_VIEW.to_string()]).await;

    if cli.pair {
        pair(&node).await?;
    }

    let target = select_device(&node, &cli.device)?;
    emit(json!({"type": "device", "id": target.to_string()}));

    let mut events = node.events();
    let options = MirrorStart {
        max_size: cli.max_size,
        fps: cli.fps,
        bitrate: cli.bitrate,
        audio: false,
        session: 0,
        app: None,
        stay_awake: true,
        screen_off: false,
        watch: None,
        sound_only: false,
        display: None,
    };
    node.mirror_start(target, options).await.note("the phone did not agree to share its screen")?;

    // The phone asks its user; wait for the stream to start.
    loop {
        match events.recv().await {
            Ok(NodeEvent::Mirroring { on: true, session: 0, .. }) => break,
            Ok(NodeEvent::Mirroring { on: false, .. }) => return fail("the phone stopped sharing its screen"),
            Ok(NodeEvent::MirrorNotice { code, .. }) => emit(json!({"type": "notice", "code": code})),
            Ok(_) => {}
            Err(_) => return fail("the engine stopped"),
        }
    }

    // The pictures go out on a loopback socket.
    let (frames_tx, frames_rx) = watch::channel::<Option<Arc<decode::Picture>>>(None);
    // Status lines go out the same way, so an embedder that only has the
    // socket still learns the stream's format and when it ends.
    let (status_tx, _) = broadcast::channel::<String>(16);
    let listener = TcpListener::bind(("127.0.0.1", cli.port)).await.note("can't open the local port")?;
    let port = listener.local_addr().note("can't read the local address")?.port();
    // Where the pictures come out, so an app that starts later can find this
    // engine again instead of starting a second one.
    let link = json!({"port": port, "pid": std::process::id()});
    let _ = std::fs::write(&link_file, link.to_string());
    emit(json!({"type": "ready", "port": port}));

    let decoder = tokio::task::spawn_blocking({
        let status = status_tx.clone();
        move || decode_loop(incoming, frames_tx, status)
    });
    let serving = tokio::spawn(serve(listener, frames_rx, status_tx, node.clone(), target));

    tokio::select! {
        _ = decoder => {}
        _ = serving => {}
    }
    Ok(())
}

/// Decodes the phone's stream, and hands the pictures on.
fn decode_loop(
    mut incoming: mpsc::UnboundedReceiver<Packet>,
    frames: watch::Sender<Option<Arc<decode::Picture>>>,
    status: broadcast::Sender<String>,
) {
    let mut decoder: Option<decode::Decoder> = None;
    let mut codec = String::from("h264");
    // The resolution last reported to the embedder.
    let mut reported = (0u32, 0u32);
    while let Some(packet) = incoming.blocking_recv() {
        match packet {
            Packet::Config(config) => {
                codec = config.codec.clone();
                decoder = None;
                // The embedder wants to know the stream's shape, and that the
                // codec changed (so it can drop the old pictures).
                let line = json!({
                    "type": "config",
                    "codec": config.codec,
                    "width": config.width,
                    "height": config.height,
                });
                let _ = status.send(line.to_string());
            }
            Packet::Data { time_us, data } => {
                if decoder.is_none() {
                    match decode::Decoder::new(&codec) {
                        Ok(decoded) => decoder = Some(decoded),
                        Err(e) => {
                            let message = format!("can't decode {codec}: {e}");
                            emit(json!({"type": "error", "message": message.clone()}));
                            let _ = status.send(json!({"type": "error", "message": message}).to_string());
                            continue;
                        }
                    }
                }
                let Some(decoded) = decoder.as_mut() else { continue };
                match decoded.decode(&data, time_us) {
                    Ok(pictures) => {
                        // Tell the embedder the resolution the decoder settled
                        // on: it can differ from what the phone asked for.
                        if !pictures.is_empty() {
                            let (width, height) = decoded.size();
                            if (width, height) != reported {
                                reported = (width, height);
                                let _ = status.send(
                                    json!({"type": "size", "width": width, "height": height}).to_string(),
                                );
                            }
                        }
                        for picture in pictures {
                            let _ = frames.send(Some(Arc::new(picture)));
                        }
                    }
                    Err(e) => {
                        let message = format!("decode failed: {e}");
                        emit(json!({"type": "error", "message": message.clone()}));
                        let _ = status.send(json!({"type": "error", "message": message}).to_string());
                        // The next keyframe starts the stream over cleanly.
                        decoded.flush();
                    }
                }
            }
            Packet::Ended => {
                emit(json!({"type": "ended"}));
                let _ = status.send(json!({"type": "ended"}).to_string());
                decoder = None;
            }
        }
    }
}

/// Hands the pictures to whoever connects, and passes touches and keys on.
async fn serve(
    listener: TcpListener,
    frames: watch::Receiver<Option<Arc<decode::Picture>>>,
    status: broadcast::Sender<String>,
    node: Node,
    device: DeviceId,
) {
    loop {
        let Ok((stream, _)) = listener.accept().await else { continue };
        let frames = frames.clone();
        let status = status.clone();
        let node = node.clone();
        tokio::spawn(async move {
            let (mut reader, mut writer) = tokio::io::split(stream);
            // One writer, many senders: the pictures and the status lines
            // share the socket, so they go through one channel.
            let (outgoing, mut outbox) = mpsc::unbounded_channel::<(u8, Vec<u8>)>();
            let pictures = tokio::spawn({
                let outgoing = outgoing.clone();
                async move {
                    let mut frames = frames;
                    loop {
                        if frames.changed().await.is_err() {
                            break;
                        }
                        let picture = frames.borrow_and_update().clone();
                        let Some(picture) = picture else { continue };
                        let payload = link::encode_frame(&picture);
                        if outgoing.send((link::KIND_FRAME, payload)).is_err() {
                            break;
                        }
                    }
                }
            });
            // The status lines ride the same socket, so an embedder that only
            // has the socket still learns the stream's format and its end.
            let statuses = tokio::spawn(async move {
                let mut status = status.subscribe();
                loop {
                    let Ok(line) = status.recv().await else { break };
                    if outgoing.send((link::KIND_STATUS, line.into_bytes())).is_err() {
                        break;
                    }
                }
            });
            let writing = tokio::spawn(async move {
                while let Some((kind, payload)) = outbox.recv().await {
                    if link::write_message(&mut writer, kind, &payload).await.is_err() {
                        break;
                    }
                }
            });
            loop {
                let Ok((kind, payload)) = link::read_message(&mut reader).await else { break };
                match kind {
                    link::KIND_TOUCH => {
                        let Some((action, x, y)) = link::decode_touch(&payload) else { continue };
                        let action = match action {
                            link::TOUCH_DOWN => TouchAction::Down,
                            link::TOUCH_MOVE => TouchAction::Move,
                            link::TOUCH_UP => TouchAction::Up,
                            _ => continue,
                        };
                        let _ = node.mirror_input(device, 0, MirrorInput::Touch { action, x, y }).await;
                    }
                    link::KIND_KEY => {
                        let Some(key) = link::decode_key(&payload) else { continue };
                        let key = match key {
                            link::KEY_BACK => "back",
                            link::KEY_HOME => "home",
                            link::KEY_RECENTS => "recents",
                            link::KEY_ENTER => "enter",
                            link::KEY_BACKSPACE => "backspace",
                            _ => continue,
                        };
                        let _ = node.mirror_input(device, 0, MirrorInput::Key { key: key.to_string() }).await;
                    }
                    _ => {}
                }
            }
            pictures.abort();
            statuses.abort();
            writing.abort();
        });
    }
}

/// Pairs with a phone, showing the link to scan.
async fn pair(node: &Node) -> Result<()> {
    let mut events = node.events();
    let link = node.pairing_start_qr().await.note("can't start pairing")?;
    let uri = link.to_uri();
    emit(json!({"type": "pairing", "uri": uri}));
    loop {
        match events.recv().await {
            Ok(NodeEvent::Pairing(PairingEvent::Paired(device))) => {
                emit(json!({"type": "paired", "id": device.id.to_string(), "name": device.info.name}));
                return Ok(());
            }
            Ok(NodeEvent::Pairing(PairingEvent::SasCode { code, .. })) => {
                emit(json!({"type": "sas", "code": code}));
                if confirm_from_stdin(&code).await? {
                    node.pairing_confirm(true)?;
                } else {
                    node.pairing_confirm(false)?;
                    return fail("the pairing was refused");
                }
            }
            Ok(NodeEvent::Pairing(PairingEvent::Failed(why))) => return fail(format!("pairing failed: {why:?}")),
            Ok(_) => {}
            Err(_) => return fail("the engine stopped"),
        }
    }
}

/// Asks the user to compare the code the phone shows.
async fn confirm_from_stdin(code: &str) -> Result<bool> {
    let code = code.to_string();
    tokio::task::spawn_blocking(move || -> Result<bool> {
        use std::io::Write;
        print!("Does the other device show {} {}? [y/N] ", &code[..3], &code[3..]);
        std::io::stdout().flush()?;
        let mut answer = String::new();
        std::io::stdin().read_line(&mut answer)?;
        Ok(matches!(answer.trim().to_ascii_lowercase().as_str(), "y" | "yes"))
    })
    .await?
}

/// The phone to mirror: the one the query names, or the only one there is.
fn select_device(node: &Node, query: &str) -> Result<DeviceId> {
    let paired = node.paired_devices().note("can't read the paired devices")?;
    let query = query.trim().to_lowercase();
    let matches: Vec<_> = paired
        .iter()
        .filter(|d| {
            query.is_empty()
                || d.id.to_string().to_lowercase().starts_with(&query)
                || d.info.name.to_lowercase() == query
        })
        .collect();
    match matches.as_slice() {
        [one] => Ok(one.id),
        [] => fail(format!("no paired phone matches {query:?}: pair one first")),
        many => {
            let names: Vec<String> = many.iter().map(|d| format!("{} ({})", d.info.name, d.id)).collect();
            fail(format!("{query:?} matches more than one phone: {}", names.join(", ")))
        }
    }
}

/// Where the engine keeps its identity when nothing says otherwise.
fn default_data_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("LOCALAPPDATA") {
        return PathBuf::from(dir).join("ok-ww").join("nectarlink");
    }
    PathBuf::from("nectarlink-sidecar")
}

/// Prints a status line, so an embedding app can follow along.
fn emit(value: serde_json::Value) {
    use std::io::Write;
    let mut out = std::io::stdout().lock();
    let _ = writeln!(out, "{value}");
    let _ = out.flush();
}

/// Reads the settings from the command line.
fn parse_args() -> Result<Cli> {
    let mut cli = Cli::default();
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        let mut value = || args.next().unwrap_or_default();
        match arg.as_str() {
            "--data-dir" => cli.data_dir = Some(PathBuf::from(value())),
            "--device" => cli.device = value(),
            "--port" => cli.port = value().parse().unwrap_or(0),
            "--max-size" => cli.max_size = value().parse().unwrap_or(cli.max_size),
            "--fps" => cli.fps = value().parse().unwrap_or(cli.fps),
            "--bitrate" => cli.bitrate = value().parse().unwrap_or(cli.bitrate),
            "--pair" => cli.pair = true,
            "--no-lan" => cli.no_lan = true,
            "--name" => cli.name = value(),
            "--app-version" => cli.app_version = value(),
            "--help" | "-h" => {
                print_help();
                std::process::exit(0);
            }
            "--version" | "-V" => {
                println!("nectarlink-sidecar {}", env!("CARGO_PKG_VERSION"));
                std::process::exit(0);
            }
            other => return fail(format!("unknown option {other:?}; try --help")),
        }
    }
    Ok(cli)
}

/// What the engine can be told to do.
fn print_help() {
    println!(
        "nectarlink-sidecar {version} - headless NectarLink mirroring engine\n\
         \n\
         Usage: nectarlink-sidecar [options]\n\
         \n\
           --data-dir <dir>    where the device key and the paired phones live\n\
           --device <query>    which paired phone: an id prefix or a name\n\
           --port <port>       the local port the pictures come out on (0: any)\n\
           --max-size <pixels> the longest side asked of the phone (default 1920)\n\
           --fps <n>           frames per second asked of the phone (default 30)\n\
           --bitrate <bps>     the video bitrate asked of the phone (default 8000000)\n\
           --pair              pair with a phone first, then mirror it\n\
           --no-lan            don't announce this device on the local network\n\
           --name <name>       the name this device shows on the phone (default ok-ww)\n\
           --app-version <v>   the version this engine reports (default {version})",
        version = env!("CARGO_PKG_VERSION")
    );
}
