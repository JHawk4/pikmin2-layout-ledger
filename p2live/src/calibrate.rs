//! Entry-screen check (events.py) and cave-name recognition (calibrate.py).

use crate::img::{max_loc, percentile, prep, pyround, FftImage, Gray, Img};
use crate::templates::{advance_width, glyph, glyph_sized, has_glyph, Cave};

pub const NAME_BAND: (f64, f64) = (0.20, 0.42);
pub const SUB_BAND: (f64, f64) = (0.46, 0.70);

/// events.is_entry_screen: dark, two lines of bright text, nothing bright near the edges.
pub fn is_entry_screen(g: &Gray) -> bool {
    if g.mean() > 60.0 {
        return false;
    }
    let h = g.h;
    // prep(g) > 0.5  <=>  (g - 90) / 120 > 0.5
    let rows: Vec<f64> = (0..h)
        .map(|y| g.row(y).iter().filter(|&&v| (v as f32 - 90.0) / 120.0 > 0.5).count() as f64 / g.w.max(1) as f64)
        .collect();
    let band_max = |a: f64, b: f64| -> f64 {
        let (y0, y1) = ((a * h as f64) as usize, (b * h as f64) as usize);
        rows[y0.min(h)..y1.min(h)].iter().cloned().fold(f64::NEG_INFINITY, f64::max)
    };
    let name = band_max(NAME_BAND.0, NAME_BAND.1) > 0.015;
    let sub = band_max(SUB_BAND.0, SUB_BAND.1) > 0.015;
    // Above the name only the middle half of the width counts: runners often put a timer or
    // splits in a top corner, and gameplay is still ruled out by the HUD along the bottom.
    let top = (0.12 * h as f64) as usize;
    let bot = (0.80 * h as f64) as usize;
    let (x0, x1) = ((0.25 * g.w as f64) as usize, (0.75 * g.w as f64) as usize);
    let top_rows = (0..top.min(h)).map(|y| {
        g.row(y)[x0..x1].iter().filter(|&&v| (v as f32 - 90.0) / 120.0 > 0.5).count() as f64 / (x1 - x0).max(1) as f64
    });
    let outside = top_rows.chain(rows[bot.min(h)..].iter().cloned()).fold(f64::NEG_INFINITY, f64::max);
    if h == 0 {
        return false;
    }
    name && sub && outside < 0.005
}

/// analyze.entry_runs: runs [a, b] of consecutive entry-screen frames, at least `min_len` long.
pub fn entry_runs_from_flags(flags: &[bool], min_len: usize) -> Vec<(usize, usize)> {
    let mut runs = Vec::new();
    let mut k = 0;
    while k < flags.len() {
        if flags[k] {
            let a = k;
            while k < flags.len() && flags[k] {
                k += 1;
            }
            if k - a >= min_len {
                runs.push((a, k - 1));
            }
        }
        k += 1;
    }
    runs
}

pub fn entry_runs(frames: &[Gray]) -> Vec<(usize, usize)> {
    let flags: Vec<bool> = frames.iter().map(is_entry_screen).collect();
    entry_runs_from_flags(&flags, 6)
}

// ---------------------------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct LetterBox {
    pub index: usize,
    pub ch: char,
    pub x: f64,
    pub y: f64,
    pub template: Img,
}

#[derive(Clone, Debug)]
pub struct Calibration {
    pub cave: Cave,
    pub score: f64,
    pub sx: f64,
    pub sy: f64,
    pub x: i64,
    pub y: i64,
    pub letters: Vec<LetterBox>,
    pub runner_up: Option<(String, f64)>,
    pub gsx: Option<f64>,
}

pub struct Piece {
    pub index: usize,
    pub ch: char,
    pub px: i64,
    pub g: Img,
}

/// calibrate.compose: `name` drawn at scale (sx, sy), glyphs `gsx` wide.
pub fn compose(name: &str, sx: f64, sy: f64, gsx: Option<f64>) -> (Img, Vec<Piece>) {
    let gsx_v = gsx.unwrap_or(sx);
    let h = pyround(40.0 * sy).max(1) as usize;
    let mut pieces: Vec<Piece> = Vec::new();
    let mut x = 0.0f64;
    for (i, ch) in name.chars().enumerate() {
        let w_adv = advance_width(ch) * sx;
        if has_glyph(ch) {
            let g = glyph(ch);
            let gw = pyround(g.w as f64 * gsx_v).max(1) as usize;
            let gh = pyround(g.h as f64 * sy).max(1) as usize;
            let gs = glyph_sized(ch, gw, gh);
            let gs = if gs.h > h { gs.rows(0, h) } else { (*gs).clone() };
            let px = pyround(x + if gsx_v != sx { (w_adv - gw as f64) / 2.0 } else { 0.0 });
            pieces.push(Piece { index: i, ch, px, g: gs });
        }
        x += w_adv;
    }
    let minpx = pieces.iter().map(|p| p.px).min().unwrap_or(0);
    if -minpx > 0 {
        for p in pieces.iter_mut() {
            p.px -= minpx;
        }
    }
    let right = pieces.iter().map(|p| p.px + p.g.w as i64).max().unwrap_or(0);
    let width = pyround(x.max(right as f64)) as usize + 2;
    let mut img = Img::zeros(width, h);
    for p in &pieces {
        for yy in 0..p.g.h {
            for xx in 0..p.g.w {
                let tx = p.px as usize + xx;
                if tx < width {
                    let v = p.g.at(xx, yy);
                    if v > img.at(tx, yy) {
                        img.set(tx, yy, v);
                    }
                }
            }
        }
    }
    (img, pieces)
}

fn bright_extent(p: &Img, thr: f32) -> Option<(i64, i64, i64, i64)> {
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    for y in 0..p.h {
        for x in 0..p.w {
            if p.at(x, y) > thr {
                xs.push(x as f64);
                ys.push(y as f64);
            }
        }
    }
    if xs.len() < 20 {
        return None;
    }
    Some((
        percentile(&xs, 0.5) as i64,
        percentile(&xs, 99.5) as i64,
        percentile(&ys, 2.0) as i64,
        percentile(&ys, 98.0) as i64,
    ))
}

fn linspace(a: f64, b: f64, n: usize) -> Vec<f64> {
    if n == 1 {
        return vec![a];
    }
    // numpy.linspace: a + i*step, last element exactly b
    let step = (b - a) / (n - 1) as f64;
    (0..n).map(|i| if i == n - 1 { b } else { a + i as f64 * step }).collect()
}

type Fit = (f64, f64, f64, (usize, usize)); // score, sx, sy, loc

fn best_fit(region: &FftImage, cave: &Cave, sys: &[f64], sx_factors: &[f64], extra: &[f64], sy0: f64, wide: f64, text_w: f64) -> Option<Fit> {
    let mut best: Option<Fit> = None;
    let consider = |img: &Img, sx: f64, sy: f64, best: &mut Option<Fit>| {
        if img.h >= region.im.h || img.w >= region.im.w {
            return;
        }
        let (score, loc) = max_loc(&region.match_t(img));
        let score = score as f64;
        if best.is_none_or(|b| score > b.0) {
            *best = Some((score, sx, sy, loc));
        }
    };
    if cave.lang == "ja" {
        let pitches = linspace(0.95, 1.3, 2 * sx_factors.len() - 1);
        for &sy in sys {
            for &pitch in &pitches {
                let p = wide * pitch;
                let (img, _) = compose(&cave.name, sy * p, sy, Some(sy));
                consider(&img, sy * p, sy, &mut best);
            }
        }
        return best;
    }
    let base_w = compose(&cave.name, 1.0, 1.0, None).0.w as f64;
    let sx0 = sy0.min(text_w / (base_w - 4.0).max(1.0));
    for &sy in sys {
        let mut sxs: Vec<f64> = sx_factors.iter().map(|f| sx0 * f).chain(extra.iter().map(|r| sy * r)).collect();
        sxs.sort_by(|a, b| a.partial_cmp(b).unwrap());
        sxs.dedup();
        for sx in sxs {
            let (img, _) = compose(&cave.name, sx, sy, None);
            consider(&img, sx, sy, &mut best);
        }
    }
    best
}

/// A stream's name scale, learned from a screen that calibrated in full: the height scale and
/// the width/height ratio of the capture (a 4:3 game shown 16:9 has ~1.33). Long English names
/// are drawn narrower by the game, so their width also comes from the measured text width.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ScaleHint {
    pub sy: f64,
    pub ratio: f64,
}

impl Calibration {
    /// The scale this screen shows. A scrunched English name gives too small a ratio, so a stream
    /// keeps the largest ratio it has seen (`ScaleHint::merge`).
    pub fn hint(&self) -> ScaleHint {
        ScaleHint { sy: self.sy, ratio: self.sx / self.sy }
    }
}

impl ScaleHint {
    pub fn merge(self, newer: ScaleHint) -> ScaleHint {
        ScaleHint { sy: newer.sy, ratio: self.ratio.max(newer.ratio) }
    }
}

/// Live calibration with a known scale: each cave's name is matched at the hinted scale (plus
/// the width the text actually has, for scrunched English names), then the two best are refined
/// in a small neighbourhood. About 1/10 of the matches of `calibrate`.
pub fn calibrate_hinted(settled: &Gray, caves: &[Cave], hint: ScaleHint) -> Option<Calibration> {
    use rayon::prelude::*;
    let p = prep(settled, None);
    let h = p.h;
    let y0 = (0.14 * h as f64) as usize;
    let y1 = (0.48 * h as f64) as usize;
    let region = p.rows(y0, y1);
    let (ex0, ex1, _, _) = bright_extent(&region, 0.35)?;
    let text_w = (ex1 - ex0 + 1) as f64;
    let region = FftImage::new(region);
    let score_at = |cave: &Cave, sx: f64, sy: f64| -> Option<Fit> {
        let gsx = if cave.lang == "ja" { Some(sy) } else { None };
        let (img, _) = compose(&cave.name, sx, sy, gsx);
        if img.h >= region.im.h || img.w >= region.im.w {
            return None;
        }
        let (score, loc) = max_loc(&region.match_t(&img));
        Some((score as f64, sx, sy, loc))
    };
    let sx_options = |cave: &Cave, sy: f64, ratio: f64| -> Vec<f64> {
        let mut v = vec![sy * ratio];
        if cave.lang != "ja" {
            // the width the text has (long names are drawn narrower; bubbles can widen the
            // measured extent a little, hence the smaller factors too)
            let base_w = compose(&cave.name, 1.0, 1.0, None).0.w as f64;
            let fit_w = text_w / (base_w - 4.0).max(1.0);
            for f in [0.9, 0.95, 1.0] {
                let sx = fit_w * f;
                if (sx - sy * ratio).abs() > 0.02 * sy * ratio {
                    v.push(sx);
                }
            }
        }
        v
    };
    let best_of = |cave: &Cave, sys: &[f64], ratios: &[f64]| -> Option<Fit> {
        let mut best: Option<Fit> = None;
        for &sy in sys {
            for &r in ratios {
                for sx in sx_options(cave, sy, r) {
                    if let Some(f) = score_at(cave, sx, sy) {
                        if best.is_none_or(|b| f.0 > b.0) {
                            best = Some(f);
                        }
                    }
                }
            }
        }
        best
    };
    let mut coarse: Vec<(Fit, &Cave)> = caves
        .par_iter()
        .filter_map(|cave| best_of(cave, &[hint.sy], &[hint.ratio]).map(|b| (b, cave)))
        .collect();
    coarse.sort_by(|a, b| b.0 .0.partial_cmp(&a.0 .0).unwrap());
    let fine_sys: Vec<f64> = [0.98, 0.99, 1.0, 1.01, 1.02].iter().map(|f| hint.sy * f).collect();
    let fine_r: Vec<f64> = [0.97, 0.985, 1.0, 1.015, 1.03].iter().map(|f| hint.ratio * f).collect();
    let top: Vec<(Fit, &Cave)> = coarse[..coarse.len().min(2)]
        .par_iter()
        .map(|(b, cave)| match best_of(cave, &fine_sys, &fine_r) {
            Some(f) if f.0 > b.0 => (f, *cave),
            _ => (*b, *cave),
        })
        .collect();
    let mut results = top;
    results.extend(coarse.iter().skip(2).cloned());
    results.sort_by(|a, b| b.0 .0.partial_cmp(&a.0 .0).unwrap());
    finish(results, y0)
}

fn finish(results: Vec<(Fit, &Cave)>, y0: usize) -> Option<Calibration> {
    if results.is_empty() {
        return None;
    }
    let ((score, sx, sy, (lx, ly)), cave) = results[0].clone();
    let gsx = if cave.lang == "ja" { Some(sy) } else { None };
    let (_, pieces) = compose(&cave.name, sx, sy, gsx);
    let letters = pieces
        .into_iter()
        .map(|pc| LetterBox { index: pc.index, ch: pc.ch, x: (lx as i64 + pc.px) as f64, y: (y0 + ly) as f64, template: pc.g })
        .collect();
    let runner_up = results[1..]
        .iter()
        .find(|(_, c)| c.cavegen != cave.cavegen && !cave.name.contains(c.name.as_str()))
        .map(|(b, c)| (c.name.clone(), b.0));
    Some(Calibration { cave: cave.clone(), score, sx, sy, x: lx as i64, y: (y0 + ly) as i64, letters, runner_up, gsx })
}

/// calibrate.calibrate: the cave whose name best matches the settled screen, and every letter's box.
pub fn calibrate(settled: &Gray, caves: &[Cave]) -> Option<Calibration> {
    use rayon::prelude::*;
    let p = prep(settled, None);
    let (h, w) = (p.h, p.w);
    let y0 = (0.14 * h as f64) as usize;
    let y1 = (0.48 * h as f64) as usize;
    let region = p.rows(y0, y1);
    let (ex0, ex1, _ey0, _ey1) = bright_extent(&region, 0.35)?;
    let text_w = (ex1 - ex0 + 1) as f64;
    let sy0 = 0.99 * h as f64 / 480.0;
    let wide = if w as f64 / h as f64 > 1.55 { (w as f64 / h as f64) / (4.0 / 3.0) } else { 1.0 };
    let region = FftImage::new(region);

    let coarse_f = linspace(0.85, 1.1, 6);
    let mut coarse: Vec<(Fit, &Cave)> = caves
        .par_iter()
        .filter_map(|cave| best_fit(&region, cave, &[sy0], &coarse_f, &[0.8, 0.9, 1.0], sy0, wide, text_w).map(|b| (b, cave)))
        .collect();
    coarse.sort_by(|a, b| b.0 .0.partial_cmp(&a.0 .0).unwrap()); // stable, descending
    let fine_sys: Vec<f64> = linspace(0.92, 1.08, 9).iter().map(|f| sy0 * f).collect();
    let fine_f = linspace(0.85, 1.1, 11);
    let fine_e = linspace(0.8, 1.0, 5);
    let top: Vec<(Fit, &Cave)> = coarse[..coarse.len().min(2)]
        .par_iter()
        .map(|(b, cave)| {
            let fine = best_fit(&region, cave, &fine_sys, &fine_f, &fine_e, sy0, wide, text_w);
            let pick = match fine {
                Some(f) if f.0 > b.0 => f,
                _ => *b,
            };
            (pick, *cave)
        })
        .collect();
    let mut results: Vec<(Fit, &Cave)> = top;
    results.extend(coarse.iter().skip(2).cloned());
    results.sort_by(|a, b| b.0 .0.partial_cmp(&a.0 .0).unwrap());
    finish(results, y0)
}
