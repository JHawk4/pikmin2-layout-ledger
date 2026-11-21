//! Track each falling letter's height frame by frame (track.py).

use rayon::prelude::*;

use crate::calibrate::{Calibration, LetterBox};
use crate::img::{bright_level, match_direct, prep, pyround, Gray, Img};

pub const MIN_BRIGHT: f64 = 25.0;

#[derive(Clone, Debug)]
pub struct Track {
    pub index: usize,
    pub ch: char,
    pub rest_y: f64,
    pub frames: Vec<f64>,
    pub y: Vec<f64>,
    pub score: Vec<f64>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Blend {
    No,
    Yes,
    Pair,
}

fn subpixel(vals: &[f32], k: usize) -> f64 {
    if k > 0 && k + 1 < vals.len() {
        let (a, b, c) = (vals[k - 1] as f64, vals[k] as f64, vals[k + 1] as f64);
        let den = a - 2.0 * b + c;
        if den < 0.0 {
            return k as f64 + 0.5 * (a - c) / den;
        }
    }
    k as f64
}

fn argmax(v: &[f32]) -> usize {
    let mut best = 0;
    for i in 1..v.len() {
        if v[i] > v[best] {
            best = i;
        }
    }
    best
}

/// The strip a letter falls through, prepped, padded `pad` rows above.
fn strip(gray: &Gray, x0: usize, x1: usize, y_bot: usize, pad: usize, rf: f64) -> Img {
    let s = prep(&gray.crop(x0, 0, x1, y_bot), Some(rf));
    let mut out = Img::zeros(s.w, s.h + pad);
    out.d[pad * s.w..].copy_from_slice(&s.d);
    out
}

/// Best column of a match result: (column values, row of its max).
fn best_column(res: &Img) -> (Vec<f32>, usize) {
    let mut colmax = vec![f32::NEG_INFINITY; res.w];
    for y in 0..res.h {
        for x in 0..res.w {
            let v = res.at(x, y);
            if v > colmax[x] {
                colmax[x] = v;
            }
        }
    }
    let col = argmax(&colmax);
    let column: Vec<f32> = (0..res.h).map(|y| res.at(col, y)).collect();
    let row = argmax(&column);
    (column, row)
}

fn geometry(b: &LetterBox) -> (usize, usize, usize, usize) {
    let (h, w) = (b.template.h, b.template.w);
    let bx = pyround(b.x);
    let x0 = (bx - 2).max(0) as usize;
    let x1 = (bx + w as i64 + 2) as usize;
    let y_bot = (pyround(b.y) + h as i64 + 2) as usize;
    (x0, x1, y_bot, h)
}

pub fn track_letter(frames: &[Gray], b: &LetterBox, min_score: f64, refs: &[f64], blended: bool) -> Track {
    let t = &b.template;
    let (x0, x1, y_bot, pad) = geometry(b);
    let h = t.h;
    let (mut fr, mut ys, mut sc) = (Vec::new(), Vec::new(), Vec::new());
    for (k, gray) in frames.iter().enumerate() {
        if refs[k] < MIN_BRIGHT {
            continue;
        }
        let s = strip(gray, x0, x1, y_bot, pad, refs[k]);
        if s.std() < 1e-3 || s.w < t.w || s.h < t.h {
            continue;
        }
        let res = match_direct(&s, t);
        let (column, row) = best_column(&res);
        if blended {
            let sep = 3usize.max((0.25 * h as f64) as usize);
            let mut masked = column.clone();
            let lo = row.saturating_sub(sep);
            let hi = (row + sep + 1).min(masked.len());
            for v in &mut masked[lo..hi] {
                *v = -1.0;
            }
            let row2 = argmax(&masked);
            if column[row] as f64 >= min_score && masked[row2] as f64 >= min_score && (row2 as f64 - row as f64).abs() <= 1.6 * h as f64 {
                let (top, bot) = if row <= row2 { (row, row2) } else { (row2, row) };
                fr.push(k as f64);
                fr.push(k as f64 + 0.5);
                ys.push(subpixel(&column, top) - pad as f64);
                ys.push(subpixel(&column, bot) - pad as f64);
                sc.push(column[top] as f64);
                sc.push(column[bot] as f64);
                continue;
            }
        }
        if (column[row] as f64) < min_score {
            continue;
        }
        fr.push(k as f64);
        ys.push(subpixel(&column, row) - pad as f64);
        sc.push(column[row] as f64);
    }
    Track { index: b.index, ch: b.ch, rest_y: b.y, frames: fr, y: ys, score: sc }
}

fn pair_templates(t: &Img, max_d: usize) -> Vec<Img> {
    (0..=max_d)
        .map(|d| {
            let mut b = Img::zeros(t.w, t.h + d);
            for y in 0..t.h {
                for x in 0..t.w {
                    let v = 0.5 * t.at(x, y);
                    b.d[y * t.w + x] += v;
                    b.d[(y + d) * t.w + x] += v;
                }
            }
            b
        })
        .collect()
}

pub fn track_letter_pair(frames: &[Gray], b: &LetterBox, min_score: f64, refs: &[f64]) -> Track {
    let t = &b.template;
    let max_d = (1.6 * t.h as f64) as usize;
    let pairs = pair_templates(t, max_d);
    let (x0, x1, y_bot, pad) = geometry(b);
    let (mut fr, mut ys, mut sc) = (Vec::new(), Vec::new(), Vec::new());
    for (k, gray) in frames.iter().enumerate() {
        if refs[k] < MIN_BRIGHT {
            continue;
        }
        let s = strip(gray, x0, x1, y_bot, pad, refs[k]);
        if s.std() < 1e-3 || s.w < t.w {
            continue;
        }
        let best: Vec<(f64, usize, Vec<f32>)> = pairs
            .iter()
            .map(|p| {
                if p.h > s.h {
                    return (-1.0, 0, Vec::new());
                }
                let (column, row) = best_column(&match_direct(&s, p));
                (column[row] as f64, row, column)
            })
            .collect();
        let mut d = 0;
        for i in 1..best.len() {
            if best[i].0 > best[d].0 {
                d = i;
            }
        }
        let (score, row, column) = (&best[d].0, best[d].1, &best[d].2);
        if *score < min_score {
            continue;
        }
        let top = subpixel(column, row) - pad as f64;
        let mut dd = d as f64;
        if d > 0 && d + 1 < best.len() {
            let (a, bb, c) = (best[d - 1].0, best[d].0, best[d + 1].0);
            let den = a - 2.0 * bb + c;
            if den < 0.0 {
                dd = d as f64 + 0.5 * (a - c) / den;
            }
        }
        fr.push(k as f64);
        fr.push(k as f64 + 0.5);
        ys.push(top);
        ys.push(top + dd);
        sc.push(*score);
        sc.push(*score);
    }
    Track { index: b.index, ch: b.ch, rest_y: b.y, frames: fr, y: ys, score: sc }
}

pub fn track_all(frames: &[Gray], cal: &Calibration, min_score: f64, blended: Blend) -> Vec<Track> {
    let refs: Vec<f64> = frames.iter().map(bright_level).collect();
    cal.letters
        .par_iter()
        .map(|b| match blended {
            Blend::Pair => track_letter_pair(frames, b, min_score, &refs),
            Blend::Yes => track_letter(frames, b, min_score, &refs, true),
            Blend::No => track_letter(frames, b, min_score, &refs, false),
        })
        .collect()
}
