// SPDX-License-Identifier: MPL-2.0
//! A small error type, so the engine needs no error library.

/// What can go wrong.
pub type Error = Box<dyn std::error::Error + Send + Sync>;

/// What can go wrong, with a result.
pub type Result<T> = std::result::Result<T, Error>;

/// Adds a note to an error, so the caller knows what was being done.
pub trait Note<T> {
    fn note(self, note: &str) -> Result<T>;
}

impl<T, E: std::fmt::Display> Note<T> for std::result::Result<T, E> {
    fn note(self, note: &str) -> Result<T> {
        self.map_err(|e| -> Error { format!("{note}: {e}").into() })
    }
}

/// Fails with a message.
pub fn fail<T>(message: impl Into<String>) -> Result<T> {
    Err(message.into().into())
}
