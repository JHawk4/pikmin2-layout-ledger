//! Track each falling letter's height frame by frame (track.py).

use std::collections::HashMap;
use std::sync::Mutex;

use rayon::prelude::*;

use crate::calibrate::{Calibration, LetterBox};
use crate::img::{bright_level, match_direct, match_pairs, prep, pyround, Gray, Img};

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

/// One letter's template match on one frame: the best column of the match result and its row.
#[derive(Clone)]
struct Single {
    column: Vec<f32>,
    row: usize,
}

/// The pair-template match on one frame: every gap's best score, the best gap `d` and its column.
#[derive(Clone)]
struct PairMatch {
    scores: Vec<f64>,
    d: usize,
    row: usize,
    column: Vec<f32>,
}

/// Template matches by (letter index, absolute frame), shared by every analysis of one entry
/// screen. The live detector analyzes the same fall again with more frames and in several
/// variants; the variants differ only in thresholds, so each frame is matched once per letter.
/// `None` is a frame the letter cannot be matched on (too dark or flat).
#[derive(Default)]
pub struct MatchCache {
    single: Mutex<HashMap<(usize, usize), Option<Single>>>,
    pair: Mutex<HashMap<(usize, usize), Option<PairMatch>>>,
}

impl MatchCache {
    pub fn len(&self) -> usize {
        self.single.lock().unwrap().len() + self.pair.lock().unwrap().len()
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// Where a call's frames sit in the stream, for the cache: `ids[k]` is frame k's absolute index.
#[derive(Clone, Copy)]
pub struct Reuse<'a> {
    pub cache: &'a MatchCache,
    pub ids: &'a [usize],
}

fn single_match(gray: &Gray, b: &LetterBox, rf: f64) -> Option<Single> {
    let t = &b.template;
    if rf < MIN_BRIGHT {
        return None;
    }
    let (x0, x1, y_bot, pad) = geometry(b);
    let s = strip(gray, x0, x1, y_bot, pad, rf);
    if s.std() < 1e-3 || s.w < t.w || s.h < t.h {
        return None;
    }
    let (column, row) = best_column(&match_direct(&s, t));
    Some(Single { column, row })
}

fn pair_match(gray: &Gray, b: &LetterBox, rf: f64, pairs: &[Img]) -> Option<PairMatch> {
    let t = &b.template;
    if rf < MIN_BRIGHT {
        return None;
    }
    let (x0, x1, y_bot, pad) = geometry(b);
    let s = strip(gray, x0, x1, y_bot, pad, rf);
    if s.std() < 1e-3 || s.w < t.w {
        return None;
    }
    let best: Vec<(f64, usize, Vec<f32>)> = match_pairs(&s, t, pairs)
        .into_iter()
        .map(|res| match res {
            None => (-1.0, 0, Vec::new()),
            Some(res) => {
                let (column, row) = best_column(&res);
                (column[row] as f64, row, column)
            }
        })
        .collect();
    let mut d = 0;
    for i in 1..best.len() {
        if best[i].0 > best[d].0 {
            d = i;
        }
    }
    let scores = best.iter().map(|x| x.0).collect();
    let (_, row, column) = best.into_iter().nth(d).unwrap();
    Some(PairMatch { scores, d, row, column })
}

/// Frame k's match, from the cache when there is one.
fn cached<T: Clone>(map: Option<&Mutex<HashMap<(usize, usize), Option<T>>>>, key: Option<(usize, usize)>, f: impl FnOnce() -> Option<T>) -> Option<T> {
    if let (Some(m), Some(k)) = (map, key) {
        if let Some(v) = m.lock().unwrap().get(&k) {
            return v.clone();
        }
        let v = f();
        m.lock().unwrap().insert(k, v.clone());
        return v;
    }
    f()
}

pub fn track_letter(frames: &[Gray], b: &LetterBox, min_score: f64, refs: &[f64], blended: bool, reuse: Option<Reuse>) -> Track {
    let h = b.template.h;
    let pad = geometry(b).3;
    let (mut fr, mut ys, mut sc) = (Vec::new(), Vec::new(), Vec::new());
    for (k, gray) in frames.iter().enumerate() {
        let key = reuse.map(|r| (b.index, r.ids[k]));
        let Some(Single { column, row }) = cached(reuse.map(|r| &r.cache.single), key, || single_match(gray, b, refs[k])) else { continue };
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

fn letter_pairs(b: &LetterBox) -> Vec<Img> {
    pair_templates(&b.template, (1.6 * b.template.h as f64) as usize)
}

pub fn track_letter_pair(frames: &[Gray], b: &LetterBox, min_score: f64, refs: &[f64], reuse: Option<Reuse>) -> Track {
    let pad = geometry(b).3;
    let mut pairs: Option<Vec<Img>> = None;
    let (mut fr, mut ys, mut sc) = (Vec::new(), Vec::new(), Vec::new());
    for (k, gray) in frames.iter().enumerate() {
        let key = reuse.map(|r| (b.index, r.ids[k]));
        let m = cached(reuse.map(|r| &r.cache.pair), key, || pair_match(gray, b, refs[k], pairs.get_or_insert_with(|| letter_pairs(b))));
        let Some(PairMatch { scores, d, row, column }) = m else { continue };
        let score = scores[d];
        if score < min_score {
            continue;
        }
        let top = subpixel(&column, row) - pad as f64;
        let mut dd = d as f64;
        if d > 0 && d + 1 < scores.len() {
            let (a, bb, c) = (scores[d - 1], scores[d], scores[d + 1]);
            let den = a - 2.0 * bb + c;
            if den < 0.0 {
                dd = d as f64 + 0.5 * (a - c) / den;
            }
        }
        fr.push(k as f64);
        fr.push(k as f64 + 0.5);
        ys.push(top);
        ys.push(top + dd);
        sc.push(score);
        sc.push(score);
    }
    Track { index: b.index, ch: b.ch, rest_y: b.y, frames: fr, y: ys, score: sc }
}

pub fn track_all(frames: &[Gray], cal: &Calibration, min_score: f64, blended: Blend, reuse: Option<Reuse>) -> Vec<Track> {
    let refs: Vec<f64> = frames.iter().map(bright_level).collect();
    cal.letters
        .par_iter()
        .map(|b| match blended {
            Blend::Pair => track_letter_pair(frames, b, min_score, &refs, reuse),
            Blend::Yes => track_letter(frames, b, min_score, &refs, true, reuse),
            Blend::No => track_letter(frames, b, min_score, &refs, false, reuse),
        })
        .collect()
}

/// Match every letter on `frames` (absolute indices `ids`) ahead of the analyses that will need
/// them: the live detector does this once the name is read, while the fall's last frames arrive.
pub fn prefill(frames: &[Gray], ids: &[usize], cal: &Calibration, cache: &MatchCache) {
    let reuse = Some(Reuse { cache, ids });
    let refs: Vec<f64> = frames.iter().map(bright_level).collect();
    cal.letters.par_iter().for_each(|b| {
        let _ = track_letter(frames, b, 2.0, &refs, false, reuse);
        let _ = track_letter_pair(frames, b, 2.0, &refs, reuse);
    });
}
