// SPDX-License-Identifier: MPL-2.0
//! Turning a phone's video into pictures.
//!
//! The phone sends H.264 in Annex B form. Windows' own decoders (Media
//! Foundation's H.264 decoder, which comes with Windows) turn that into
//! NV12, which the embedder turns into colors. Nothing else is needed: no
//! FFmpeg, no GPU, no extra libraries.

/// A picture in NV12, tightly packed: the luma rows, then the chroma rows.
#[derive(Debug, Clone)]
pub struct Picture {
    pub width: u32,
    pub height: u32,
    pub pixels: Vec<u8>,
}

#[cfg(not(windows))]
mod imp {
    use crate::err::{Result, fail};

    use super::Picture;

    /// A decoder for the codecs this build knows.
    #[derive(Debug)]
    pub struct Decoder;

    impl Decoder {
        pub fn new(codec: &str) -> Result<Self> {
            fail(format!("this build has no video decoder for {codec} (Windows only)"))
        }

        pub fn decode(&mut self, _data: &[u8], _time_us: u64) -> Result<Vec<Picture>> {
            fail("this build has no video decoder")
        }

        pub fn flush(&mut self) {}
    }
}

#[cfg(windows)]
mod imp {
    use std::mem::ManuallyDrop;
    use std::ptr;

    use windows::Win32::Media::MediaFoundation::{
        CLSID_MSH264DecoderMFT, CODECAPI_AVDecNumWorkerThreads, IMF2DBuffer, IMFMediaType, IMFSample,
        IMFTransform, MF_E_NOTACCEPTING, MF_E_TRANSFORM_NEED_MORE_INPUT, MF_E_TRANSFORM_STREAM_CHANGE,
        MF_LOW_LATENCY, MF_MT_FRAME_SIZE, MF_MT_MAJOR_TYPE, MF_MT_SUBTYPE, MF_VERSION, MFCreateMediaType,
        MFCreateMemoryBuffer, MFCreateSample, MFMediaType_Video, MFVideoFormat_H264, MFVideoFormat_NV12,
        MFSTARTUP_NOSOCKET, MFStartup, MFT_MESSAGE_COMMAND_FLUSH, MFT_MESSAGE_NOTIFY_BEGIN_STREAMING,
        MFT_MESSAGE_NOTIFY_START_OF_STREAM, MFT_OUTPUT_DATA_BUFFER, MFT_OUTPUT_STREAM_PROVIDES_SAMPLES,
    };
    use windows::Win32::System::Com::{CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED, CoCreateInstance, CoInitializeEx};
    use windows::core::Interface;

    use crate::err::{Note, Result, fail};

    use super::Picture;

    /// Starts Media Foundation once for the process: its platform work
    /// queues must not be torn down while other decoders still use them.
    fn ensure_mf_started() -> Result<()> {
        static STARTED: std::sync::Mutex<bool> = std::sync::Mutex::new(false);
        // SAFETY: plain COM and Media Foundation startup calls.
        unsafe {
            let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
            let mut started = STARTED.lock().unwrap_or_else(|e| e.into_inner());
            if !*started {
                MFStartup(MF_VERSION, MFSTARTUP_NOSOCKET)?;
                *started = true;
            }
        }
        Ok(())
    }

    /// A decoder for one stream.
    #[derive(Debug)]
    pub struct Decoder {
        transform: IMFTransform,
        output_size: u32,
        provides_samples: bool,
        width: u32,
        height: u32,
    }

    impl Decoder {
        /// A decoder for `codec` ("h264" for now).
        pub fn new(codec: &str) -> Result<Self> {
            ensure_mf_started().note("can't start Media Foundation")?;
            if !codec.eq_ignore_ascii_case("h264") {
                return fail(format!("this build decodes H.264 only, not {codec}"));
            }
            // SAFETY: plain COM calls on values this function owns.
            unsafe {
                let transform: IMFTransform =
                    CoCreateInstance(&CLSID_MSH264DecoderMFT, None, CLSCTX_INPROC_SERVER)
                        .note("can't create the H.264 decoder")?;
                // Low latency: the decoder hands a picture over as soon as it
                // has it, instead of holding it back to reorder.
                if let Ok(attributes) = transform.GetAttributes() {
                    let _ = attributes.SetUINT32(&MF_LOW_LATENCY, 1);
                    let _ = attributes.SetUINT32(&CODECAPI_AVDecNumWorkerThreads, 1);
                }
                let input = MFCreateMediaType()?;
                input.SetGUID(&MF_MT_MAJOR_TYPE, &MFMediaType_Video)?;
                input.SetGUID(&MF_MT_SUBTYPE, &MFVideoFormat_H264)?;
                transform.SetInputType(0, &input, 0)?;
                let mut decoder = Decoder {
                    transform,
                    output_size: 0,
                    provides_samples: false,
                    width: 0,
                    height: 0,
                };
                decoder.choose_output()?;
                decoder.transform.ProcessMessage(MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0)?;
                decoder.transform.ProcessMessage(MFT_MESSAGE_NOTIFY_START_OF_STREAM, 0)?;
                Ok(decoder)
            }
        }

        /// The picture's size, once the stream has said.
        pub fn size(&self) -> (u32, u32) {
            (self.width, self.height)
        }

        /// Picks NV12 as the output, again after the stream's size changed.
        fn choose_output(&mut self) -> Result<()> {
            // SAFETY: as above.
            unsafe {
                let mut index = 0;
                let chosen: IMFMediaType = loop {
                    let candidate = self
                        .transform
                        .GetOutputAvailableType(0, index)
                        .note("can't list the decoder's output formats")?;
                    if candidate.GetGUID(&MF_MT_SUBTYPE)? == MFVideoFormat_NV12 {
                        break candidate;
                    }
                    index += 1;
                };
                self.transform.SetOutputType(0, &chosen, 0)?;
                let size = chosen.GetUINT64(&MF_MT_FRAME_SIZE).unwrap_or(0);
                self.width = (size >> 32) as u32;
                self.height = size as u32;
                let info = self.transform.GetOutputStreamInfo(0)?;
                self.provides_samples = info.dwFlags & MFT_OUTPUT_STREAM_PROVIDES_SAMPLES.0 as u32 != 0;
                self.output_size = info.cbSize;
                Ok(())
            }
        }

        /// Decodes one access unit (Annex B); returns the pictures it made.
        pub fn decode(&mut self, data: &[u8], time_us: u64) -> Result<Vec<Picture>> {
            let sample = sample_of(data, time_us)?;
            let mut pictures = Vec::new();
            // SAFETY: the sample is alive for the call.
            loop {
                let accepted = unsafe { self.transform.ProcessInput(0, &sample, 0) };
                match accepted {
                    Ok(()) => break,
                    // The decoder is busy: take what is ready, then try again.
                    Err(e) if e.code() == MF_E_NOTACCEPTING => pictures.extend(self.drain()?),
                    Err(e) => return Err(format!("the decoder refused a frame: {e}").into()),
                }
            }
            pictures.extend(self.drain()?);
            Ok(pictures)
        }

        /// Starts over after lost packets: the next keyframe decodes cleanly.
        pub fn flush(&mut self) {
            // SAFETY: a plain command to the transform.
            unsafe {
                let _ = self.transform.ProcessMessage(MFT_MESSAGE_COMMAND_FLUSH, 0);
            }
        }

        /// Takes the pictures the decoder has ready.
        fn drain(&mut self) -> Result<Vec<Picture>> {
            let mut pictures = Vec::new();
            loop {
                // SAFETY: the output buffer is ours until it is taken back.
                let provided = if self.provides_samples {
                    None
                } else {
                    unsafe {
                        let buffer = MFCreateMemoryBuffer(self.output_size.max(1))?;
                        let sample = MFCreateSample()?;
                        sample.AddBuffer(&buffer)?;
                        Some(sample)
                    }
                };
                let mut output = [MFT_OUTPUT_DATA_BUFFER {
                    dwStreamID: 0,
                    pSample: ManuallyDrop::new(provided),
                    dwStatus: 0,
                    pEvents: ManuallyDrop::new(None),
                }];
                let mut status = 0;
                // SAFETY: as above.
                let result = unsafe { self.transform.ProcessOutput(0, &mut output, &mut status) };
                let sample = unsafe { ManuallyDrop::take(&mut output[0].pSample) };
                drop(unsafe { ManuallyDrop::take(&mut output[0].pEvents) });
                match result {
                    Ok(()) => {
                        if let Some(sample) = sample
                            && let Some(picture) = self.read_picture(&sample)?
                        {
                            pictures.push(picture);
                        }
                    }
                    // Nothing more for now.
                    Err(e) if e.code() == MF_E_TRANSFORM_NEED_MORE_INPUT => return Ok(pictures),
                    // The stream's size changed: take the new output format
                    // and ask again; the picture follows.
                    Err(e) if e.code() == MF_E_TRANSFORM_STREAM_CHANGE => self.choose_output()?,
                    Err(e) => return Err(format!("the decoder failed: {e}").into()),
                }
            }
        }

        /// Copies a decoded picture out of its sample.
        fn read_picture(&self, sample: &IMFSample) -> Result<Option<Picture>> {
            // SAFETY: the buffer is locked while it is read and unlocked after.
            unsafe {
                let buffer = sample.ConvertToContiguousBuffer()?;
                let width = self.width as usize;
                let height = self.height as usize;
                if width == 0 || height == 0 {
                    return Ok(None);
                }
                if let Ok(two_d) = buffer.cast::<IMF2DBuffer>()
                    && let Some(pixels) = copy_from_2d(&two_d, width, height)
                {
                    return Ok(Some(Picture { width: width as u32, height: height as u32, pixels }));
                }
                let mut data: *mut u8 = ptr::null_mut();
                let mut length = 0u32;
                buffer.Lock(&mut data, None, Some(&mut length))?;
                let wanted = width * height * 3 / 2;
                let pixels = if data.is_null() || length == 0 {
                    Vec::new()
                } else {
                    let take = (wanted as u64).min(length as u64) as usize;
                    std::slice::from_raw_parts(data, take).to_vec()
                };
                buffer.Unlock()?;
                if pixels.len() < wanted {
                    return fail(format!(
                        "the decoder gave {} bytes for a {wanted} byte picture",
                        pixels.len()
                    ));
                }
                Ok(Some(Picture { width: width as u32, height: height as u32, pixels }))
            }
        }
    }

    /// Copies a picture out of a two-dimensional buffer: the luma rows, then
    /// the chroma rows, both tight.
    ///
    /// SAFETY: the buffer is locked while it is read and unlocked after.
    unsafe fn copy_from_2d(buffer: &IMF2DBuffer, width: usize, height: usize) -> Option<Vec<u8>> {
        // SAFETY: the caller promised the buffer outlives this call, and every
        // raw pointer below comes from the buffer's own lock.
        unsafe {
            let mut scan0: *mut u8 = ptr::null_mut();
            let mut pitch: i32 = 0;
            buffer.Lock2D(&mut scan0, &mut pitch).ok()?;
            if pitch <= 0 || scan0.is_null() {
                let _ = buffer.Unlock2D();
                return None;
            }
            let stride = pitch as usize;
            let mut out = vec![0u8; width * height * 3 / 2];
            for row in 0..height {
                let from = scan0.add(row * stride);
                std::ptr::copy_nonoverlapping(from, out.as_mut_ptr().add(row * width), width);
            }
            // The chroma plane follows the luma rows in the same allocation.
            let chroma_width = width / 2;
            let chroma_height = height / 2;
            let chroma_from = scan0.add(stride * height);
            for row in 0..chroma_height {
                let from = chroma_from.add(row * stride);
                let to = out.as_mut_ptr().add(width * height + row * chroma_width);
                std::ptr::copy_nonoverlapping(from, to, chroma_width);
            }
            let _ = buffer.Unlock2D();
            Some(out)
        }
    }

    /// A sample holding `data`.
    fn sample_of(data: &[u8], time_us: u64) -> Result<IMFSample> {
        let len = data.len();
        // SAFETY: the buffer is at least `len` long and locked while it is
        // written.
        unsafe {
            let buffer = MFCreateMemoryBuffer(len as u32)?;
            let mut target: *mut u8 = ptr::null_mut();
            buffer.Lock(&mut target, None, None)?;
            std::ptr::copy_nonoverlapping(data.as_ptr(), target, len);
            buffer.Unlock()?;
            buffer.SetCurrentLength(len as u32)?;
            let sample = MFCreateSample()?;
            sample.AddBuffer(&buffer)?;
            // In 100-nanosecond units.
            sample.SetSampleTime(time_us as i64 * 10)?;
            Ok(sample)
        }
    }
}

pub use imp::Decoder;

#[cfg(all(test, windows))]
mod tests {
    use super::*;

    /// The sample stream the desktop app's own tests use.
    const FIXTURE: &str = "../../desktop/app/src/win/testdata/testsrc.h264";

    #[test]
    fn a_stream_becomes_pictures() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(FIXTURE);
        let Ok(stream) = std::fs::read(&path) else {
            eprintln!("no fixture at {}", path.display());
            return;
        };
        let mut decoder = Decoder::new("h264").unwrap();
        let mut pictures = Vec::new();
        for chunk in stream.chunks(64 * 1024) {
            pictures.extend(decoder.decode(chunk, 0).unwrap());
        }
        assert!(!pictures.is_empty(), "the stream gave no pictures");
        let picture = &pictures[0];
        assert!(picture.width > 0 && picture.height > 0);
        assert_eq!(picture.pixels.len(), picture.width as usize * picture.height as usize * 3 / 2);
        // A picture of something is not uniformly black.
        let average = picture.pixels.iter().map(|&b| b as u32).sum::<u32>() / picture.pixels.len() as u32;
        assert!(average > 4, "the picture is black (average {average})");
    }
}
