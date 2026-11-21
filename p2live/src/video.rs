//! Video frames through ffmpeg (decoded to BGR like OpenCV's ffmpeg backend, then OpenCV's gray
//! conversion), cropped to the game feed.

use std::io::Read;
use std::process::{Command, Stdio};
use std::sync::Mutex;

use crate::analyze::Frames;
use crate::img::Gray;

#[derive(Clone, Copy, Debug)]
pub struct Feed {
    pub x0: usize,
    pub y0: usize,
    pub x1: usize,
    pub y1: usize,
}

#[derive(Clone, Debug)]
pub struct Info {
    pub w: usize,
    pub h: usize,
    pub fps: f64,
    pub frames: usize,
}

fn ffmpeg() -> String {
    std::env::var("P2LIVE_FFMPEG").unwrap_or_else(|_| "ffmpeg".into())
}
fn ffprobe() -> String {
    std::env::var("P2LIVE_FFPROBE").unwrap_or_else(|_| "ffprobe".into())
}

fn ratio(s: &str) -> f64 {
    let mut it = s.split('/');
    let a: f64 = it.next().and_then(|x| x.parse().ok()).unwrap_or(0.0);
    let b: f64 = it.next().and_then(|x| x.parse().ok()).unwrap_or(1.0);
    if b == 0.0 { 0.0 } else { a / b }
}

pub fn probe(path: &str) -> std::io::Result<Info> {
    let out = Command::new(ffprobe())
        .args(["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames:format=duration", "-of", "json", path])
        .output()?;
    let j: serde_json::Value = serde_json::from_slice(&out.stdout).map_err(std::io::Error::other)?;
    let s = &j["streams"][0];
    let w = s["width"].as_u64().unwrap_or(0) as usize;
    let h = s["height"].as_u64().unwrap_or(0) as usize;
    let mut fps = ratio(s["avg_frame_rate"].as_str().unwrap_or("0/1"));
    if fps <= 0.0 {
        fps = ratio(s["r_frame_rate"].as_str().unwrap_or("30/1"));
    }
    let frames = s["nb_frames"].as_str().and_then(|x| x.parse().ok()).unwrap_or_else(|| {
        let d: f64 = j["format"]["duration"].as_str().and_then(|x| x.parse().ok()).unwrap_or(0.0);
        (d * fps) as usize
    });
    Ok(Info { w, h, fps, frames })
}

/// `n` frames starting at frame `start`, BGR -> gray (cv2 fixed point), cropped to `feed`.
/// YUV -> BGR uses the BT.601 matrix whatever the stream is tagged, as OpenCV's reader does
/// (ffmpeg would honor a bt709 tag, and saturated colors would then differ by up to ~30 levels).
pub fn decode(path: &str, info: &Info, fps: f64, feed: Feed, start: usize, n: usize) -> std::io::Result<Vec<Gray>> {
    if n == 0 {
        return Ok(Vec::new());
    }
    let t = if start == 0 { 0.0 } else { (start as f64 - 0.5) / fps };
    let mut child = Command::new(ffmpeg())
        .args(["-v", "error", "-nostdin", "-ss", &format!("{t:.6}"), "-i", path, "-frames:v", &n.to_string(), "-an", "-vf", "scale=in_color_matrix=bt601", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let mut out = child.stdout.take().unwrap();
    let (w, h) = (info.w, info.h);
    let fw = feed.x1.min(w) - feed.x0;
    let fh = feed.y1.min(h) - feed.y0;
    let mut buf = vec![0u8; w * h * 3];
    let mut frames = Vec::with_capacity(n);
    loop {
        if frames.len() == n {
            break;
        }
        if out.read_exact(&mut buf).is_err() {
            break;
        }
        let mut g = vec![0u8; fw * fh];
        for y in 0..fh {
            let row = &buf[((feed.y0 + y) * w + feed.x0) * 3..];
            for x in 0..fw {
                let (b, gg, r) = (row[x * 3] as u32, row[x * 3 + 1] as u32, row[x * 3 + 2] as u32);
                g[y * fw + x] = ((b * 1868 + gg * 9617 + r * 4899 + 8192) >> 14) as u8;
            }
        }
        frames.push(Gray::new(fw, fh, g));
    }
    drop(out);
    let _ = child.kill();
    let _ = child.wait();
    Ok(frames)
}

/// A decoded window of a video, served as a frame source; requests outside it decode on demand.
pub struct Window {
    pub path: String,
    pub info: Info,
    pub fps: f64,
    pub feed: Feed,
    pub start: usize,
    pub frames: Vec<Gray>,
    pub extra_decodes: Mutex<usize>,
}

impl Window {
    pub fn new(path: &str, info: Info, fps: f64, feed: Feed, start: usize, stop: usize) -> std::io::Result<Self> {
        let stop = stop.min(info.frames);
        let frames = decode(path, &info, fps, feed, start, stop.saturating_sub(start))?;
        Ok(Window { path: path.to_string(), info, fps, feed, start, frames, extra_decodes: Mutex::new(0) })
    }
}

impl Frames for Window {
    fn frames(&self, start: usize, stop: usize) -> Vec<Gray> {
        let stop = stop.min(self.count());
        if start >= stop {
            return Vec::new();
        }
        if start >= self.start && stop <= self.start + self.frames.len() {
            return self.frames[start - self.start..stop - self.start].to_vec();
        }
        *self.extra_decodes.lock().unwrap() += 1;
        decode(&self.path, &self.info, self.fps, self.feed, start, stop - start).unwrap_or_default()
    }
    fn count(&self) -> usize {
        self.info.frames
    }
}
