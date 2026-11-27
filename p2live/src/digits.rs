//! The sublevel number on the "Sublevel N" line (digits.py, analyze.digit_crop / split_digits / _read_sublevel).

use std::collections::BTreeMap;
use std::sync::OnceLock;

use crate::img::{prep, resize_area, Gray, Img};
use crate::templates::{digits_dir, read_gray_png};

const SIZE: (usize, usize) = (24, 32);
const MIN_SCORE: f64 = 0.6;
const MIN_MARGIN: f64 = 0.08;

fn norm(img: &Img) -> Vec<f64> {
    let a = resize_area(img, SIZE.0, SIZE.1);
    let mean: f64 = a.d.iter().map(|&x| x as f64).sum::<f64>() / a.d.len() as f64;
    let c: Vec<f64> = a.d.iter().map(|&x| x as f64 - mean).collect();
    let n = c.iter().map(|x| x * x).sum::<f64>().sqrt();
    if n > 0.0 { c.iter().map(|x| x / n).collect() } else { c }
}

fn references() -> &'static BTreeMap<u32, Vec<Vec<f64>>> {
    static R: OnceLock<BTreeMap<u32, Vec<Vec<f64>>>> = OnceLock::new();
    R.get_or_init(|| {
        let mut refs: BTreeMap<u32, Vec<Vec<f64>>> = BTreeMap::new();
        let mut paths: Vec<_> = std::fs::read_dir(digits_dir()).map(|d| d.filter_map(|e| e.ok()).map(|e| e.path()).collect()).unwrap_or_default();
        paths.sort();
        for p in paths {
            if p.extension().and_then(|e| e.to_str()) != Some("png") {
                continue;
            }
            let stem = p.file_stem().unwrap().to_string_lossy().to_string();
            let Ok(value) = stem.split('_').next().unwrap_or("").parse::<u32>() else { continue };
            if value > 9 {
                continue;
            }
            if let Some(mut img) = read_gray_png(&p) {
                for x in img.d.iter_mut() {
                    *x /= 255.0;
                }
                refs.entry(value).or_default().push(norm(&img));
            }
        }
        refs
    })
}

pub fn read(crop: &Img) -> (Option<u32>, f64) {
    if crop.d.is_empty() || references().is_empty() {
        return (None, 0.0);
    }
    let c = norm(crop);
    let mut scored: Vec<(f64, u32)> = references()
        .iter()
        .map(|(&v, rs)| (rs.iter().map(|r| c.iter().zip(r).map(|(a, b)| a * b).sum::<f64>()).fold(f64::NEG_INFINITY, f64::max), v))
        .collect();
    scored.sort_by(|a, b| b.partial_cmp(a).unwrap());
    let (best, value) = scored[0];
    let second = if scored.len() > 1 { scored[1].0 } else { -1.0 };
    if best < MIN_SCORE || best - second < MIN_MARGIN {
        return (None, best);
    }
    (Some(value), best)
}

pub fn read_number(parts: &[Img]) -> Option<u32> {
    if parts.is_empty() || parts.len() > 2 {
        return None;
    }
    let mut n = 0;
    for p in parts {
        n = n * 10 + read(p).0?;
    }
    (n >= 1).then_some(n)
}

/// analyze.digit_crop: the number at the end of the "Sublevel N" line, prepped.
pub fn digit_crop(feed: &Gray, lang: &str) -> Option<Img> {
    let h = feed.h;
    let (y0, y1) = ((0.46 * h as f64) as usize, (0.70 * h as f64) as usize);
    let p = prep(&feed.crop(0, y0, feed.w, y1), None);
    let on = |x: usize, y: usize| p.at(x, y) > 0.5;
    let rows: Vec<usize> = (0..p.h).filter(|&y| (0..p.w).filter(|&x| on(x, y)).count() as f64 / p.w as f64 > 0.01).collect();
    let cols: Vec<usize> = (0..p.w).filter(|&x| (0..p.h).any(|y| on(x, y))).collect();
    if rows.is_empty() || cols.is_empty() {
        return None;
    }
    let gap = 3usize.max((0.25 * (rows[rows.len() - 1] - rows[0] + 1) as f64) as usize);
    let mut groups = Vec::new();
    let mut start = cols[0];
    for w in cols.windows(2) {
        if w[1] - w[0] > gap {
            groups.push((start, w[0]));
            start = w[1];
        }
    }
    groups.push((start, cols[cols.len() - 1]));
    let (mut x0, x1) = groups[groups.len() - 1];
    let hh = (rows[rows.len() - 1] - rows[0] + 1) as f64;
    if lang == "ja" && groups.len() > 1 {
        let (a, b) = groups[groups.len() - 2];
        if ((b - a + 1) as f64) < 0.45 * hh && (x0 - b) as f64 <= 0.8 * hh {
            x0 = a;
        }
    }
    let glyph_rows: Vec<usize> = (0..p.h).filter(|&y| (x0..=x1).any(|x| on(x, y))).collect();
    if glyph_rows.is_empty() {
        return None;
    }
    Some(p.crop(x0, glyph_rows[0], x1 + 1, glyph_rows[glyph_rows.len() - 1] + 1))
}

/// analyze.split_digits: cut a number into digits at empty columns.
pub fn split_digits(crop: &Img) -> Vec<Img> {
    if crop.d.is_empty() {
        return Vec::new();
    }
    let on = |x: usize, y: usize| crop.at(x, y) > 0.5;
    let h = crop.h as f64;
    let mut parts = Vec::new();
    let mut start: Option<usize> = None;
    for x in 0..=crop.w {
        let f = x < crop.w && (0..crop.h).any(|y| on(x, y));
        if f && start.is_none() {
            start = Some(x);
        } else if !f {
            if let Some(s) = start.take() {
                parts.push((s, x));
            }
        }
    }
    let mut merged: Vec<(usize, usize)> = Vec::new();
    for (a, b) in parts {
        if let Some(last) = merged.last_mut() {
            if (((b - a) as f64) < 0.12 * h || ((last.1 - last.0) as f64) < 0.12 * h) && a - last.1 <= 2 {
                last.1 = b;
                continue;
            }
        }
        merged.push((a, b));
    }
    let mut out = Vec::new();
    for (a, b) in merged {
        let rows: Vec<usize> = (0..crop.h).filter(|&y| (a..b).any(|x| on(x, y))).collect();
        if !rows.is_empty() && (rows[rows.len() - 1] - rows[0] + 1) as f64 >= 0.6 * h {
            out.push(crop.crop(a, rows[0], b, rows[rows.len() - 1] + 1));
        }
    }
    out
}

/// analyze._read_sublevel: majority of clear reads on 7 frames of the settled run.
pub fn read_sublevel(frames: &[Gray], a: usize, b: usize, lang: &str) -> (Option<u32>, BTreeMap<u32, u32>) {
    let n = 7;
    let mut votes: BTreeMap<u32, u32> = BTreeMap::new();
    for i in 0..n {
        let step = (b as f64 - a as f64) / (n - 1) as f64;
        let j = if i == n - 1 { b } else { (a as f64 + i as f64 * step) as usize };
        let crop = digit_crop(&frames[j], lang);
        let parts = crop.as_ref().map(split_digits).unwrap_or_default();
        let mut value = if parts.len() == 2 { read_number(&parts) } else { None };
        if value.is_none() {
            if let Some(c) = &crop {
                value = read(c).0;
            }
        }
        if let Some(v) = value {
            *votes.entry(v).or_default() += 1;
        }
    }
    if votes.is_empty() {
        return (None, votes);
    }
    let total: u32 = votes.values().sum();
    // max by count; on ties the first in dict order (insertion) wins in Python; use smallest frame order
    let (&value, &count) = votes.iter().max_by_key(|(_, c)| **c).unwrap();
    ((count as f64 > total as f64 / 2.0).then_some(value), votes)
}
