//! Frame sources: a camera (DirectShow, which includes the OBS Virtual Camera) or a video file
//! played at real speed (for trying the app without a game; needs ffmpeg on PATH).

use std::io::Read;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{sync_channel, Receiver, SyncSender};
use std::thread::JoinHandle;

use p2live::img::Gray;
use serde::{Deserialize, Serialize};

/// One captured frame, RGB24 top-down.
pub struct Frame {
    pub w: usize,
    pub h: usize,
    pub rgb: Vec<u8>,
}

/// A rectangle of the capture, in its pixels (x1, y1 exclusive).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Crop {
    pub x0: usize,
    pub y0: usize,
    pub x1: usize,
    pub y1: usize,
}

impl Crop {
    pub fn full(w: usize, h: usize) -> Crop {
        Crop { x0: 0, y0: 0, x1: w, y1: h }
    }
    /// Clamped to a w x h frame and at least 16 x 16.
    pub fn clamp(self, w: usize, h: usize) -> Crop {
        let x0 = self.x0.min(w.saturating_sub(16));
        let y0 = self.y0.min(h.saturating_sub(16));
        Crop { x0, y0, x1: self.x1.clamp(x0 + 16, w.max(x0 + 16)).min(w), y1: self.y1.clamp(y0 + 16, h.max(y0 + 16)).min(h) }
    }
    pub fn w(&self) -> usize {
        self.x1 - self.x0
    }
    pub fn h(&self) -> usize {
        self.y1 - self.y0
    }
}

impl Frame {
    pub fn from_rgb(w: usize, h: usize, rgb: Vec<u8>) -> Frame {
        Frame { w, h, rgb }
    }

    /// The cropped part in gray, as OpenCV converts BGR (what the detector was tuned on).
    pub fn gray(&self, crop: Crop) -> Gray {
        let c = crop.clamp(self.w, self.h);
        let (fw, fh) = (c.w(), c.h());
        let mut g = vec![0u8; fw * fh];
        for y in 0..fh {
            let row = &self.rgb[((c.y0 + y) * self.w + c.x0) * 3..];
            for x in 0..fw {
                let (r, gg, b) = (row[x * 3] as u32, row[x * 3 + 1] as u32, row[x * 3 + 2] as u32);
                g[y * fw + x] = ((b * 1868 + gg * 9617 + r * 4899 + 8192) >> 14) as u8;
            }
        }
        Gray::new(fw, fh, g)
    }

    /// Gray of the whole frame shrunk to at most `max_w` wide (for finding the game picture).
    pub fn small_gray(&self, max_w: usize) -> (Gray, usize) {
        let step = self.w.div_ceil(max_w).max(1);
        let (sw, sh) = (self.w / step, self.h / step);
        let mut g = vec![0u8; sw * sh];
        for y in 0..sh {
            for x in 0..sw {
                let i = ((y * step) * self.w + x * step) * 3;
                let (r, gg, b) = (self.rgb[i] as u32, self.rgb[i + 1] as u32, self.rgb[i + 2] as u32);
                g[y * sw + x] = ((b * 1868 + gg * 9617 + r * 4899 + 8192) >> 14) as u8;
            }
        }
        (Gray::new(sw, sh, g), step)
    }
}

/// Where frames come from (saved in a profile).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum SourceSpec {
    Camera { name: String },
    Video { path: String },
}

impl SourceSpec {
    pub fn label(&self) -> String {
        match self {
            SourceSpec::Camera { name } => name.clone(),
            SourceSpec::Video { path } => format!("video: {}", std::path::Path::new(path).file_name().map(|f| f.to_string_lossy().to_string()).unwrap_or_default()),
        }
    }
}

/// The cameras to offer (the OBS Virtual Camera first when present).
pub fn cameras() -> Vec<String> {
    #[cfg(windows)]
    let mut v = crate::dshow::list();
    #[cfg(not(windows))]
    let mut v: Vec<String> = Vec::new();
    v.sort_by_key(|n| !n.to_lowercase().contains("obs virtual camera"));
    v
}

/// A running source: frames arrive on `rx`; dropping it stops the source.
pub struct Source {
    pub rx: Receiver<Frame>,
    pub fps: f64,
    pub w: usize,
    pub h: usize,
    _keep: Keep,
}

enum Keep {
    #[cfg(windows)]
    Camera(#[allow(dead_code)] crate::dshow::Camera),
    Video(Child, Option<JoinHandle<()>>),
}

impl Drop for Keep {
    fn drop(&mut self) {
        if let Keep::Video(child, t) = self {
            let _ = child.kill();
            let _ = child.wait();
            if let Some(t) = t.take() {
                let _ = t.join();
            }
        }
    }
}

/// Queue length between the capture and the detector: about two seconds at 60 fps.
const QUEUE: usize = 120;

impl Source {
    pub fn open(spec: &SourceSpec) -> Result<Source, String> {
        let (tx, rx) = sync_channel(QUEUE);
        match spec {
            #[cfg(windows)]
            SourceSpec::Camera { name } => {
                let cam = crate::dshow::Camera::open(name, 720, tx)?;
                Ok(Source { rx, fps: cam.fps, w: cam.w, h: cam.h, _keep: Keep::Camera(cam) })
            }
            #[cfg(not(windows))]
            SourceSpec::Camera { .. } => Err("cameras are only supported on Windows so far".into()),
            SourceSpec::Video { path } => open_video(path, tx, rx),
        }
    }
}

fn open_video(path: &str, tx: SyncSender<Frame>, rx: Receiver<Frame>) -> Result<Source, String> {
    let info = p2live::video::probe(path).map_err(|e| format!("reading {path} (is ffmpeg installed?): {e}"))?;
    let (w, h) = (info.w, info.h);
    let mut child = Command::new(std::env::var("P2LIVE_FFMPEG").unwrap_or_else(|_| "ffmpeg".into()))
        .args(["-v", "error", "-nostdin", "-re", "-stream_loop", "-1", "-i", path, "-an", "-vf", "scale=in_color_matrix=bt601", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("starting ffmpeg: {e}"))?;
    let mut out = child.stdout.take().unwrap();
    let t = std::thread::spawn(move || {
        loop {
            let mut buf = vec![0u8; w * h * 3];
            if out.read_exact(&mut buf).is_err() {
                break;
            }
            if tx.send(Frame::from_rgb(w, h, buf)).is_err() {
                break;
            }
        }
    });
    Ok(Source { rx, fps: info.fps, w, h, _keep: Keep::Video(child, Some(t)) })
}
