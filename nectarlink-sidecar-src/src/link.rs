// SPDX-License-Identifier: MPL-2.0
//! The local link between the engine and whoever embeds it.
//!
//! One TCP connection on the loopback interface carries both ways: the
//! engine pushes decoded pictures and status lines down it, and the
//! embedder sends touches and keys up it. Every message is a kind byte, a
//! length and a payload; nothing else travels, so the two sides can be
//! written in any language.

use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};

use crate::decode::Picture;

/// A status line, as JSON text.
pub const KIND_STATUS: u8 = 1;
/// A picture, in NV12.
pub const KIND_FRAME: u8 = 2;
/// A finger, from the embedder to the phone.
pub const KIND_TOUCH: u8 = 3;
/// A key, from the embedder to the phone.
pub const KIND_KEY: u8 = 4;

/// The biggest message accepted: a 8K picture in NV12 is under 50 MB.
const MAX_MESSAGE: usize = 64 * 1024 * 1024;

/// A finger going down, moving or lifting.
pub const TOUCH_DOWN: u8 = 0;
pub const TOUCH_MOVE: u8 = 1;
pub const TOUCH_UP: u8 = 2;

/// The keys the embedder can ask for. The numbers are the ones the phone
/// understands (see `mirror_keys` in the protocol).
pub const KEY_BACK: u8 = 0;
pub const KEY_HOME: u8 = 1;
pub const KEY_RECENTS: u8 = 2;
pub const KEY_ENTER: u8 = 3;
pub const KEY_BACKSPACE: u8 = 4;

/// Writes one message: a kind, a length and the payload.
pub async fn write_message<W: AsyncWrite + Unpin>(w: &mut W, kind: u8, payload: &[u8]) -> std::io::Result<()> {
    let mut head = [0u8; 5];
    head[0] = kind;
    head[1..5].copy_from_slice(&(payload.len() as u32).to_le_bytes());
    w.write_all(&head).await?;
    w.write_all(payload).await?;
    w.flush().await
}

/// Reads one message. Returns the kind and the payload.
pub async fn read_message<R: AsyncRead + Unpin>(r: &mut R) -> std::io::Result<(u8, Vec<u8>)> {
    let mut head = [0u8; 5];
    r.read_exact(&mut head).await?;
    let len = u32::from_le_bytes([head[1], head[2], head[3], head[4]]) as usize;
    if len > MAX_MESSAGE {
        return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "message too big"));
    }
    let mut payload = vec![0u8; len];
    r.read_exact(&mut payload).await?;
    Ok((head[0], payload))
}

/// A picture, as it goes on the wire: its size, then the NV12 pixels.
pub fn encode_frame(picture: &Picture) -> Vec<u8> {
    let mut out = Vec::with_capacity(12 + picture.pixels.len());
    out.extend_from_slice(&picture.width.to_le_bytes());
    out.extend_from_slice(&picture.height.to_le_bytes());
    out.extend_from_slice(&(picture.pixels.len() as u32).to_le_bytes());
    out.extend_from_slice(&picture.pixels);
    out
}

/// A finger: the action, and where it is (a share of the screen, 0..1).
pub fn decode_touch(payload: &[u8]) -> Option<(u8, f32, f32)> {
    if payload.len() < 9 {
        return None;
    }
    let action = payload[0];
    let x = f32::from_le_bytes(payload[1..5].try_into().ok()?);
    let y = f32::from_le_bytes(payload[5..9].try_into().ok()?);
    Some((action, x, y))
}

/// A key: its number.
pub fn decode_key(payload: &[u8]) -> Option<u8> {
    payload.first().copied()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn a_message_comes_back_as_it_went() {
        let mut buffer = Vec::new();
        write_message(&mut buffer, KIND_TOUCH, &[1, 2, 3]).await.unwrap();
        let mut cursor = std::io::Cursor::new(buffer);
        let (kind, payload) = read_message(&mut cursor).await.unwrap();
        assert_eq!(kind, KIND_TOUCH);
        assert_eq!(payload, vec![1, 2, 3]);
    }

    #[test]
    fn a_finger_is_read_as_an_action_and_a_place() {
        let mut payload = vec![TOUCH_DOWN];
        payload.extend_from_slice(&0.25f32.to_le_bytes());
        payload.extend_from_slice(&0.75f32.to_le_bytes());
        let (action, x, y) = decode_touch(&payload).unwrap();
        assert_eq!(action, TOUCH_DOWN);
        assert!((x - 0.25).abs() < 1e-6);
        assert!((y - 0.75).abs() < 1e-6);
        assert!(decode_touch(&[1, 2]).is_none());
    }

    /// The status lines travel over the same socket as the pictures, so an
    /// embedder that only has the socket still learns the stream's shape.
    #[tokio::test]
    async fn a_status_line_travels_as_text() {
        let mut buffer = Vec::new();
        write_message(&mut buffer, KIND_STATUS, br#"{"type":"size","width":1080}"#)
            .await
            .unwrap();
        let mut cursor = std::io::Cursor::new(buffer);
        let (kind, payload) = read_message(&mut cursor).await.unwrap();
        assert_eq!(kind, KIND_STATUS);
        let text = String::from_utf8(payload).unwrap();
        assert!(text.contains("\"width\":1080"));
    }
}
