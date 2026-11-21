//! Letter glyphs (templates.py), the cave list (caves.py) and the letter fall model (letters_model.py).

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, OnceLock, RwLock};

use crate::img::{prep_f, resize_area, Img};
use crate::rng;

pub const SPACE_MULT: f64 = 1.34;
pub const APOSTROPHE_MULT: f64 = 0.6875;

pub fn letters_dir() -> PathBuf {
    if let Ok(p) = std::env::var("P2LIVE_LETTERS") {
        return PathBuf::from(p);
    }
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../vendor/CaveGen/files/templates/letters")
}

pub fn digits_dir() -> PathBuf {
    if let Ok(p) = std::env::var("P2LIVE_DIGITS") {
        return PathBuf::from(p);
    }
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../p2seeds/src/p2seeds/data/digits")
}

/// cv2.imread(path, IMREAD_GRAYSCALE) as 0-255 floats.
pub fn read_gray_png(path: &Path) -> Option<Img> {
    let f = std::fs::File::open(path).ok()?;
    let mut dec = png::Decoder::new(f);
    dec.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = dec.read_info().ok()?;
    let mut buf = vec![0; reader.output_buffer_size()];
    let info = reader.next_frame(&mut buf).ok()?;
    let (w, h) = (info.width as usize, info.height as usize);
    let ch = info.color_type.samples();
    let mut out = Img::zeros(w, h);
    for i in 0..w * h {
        let p = &buf[i * ch..(i + 1) * ch];
        out.d[i] = match ch {
            1 | 2 => p[0] as f32,
            _ => {
                // cv2 RGB -> gray, fixed point
                let (r, g, b) = (p[0] as u32, p[1] as u32, p[2] as u32);
                ((b * 1868 + g * 9617 + r * 4899 + 8192) >> 14) as f32
            }
        };
    }
    Some(out)
}

fn glyph_cache() -> &'static RwLock<HashMap<char, Arc<Img>>> {
    static C: OnceLock<RwLock<HashMap<char, Arc<Img>>>> = OnceLock::new();
    C.get_or_init(|| RwLock::new(HashMap::new()))
}

/// The prepped glyph template of a character.
pub fn glyph(ch: char) -> Arc<Img> {
    if let Some(g) = glyph_cache().read().unwrap().get(&ch) {
        return g.clone();
    }
    let name = if !ch.is_ascii() {
        format!("u{:04x}", ch as u32)
    } else if ch.is_ascii_uppercase() {
        format!("{ch}{ch}")
    } else {
        ch.to_string()
    };
    let path = letters_dir().join(format!("{name}.png"));
    let raw = read_gray_png(&path).unwrap_or_else(|| panic!("no glyph template for {ch:?} at {}", path.display()));
    let g = Arc::new(prep_f(&raw));
    glyph_cache().write().unwrap().insert(ch, g.clone());
    g
}

/// The glyph resized to w x h (cv2 INTER_AREA), cached.
pub fn glyph_sized(ch: char, w: usize, h: usize) -> Arc<Img> {
    static C: OnceLock<RwLock<HashMap<(char, usize, usize), Arc<Img>>>> = OnceLock::new();
    let c = C.get_or_init(|| RwLock::new(HashMap::new()));
    if let Some(g) = c.read().unwrap().get(&(ch, w, h)) {
        return g.clone();
    }
    let g = Arc::new(resize_area(&glyph(ch), w, h));
    c.write().unwrap().insert((ch, w, h), g.clone());
    g
}

pub fn has_glyph(ch: char) -> bool {
    ch != ' ' && ch != '\''
}

pub fn advance_width(ch: char) -> f64 {
    match ch {
        ' ' => glyph('l').w as f64 * SPACE_MULT,
        '\'' => glyph('l').w as f64 * APOSTROPHE_MULT,
        _ => glyph(ch).w as f64,
    }
}

// ---------------------------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq)]
pub struct Cave {
    pub name: String,
    pub cavegen: &'static str,
    pub sublevels: u32,
    pub lang: &'static str,
    pub english: &'static str,
}

impl Cave {
    pub fn num_chars(&self) -> usize {
        self.name.chars().count()
    }
    pub fn label(&self) -> &str {
        if self.english.is_empty() { &self.name } else { self.english }
    }
}

const EN: [(&str, &str, u32, &str); 14] = [
    ("Emergence Cave", "EC", 2, "始まりの洞窟"),
    ("Subterranean Complex", "SCx", 9, "地下の秘密基地"),
    ("Frontier Cavern", "FC", 8, "辺境の洞窟"),
    ("Hole of Beasts", "HoB", 5, "けだものの穴"),
    ("White Flower Garden", "WFG", 5, "白い花園"),
    ("Bulblax Kingdom", "BK", 7, "デメマダラの王国"),
    ("Snagret Hole", "SH", 7, "ヘビガラスの穴"),
    ("Citadel of Spiders", "CoS", 5, "クモの根城"),
    ("Glutton's Kitchen", "GK", 6, "食神の台所"),
    ("Shower Room", "SR", 7, "シャワールーム"),
    ("Submerged Castle", "SC", 5, "水中の城"),
    ("Cavern of Chaos", "CoC", 10, "混沌の魔窟"),
    ("Hole of Heroes", "HoH", 15, "百戦錬磨の穴"),
    ("Dream Den", "DD", 14, "夢の穴"),
];

pub const POD_CAVES: [&str; 9] = ["EC", "HoB", "WFG", "SH", "BK", "SCx", "FC", "CoS", "GK"];

/// Every story cave, English first then Japanese (caves.CAVES order).
pub fn caves() -> Vec<Cave> {
    let mut v: Vec<Cave> = EN
        .iter()
        .map(|&(n, id, s, _)| Cave { name: n.to_string(), cavegen: id, sublevels: s, lang: "en", english: "" })
        .collect();
    v.extend(EN.iter().map(|&(n, id, s, ja)| Cave { name: ja.to_string(), cavegen: id, sublevels: s, lang: "ja", english: n }));
    v
}

// ---------------------------------------------------------------------------------------------
// letters_model

pub const START_POS: f64 = 200.0;
pub const FPS: u32 = 30;

/// Frames before character i starts, replicating Letters.java's float32 loop.
pub fn delay_frames(i: usize, n: usize) -> i64 {
    let mut t = i as f32 / n as f32;
    let step = 1.0f32 / FPS as f32;
    let mut frames = 0;
    while t > 0.0 {
        t -= step;
        frames += 1;
    }
    frames
}

#[inline]
pub fn pos(v: f64, f: f64) -> f64 {
    START_POS + (v - 0.5) * f - f * f / 2.0
}

pub fn layout_seed(letter_seed: u64, num_chars: usize) -> u64 {
    rng::next_seed(letter_seed, num_chars as i64) & rng::MASK31
}
