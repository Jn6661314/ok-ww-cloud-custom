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
use std::time::Duration;

use err::{Note, Result, fail};
use nectarlink_core::{
    MIRROR_VIEW, DeviceId, DeviceInfo, DeviceKind, LinkState, MirrorConfig, MirrorInput, MirrorSink, MirrorStart, Node,
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
    /// How long to wait for the phone to come online (seconds).
    wait_seconds: u64,
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
            wait_seconds: 120,
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
async fn main() {
    if let Err(err) = run().await {
        // stdout carries the status lines, so the embedder reads the error
        // from there too — not only from stderr, which it may not capture.
        emit(json!({"type": "error", "message": err.to_string()}));
        eprintln!("Error: {err:?}");
        std::process::exit(1);
    }
}

async fn run() -> Result<()> {
    let cli = parse_args()?;
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        // The embedder reads this log as text: colour codes would just get in
        // the way of telling an ordinary line from a real error.
        .with_ansi(false)
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

    // 记下自己在跑: 同一个数据目录只能有一个内核。设备身份是存在这里的, 两个
    // 内核用同一个身份在局域网里互相广播时, 手机会拿到对不上的地址, 然后报
    // "设备离线" —— 所以后来的那个要能被发现并被清掉。
    let state = StateFile::create(&data_dir)?;

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

    // 节点刚起来时, 和手机之间的连接通常还没建好(后台在拨号重连)。这时候直接
    // 要求投屏, 内核会拿到 "device is offline" 然后自己退出 —— 所以先等手机上线。
    // 上游 CLI 也是先等设备在线再开口的。
    let wait = Duration::from_secs(cli.wait_seconds);
    wait_until_online(&node, target, wait).await?;

    // 要求手机开始投屏(手机上会弹一个"允许")。等待期间连接可能又断了一次,
    // 那就再等等重试 —— 手机刚同意时连接经常要重建一次。
    let mut attempt = 0;
    loop {
        attempt += 1;
        match node.mirror_start(target, options.clone()).await {
            Ok(()) => break,
            Err(err) => {
                let retryable = matches!(
                    err,
                    nectarlink_core::Error::Offline
                        | nectarlink_core::Error::Network(_)
                        | nectarlink_core::Error::Timeout
                );
                if !retryable || attempt >= 5 {
                    return Err::<(), _>(err).note("the phone did not agree to share its screen");
                }
                emit(json!({
                    "type": "retry",
                    "attempt": attempt,
                    "message": err.to_string(),
                }));
                wait_until_online(&node, target, wait).await?;
            }
        }
    }

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
    state.set_port(port);
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

/// Waits until the phone is reachable, so the mirror request doesn't bounce.
///
/// A node that just started is still dialing the phone in the background: the
/// session isn't up yet, and asking for the screen then fails with "device is
/// offline". The upstream CLI waits for the device to come online first, and so
/// does this.
async fn wait_until_online(node: &Node, id: DeviceId, timeout: Duration) -> Result<()> {
    let deadline = tokio::time::Instant::now() + timeout;
    let mut announced = false;
    let mut last_note = std::time::Instant::now();
    loop {
        // The store's own view of the link: Online means the phone and this
        // node have a session, which is what the mirror request needs.
        let online = node
            .paired_devices()
            .map(|devices| {
                devices
                    .iter()
                    .any(|d| d.id == id && matches!(d.link, LinkState::Online { .. }))
            })
            .unwrap_or(false);
        if online {
            emit(json!({"type": "online", "id": id.to_string()}));
            return Ok(());
        }
        if tokio::time::Instant::now() >= deadline {
            return fail(format!(
                "the phone didn't come online within {} seconds (is the NectarLink app running on it?)",
                timeout.as_secs()
            ));
        }
        // Say we're waiting, then keep saying so now and then: the embedder
        // shows this to the user, and silence looks like a hang.
        if !announced || last_note.elapsed() >= Duration::from_secs(10) {
            announced = true;
            last_note = std::time::Instant::now();
            emit(json!({
                "type": "waiting",
                "message": "等手机上线(手机上的 NectarLink 要在运行)…",
            }));
        }
        tokio::time::sleep(Duration::from_millis(300)).await;
    }
}

/// Remembers that this engine is running, so the next start can find it.
///
/// Only one engine may use a data directory: the device identity lives there,
/// and two engines answering with the same identity on the local network leave
/// the phone with addresses that don't match — it then reports the device as
/// offline.
struct StateFile {
    path: PathBuf,
}

impl StateFile {
    /// Writes the state file for this process.
    fn create(data_dir: &std::path::Path) -> Result<Self> {
        let path = data_dir.join("sidecar.json");
        let state = StateFile { path };
        state.write(json!({
            "pid": std::process::id(),
            "port": 0,
            "started": std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs())
                .unwrap_or(0),
        }));
        Ok(state)
    }

    /// Writes the state file, keeping whatever was already in it.
    fn write(&self, mut value: serde_json::Value) {
        let mut state = self.read().unwrap_or_else(|| serde_json::json!({}));
        if let (Some(state), Some(value)) = (state.as_object_mut(), value.as_object_mut()) {
            for (key, item) in value {
                state.insert(key.clone(), item.clone());
            }
        } else {
            return;
        }
        let _ = std::fs::write(&self.path, state.to_string());
    }

    /// Reads the state file.
    fn read(&self) -> Option<serde_json::Value> {
        let text = std::fs::read_to_string(&self.path).ok()?;
        serde_json::from_str(&text).ok()
    }

    /// Records the port the pictures come out on.
    fn set_port(&self, port: u16) {
        self.write(json!({"port": port}));
    }
}

impl Drop for StateFile {
    fn drop(&mut self) {
        // Only remove the file while it still describes this process: another
        // engine may have taken over in the meantime.
        let mine = self
            .read()
            .and_then(|state| state.get("pid").and_then(|pid| pid.as_u64()))
            .map(|pid| pid == std::process::id() as u64)
            .unwrap_or(false);
        if mine {
            let _ = std::fs::remove_file(&self.path);
        }
    }
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
///
/// The prompt goes to stderr on purpose: stdout carries the status lines as
/// JSON, one per line, and a prompt without a newline would end up glued to
/// the front of the next JSON line — which the embedder would then fail to
/// parse, losing that message.
async fn confirm_from_stdin(code: &str) -> Result<bool> {
    let code = code.to_string();
    tokio::task::spawn_blocking(move || -> Result<bool> {
        use std::io::Write;
        let mut err = std::io::stderr().lock();
        // The code is six digits; split it in the middle so it reads easier.
        let (head, tail) = match code.char_indices().nth(3) {
            Some((at, _)) => (&code[..at], &code[at..]),
            None => (code.as_str(), ""),
        };
        let _ = write!(err, "Does the other device show {head} {tail}? [y/N] ");
        let _ = err.flush();
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
    parse_args_from(std::env::args().skip(1))
}

/// Reads the settings from a list of arguments.
fn parse_args_from<I: IntoIterator<Item = String>>(args: I) -> Result<Cli> {
    let mut cli = Cli::default();
    let mut args = args.into_iter();
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
            "--wait-seconds" => cli.wait_seconds = value().parse().unwrap_or(cli.wait_seconds),
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
           --app-version <v>   the version this engine reports (default {version})\n\
           --wait-seconds <n>  how long to wait for the phone to come online (default 120)",
        version = env!("CARGO_PKG_VERSION")
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The engine has to wait for the phone: asking for the screen before the
    /// phone is reachable fails with "device is offline" and the engine quits.
    #[test]
    fn the_wait_time_can_be_set() {
        let cli = parse_args_from(["--wait-seconds".to_string(), "30".to_string()]).unwrap();
        assert_eq!(cli.wait_seconds, 30);
    }

    #[test]
    fn the_wait_time_has_a_default() {
        let cli = parse_args_from(Vec::<String>::new()).unwrap();
        assert!(cli.wait_seconds > 0, "总得给手机一点时间上线");
    }

    /// The state file is how the next start finds (and clears) the engine this
    /// one left behind.
    #[test]
    fn the_state_file_says_which_engine_is_running() {
        let dir = std::env::temp_dir().join(format!("nl-state-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        {
            let state = StateFile::create(&dir).unwrap();
            state.set_port(4242);
            let read = state.read().unwrap();
            assert_eq!(read.get("pid").unwrap().as_u64().unwrap(), std::process::id() as u64);
            assert_eq!(read.get("port").unwrap().as_u64().unwrap(), 4242);
        }
        // The engine is gone: the state file goes with it, so the next start
        // doesn't look for a process that isn't there.
        assert!(!dir.join("sidecar.json").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn an_unknown_option_is_refused() {
        assert!(parse_args_from(["--nope".to_string()]).is_err());
    }
}
