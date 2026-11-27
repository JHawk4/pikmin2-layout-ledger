//! Challenge Mode: the RNG state from the results-screen score roll (a port of p2seeds'
//! `challenge_results.py`, from the challenge-mode-seeds branch).
//!
//! After a challenge stage the results screen rolls four counters (pokos, Pikmin, time bonus,
//! total). Every game frame, for each counter in that order and each digit from the ones digit
//! up, a digit that is not locked yet shows `randInt(9) + 1` from the global RNG
//! (`TChallengeResultCounter::update`). Low digits lock first, one every `_1C` frames after the
//! counter's onyon arrives. A clean frame shows up to ~14 consecutive draws; following the roll
//! to its end pins the RNG position exactly.
//!
//! 1. Frames where much of the picture is the results screen's blue form a screen (`Screens`).
//! 2. The panel is registered against a reference (scale + shift, so 4:3 GC, 16:9 Wii / Wii U and
//!    any crop work) and warped to canonical coordinates; each counter's digit slots are read by
//!    template matching.
//! 3. An early frame's rolling digits are solved by lattice enumeration (each digit bounds the
//!    15-bit rand to a 1/9 interval) and confirmed by the next frames.
//! 4. A beam search over (RNG position, locked digits and lock timers per counter) follows the
//!    roll frame by frame to its end.
//!
//! **Switch** (Pikmin 2 HD) draws from musl's 64-bit LCG: a digit is `9 * (s >> 49) / 32768 + 1`,
//! and solving takes about 24 digits instead of 12 ([`decode_screen_with`], `Gen::Switch`).
//!
//! **Anchor.** With a known earlier RNG state (the previous screen's roll end, or one the runner
//! entered), a screen whose digits are too poor to solve is found by scanning the digit stream
//! after the anchor (up to [`ANCHOR_MAX_DRAWS`] draws; one stage of play is about 20k–120k), which
//! needs far fewer readable digits.

use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

use crate::img::{max_loc, match_direct, resize_area, FftImage, Gray, Img};
#[cfg(test)]
use crate::img::match_direct as _md;
use crate::lattice::box_points;
use crate::rng::{Gen, MASK32};

const M: u64 = 1 << 31;

pub const CANON_W: usize = 468;
pub const CANON_H: usize = 307;
const TW: usize = 22;
const TH: usize = 25;
const PAD_X: usize = 4;
const PAD_Y: usize = 3;

pub const COUNTERS: [&str; 4] = ["pokos", "pikmin", "time", "total"];
/// right-most digit centre x, y, digit pitch (canonical px), max digits
const GEOM: [(f64, f64, f64, usize); 4] = [(143.25, 162.0, 27.75, 5), (267.25, 162.0, 27.0, 4), (402.5, 162.0, 27.5, 5), (292.75, 108.5, 28.0, 5)];
const SQUEEZE: [f64; 5] = [1.0, 0.92, 0.85, 0.78, 0.72];

pub const MIN_DIGIT_SCORE: f64 = 0.55;
/// How far after an anchor a screen's roll is searched for (draws).
pub const ANCHOR_MAX_DRAWS: usize = 5_000_000;
pub const REG_MIN: f64 = 0.80;

// ------------------------------------------------------------------------------------------
// RNG digits

#[inline]
pub fn digit_of_state(s: u64) -> u8 {
    ((((s >> 16) & 0x7FFF) * 9) / 32768 + 1) as u8
}

/// The digit a draw shows on either generator.
#[inline]
pub fn digit_of_state_gen(g: Gen, s: u64) -> u8 {
    match g {
        Gen::Gc => digit_of_state(s),
        Gen::Switch => (((s >> 49) * 9) / 32768 + 1) as u8,
    }
}

/// Digits of the draws whose states are s0, next(s0), ... (n of them).
pub fn digit_stream(s0: u64, n: usize) -> Vec<u8> {
    digit_stream_gen(Gen::Gc, s0, n)
}

pub fn digit_stream_gen(g: Gen, s0: u64, n: usize) -> Vec<u8> {
    let mut out = Vec::with_capacity(n);
    let mut s = if g == Gen::Gc { s0 & MASK32 } else { s0 };
    for _ in 0..n {
        out.push(digit_of_state_gen(g, s));
        s = g.step(s);
    }
    out
}

/// Bits below the 15-bit value a digit reads (16 on GC, 49 on Switch) and the modulus that
/// matters (2^31, 2^64).
fn digit_geometry(g: Gen) -> (u32, i128) {
    match g {
        Gen::Gc => (16, M as i128),
        Gen::Switch => (49, 1i128 << 64),
    }
}

fn state_box(g: Gen, d: u8) -> (i128, i128) {
    let (lo_bits, _) = digit_geometry(g);
    let d = d as i128;
    let lo_r = ((d - 1) * 32768 + 8) / 9; // ceil((d-1)*32768/9)
    let hi_r = (d * 32768 + 8) / 9 - 1;
    (lo_r << lo_bits, (hi_r << lo_bits) | ((1i128 << lo_bits) - 1))
}

/// Digits a solve uses: about (log2 of the state space + 10) / 3.17 bits per digit.
fn solve_len(g: Gen) -> usize {
    match g {
        Gen::Gc => 12,
        Gen::Switch => 24,
    }
}

/// Lattice nodes a solve may visit (a 24-dimensional Switch box needs more).
fn solve_nodes(g: Gen) -> usize {
    match g {
        Gen::Gc => 100_000,
        Gen::Switch => 1_000_000,
    }
}

/// States s0 (mod 2^31) such that draw i (state next_seed(s0, i)) shows digit d for every (i, d)
/// in `obs`. None when the enumeration is too large (too few digits).
pub fn solve_digits(obs: &[(usize, u8)], max_nodes: usize) -> Option<Vec<u64>> {
    solve_digits_gen(Gen::Gc, obs, max_nodes)
}

/// solve_digits for either generator (Switch: full 64-bit states; about 24 digits needed).
pub fn solve_digits_gen(g: Gen, obs: &[(usize, u8)], max_nodes: usize) -> Option<Vec<u64>> {
    let mut obs = obs.to_vec();
    obs.sort();
    let i0 = obs[0].0;
    let (_, m) = digit_geometry(g);
    let mut lo = Vec::new();
    let mut hi = Vec::new();
    let mut a_row = Vec::new();
    for &(i, d) in &obs {
        let (a, c) = g.jump((i - i0) as i64);
        let (l, h) = state_box(g, d);
        a_row.push((a as i128).rem_euclid(m));
        lo.push(l - (c as i128).rem_euclid(m));
        hi.push(h - (c as i128).rem_euclid(m));
    }
    let (l0, h0) = state_box(g, obs[0].1);
    lo[0] = l0;
    hi[0] = h0;
    let n = obs.len();
    let mut gens = vec![a_row];
    for t in 1..n {
        gens.push((0..n).map(|j| if j == t { m } else { 0 }).collect());
    }
    let pts = box_points(&gens, &lo, &hi, max_nodes)?;
    let mut out: Vec<u64> = pts
        .iter()
        .map(|p| {
            let x = p[0].rem_euclid(m) as u64;
            g.next(x, -(i0 as i64)) & g.seed_mask()
        })
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();
    out.sort();
    Some(out)
}

// ------------------------------------------------------------------------------------------
// templates

macro_rules! digit_pngs {
    ($($name:literal),*) => { &[$( ($name, include_bytes!(concat!("../data/challenge_digits/", $name, ".png")) as &[u8]) ),*] };
}

const DIGIT_PNGS: &[(&str, &[u8])] = digit_pngs!(
    "d0_c_gc", "d0_c_wiiu", "d1_c_gc", "d1_c_wiiu", "d1_t_gc", "d1_t_wiiu", "d2_c_gc", "d2_c_wiiu", "d2_t_gc", "d2_t_wiiu", "d3_c_gc", "d3_c_wiiu", "d3_t_gc",
    "d3_t_wiiu", "d4_c_gc", "d4_c_wiiu", "d4_t_gc", "d4_t_wiiu", "d5_c_gc", "d5_c_wiiu", "d5_t_gc", "d5_t_wiiu", "d6_c_gc", "d6_c_wiiu", "d6_t_gc", "d6_t_wiiu",
    "d7_c_gc", "d7_c_wiiu", "d7_t_gc", "d7_t_wiiu", "d8_c_gc", "d8_c_wiiu", "d8_t_gc", "d8_t_wiiu", "d9_c_gc", "d9_c_wiiu", "d9_t_gc", "d9_t_wiiu"
);
const PANEL_PNG: &[u8] = include_bytes!("../data/challenge_digits/panel.png");

fn decode_gray(bytes: &[u8]) -> Img {
    let mut dec = png::Decoder::new(std::io::Cursor::new(bytes));
    dec.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut r = dec.read_info().expect("png");
    let mut buf = vec![0u8; r.output_buffer_size()];
    let info = r.next_frame(&mut buf).expect("png");
    let (w, h) = (info.width as usize, info.height as usize);
    let ch = info.color_type.samples();
    let mut im = Img::zeros(w, h);
    for i in 0..w * h {
        let p = &buf[i * ch..i * ch + ch];
        im.d[i] = if ch >= 3 {
            // cv2.IMREAD_GRAYSCALE of a colour PNG
            ((p[2] as f32) * 0.114 + (p[1] as f32) * 0.587 + (p[0] as f32) * 0.299).round()
        } else {
            p[0] as f32
        };
    }
    im
}

fn templates() -> &'static Vec<(u8, Img)> {
    static T: OnceLock<Vec<(u8, Img)>> = OnceLock::new();
    T.get_or_init(|| DIGIT_PNGS.iter().map(|(n, b)| (n.as_bytes()[1] - b'0', decode_gray(b))).collect())
}

fn panel_reference() -> &'static Img {
    static P: OnceLock<Img> = OnceLock::new();
    P.get_or_init(|| blur(&decode_gray(PANEL_PNG), 1.5))
}

// ------------------------------------------------------------------------------------------
// image helpers

/// cv2.GaussianBlur(img, (0, 0), sigma) on a float image (BORDER_REFLECT_101).
pub fn blur(im: &Img, sigma: f64) -> Img {
    let ks = ((sigma * 4.0 * 2.0 + 1.0).round() as usize) | 1;
    let r = ks / 2;
    let mut k: Vec<f64> = (0..ks).map(|i| (-((i as f64 - r as f64).powi(2)) / (2.0 * sigma * sigma)).exp()).collect();
    let s: f64 = k.iter().sum();
    k.iter_mut().for_each(|v| *v /= s);
    let refl = |i: i64, n: usize| -> usize {
        let n = n as i64;
        if n == 1 {
            return 0;
        }
        let mut i = i;
        while i < 0 || i >= n {
            if i < 0 {
                i = -i;
            }
            if i >= n {
                i = 2 * n - 2 - i;
            }
        }
        i as usize
    };
    let (w, h) = (im.w, im.h);
    let mut tmp = vec![0f32; w * h];
    for y in 0..h {
        for x in 0..w {
            let mut a = 0.0;
            for (j, kv) in k.iter().enumerate() {
                a += kv * im.d[y * w + refl(x as i64 + j as i64 - r as i64, w)] as f64;
            }
            tmp[y * w + x] = a as f32;
        }
    }
    let mut out = Img::zeros(w, h);
    for y in 0..h {
        for x in 0..w {
            let mut a = 0.0;
            for (j, kv) in k.iter().enumerate() {
                a += kv * tmp[refl(y as i64 + j as i64 - r as i64, h) * w + x] as f64;
            }
            out.d[y * w + x] = a as f32;
        }
    }
    out
}

fn to_img(g: &Gray) -> Img {
    let mut im = Img::zeros(g.w, g.h);
    for y in 0..g.h {
        for (x, &v) in g.row(y).iter().enumerate() {
            im.d[y * g.w + x] = v as f32;
        }
    }
    im
}

fn resize_to(im: &Img, w: usize, h: usize) -> Img {
    resize_area(im, w.max(1), h.max(1))
}

// ------------------------------------------------------------------------------------------
// registration

/// Where the canonical panel sits in a frame: video px per canonical px, and its top-left.
#[derive(Clone, Copy, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Placement {
    pub score: f64,
    pub sx: f64,
    pub sy: f64,
    pub x: f64,
    pub y: f64,
}

fn match_at(g: &Img, gfft: Option<&FftImage>, r: &Img, sx: f64, sy: f64, region: Option<(i64, i64, i64, i64)>) -> (f64, f64, f64) {
    let w = (r.w as f64 * sx).round() as usize;
    let h = (r.h as f64 * sy).round() as usize;
    if w < 8 || h < 8 {
        return (-1.0, 0.0, 0.0);
    }
    let t = resize_to(r, w, h);
    match region {
        None => {
            if g.w < w || g.h < h {
                return (-1.0, 0.0, 0.0);
            }
            let res = match gfft {
                Some(f) => f.match_t(&t),
                None => match_direct(g, &t),
            };
            let (mv, (x, y)) = max_loc(&res);
            (mv as f64, x as f64, y as f64)
        }
        Some((xa, ya, xb, yb)) => {
            let (xa, ya) = (xa.max(0) as usize, ya.max(0) as usize);
            let x1 = ((xb.max(0) as usize) + w).min(g.w);
            let y1 = ((yb.max(0) as usize) + h).min(g.h);
            if x1 <= xa || y1 <= ya || x1 - xa < w || y1 - ya < h {
                return (-1.0, 0.0, 0.0);
            }
            let sub = g.crop(xa, ya, x1, y1);
            let res = FftImage::new(sub).match_t(&t);
            let (mv, (x, y)) = max_loc(&res);
            (mv as f64, (xa + x) as f64, (ya + y) as f64)
        }
    }
}

/// Find the results panel in a gray frame (coarse search unless `hint`, then refine).
pub fn register(gray: &Gray, hint: Option<&Placement>) -> Placement {
    let r = panel_reference();
    let g = blur(&to_img(gray), 1.5);
    let (sx0, sy0, x0, y0, span, step) = match hint {
        None => {
            let gs = resize_to(&g, (g.w as f64 * 0.5).round() as usize, (g.h as f64 * 0.5).round() as usize);
            let rs = resize_to(r, (r.w as f64 * 0.5).round() as usize, (r.h as f64 * 0.5).round() as usize);
            use rayon::prelude::*;
            let gf = FftImage::new(gs.clone());
            let grid: Vec<(f64, f64)> = (0..44).flat_map(|a| (0..28).map(move |b| (0.5 + a as f64 * 0.025, 0.8 + b as f64 * 0.025))).collect();
            let found: Vec<(f64, f64, f64, f64, f64)> = grid
                .par_iter()
                .map(|&(sy, ar)| {
                    let sx = sy * ar;
                    let (mv, x, y) = match_at(&gs, Some(&gf), &rs, sx, sy, None);
                    (mv, sx, sy, x / 0.5, y / 0.5)
                })
                .collect();
            // the first best in the search order, as the sequential search finds it
            let mut best = (-1.0, 1.0, 1.0, 0.0, 0.0);
            for f in found {
                if f.0 > best.0 {
                    best = f;
                }
            }
            (best.1, best.2, best.3, best.4, 0.03, 0.006)
        }
        Some(p) => (p.sx, p.sy, p.x, p.y, 0.012, 0.006),
    };
    use rayon::prelude::*;
    let n = (2.0f64 * span / step + 1e-9).floor() as i64;
    let grid: Vec<(f64, f64)> = (0..=n).flat_map(|a| (0..=n).map(move |b| (sy0 - span + a as f64 * step, sx0 - span + b as f64 * step))).collect();
    let found: Vec<Placement> = grid
        .par_iter()
        .map(|&(sy, sx)| {
            let reg = (x0 as i64 - 8, y0 as i64 - 8, x0 as i64 + 8, y0 as i64 + 8);
            let (mv, x, y) = match_at(&g, None, r, sx, sy, Some(reg));
            let w = (r.w as f64 * sx).round();
            let h = (r.h as f64 * sy).round();
            Placement { score: mv, sx: w / r.w as f64, sy: h / r.h as f64, x, y }
        })
        .collect();
    let mut best = Placement { score: -1.0, sx: sx0, sy: sy0, x: x0, y: y0 };
    for p in found {
        if p.score > best.score {
            best = p;
        }
    }
    best
}

/// The panel warped to canonical coordinates (bilinear, zero outside).
pub fn rectify(gray: &Gray, pl: &Placement) -> Img {
    let mut out = Img::zeros(CANON_W, CANON_H);
    let (w, h) = (gray.w as f64, gray.h as f64);
    for yc in 0..CANON_H {
        let sy = pl.sy * yc as f64 + pl.y;
        for xc in 0..CANON_W {
            let sx = pl.sx * xc as f64 + pl.x;
            if sx < 0.0 || sy < 0.0 || sx > w - 1.0 || sy > h - 1.0 {
                continue;
            }
            let (x0, y0) = (sx.floor() as usize, sy.floor() as usize);
            let (fx, fy) = (sx - x0 as f64, sy - y0 as f64);
            let x1 = (x0 + 1).min(gray.w - 1);
            let y1 = (y0 + 1).min(gray.h - 1);
            let v = gray.at(x0, y0) as f64 * (1.0 - fx) * (1.0 - fy)
                + gray.at(x1, y0) as f64 * fx * (1.0 - fy)
                + gray.at(x0, y1) as f64 * (1.0 - fx) * fy
                + gray.at(x1, y1) as f64 * fx * fy;
            out.d[yc * CANON_W + xc] = v as f32;
        }
    }
    out
}

// ------------------------------------------------------------------------------------------
// digit reading

fn slot_crop(canon: &Img, ci: usize, i: usize, squeeze: f64) -> Img {
    let (gx, gy, pitch, _) = GEOM[ci];
    let cx = gx - i as f64 * pitch * squeeze;
    let cy = gy;
    let hw = (TW as f64 / 2.0 + PAD_X as f64) * squeeze;
    let x0 = (cx - hw).round() as i64;
    let x1 = (cx + hw).round() as i64;
    let y0 = (cy - TH as f64 / 2.0 - PAD_Y as f64).round() as i64;
    let y1 = (cy + TH as f64 / 2.0 + PAD_Y as f64).round() as i64;
    let (cw, ch) = ((x1 - x0).max(1) as usize, (y1 - y0).max(1) as usize);
    let mut crop = Img::zeros(cw, ch);
    for y in 0..ch {
        let yy = (y0 + y as i64).clamp(0, canon.h as i64 - 1) as usize;
        for x in 0..cw {
            // copyMakeBorder(REPLICATE) for columns outside the panel
            let xx = (x0 + x as i64).clamp(0, canon.w as i64 - 1) as usize;
            crop.d[y * cw + x] = canon.d[yy * canon.w + xx];
        }
    }
    resize_to(&crop, TW + 2 * PAD_X, TH + 2 * PAD_Y)
}

/// The digit templates as zero-mean unit vectors (TM_CCOEFF_NORMED then needs only a dot product
/// with each window, divided by the window's own norm).
fn unit_templates() -> &'static Vec<(u8, Vec<f32>)> {
    static U: OnceLock<Vec<(u8, Vec<f32>)>> = OnceLock::new();
    U.get_or_init(|| {
        templates()
            .iter()
            .map(|(d, t)| {
                assert_eq!((t.w, t.h), (TW, TH));
                let m = t.d.iter().map(|&v| v as f64).sum::<f64>() / t.d.len() as f64;
                let n = t.d.iter().map(|&v| (v as f64 - m).powi(2)).sum::<f64>().sqrt().max(1e-9);
                (*d, t.d.iter().map(|&v| ((v as f64 - m) / n) as f32).collect())
            })
            .collect()
    })
}

/// Best TM_CCOEFF_NORMED of each digit 0-9 over the windows of a padded slot crop.
fn slot_scores(crop: &Img) -> [f64; 10] {
    let (cw, ch) = (crop.w, crop.h);
    let (rw, rh) = (cw + 1 - TW, ch + 1 - TH);
    let n = (TW * TH) as f64;
    // window norms (of the mean-subtracted window)
    let mut norms = vec![0f64; rw * rh];
    for y in 0..rh {
        for x in 0..rw {
            let (mut s, mut s2) = (0f64, 0f64);
            for yy in 0..TH {
                for &v in &crop.d[(y + yy) * cw + x..(y + yy) * cw + x + TW] {
                    s += v as f64;
                    s2 += (v as f64) * (v as f64);
                }
            }
            norms[y * rw + x] = (s2 - s * s / n).max(0.0).sqrt();
        }
    }
    let mut best = [-1.0f64; 10];
    for (d, t) in unit_templates() {
        let mut bd = f64::NEG_INFINITY;
        for y in 0..rh {
            for x in 0..rw {
                let nw = norms[y * rw + x];
                let v = if nw < 1e-6 {
                    0.0
                } else {
                    let mut acc = 0f32;
                    for yy in 0..TH {
                        let row = &crop.d[(y + yy) * cw + x..(y + yy) * cw + x + TW];
                        let tr = &t[yy * TW..(yy + 1) * TW];
                        acc += row.iter().zip(tr).map(|(a, b)| a * b).sum::<f32>();
                    }
                    acc as f64 / nw
                };
                if v > bd {
                    bd = v;
                }
            }
        }
        if bd > best[*d as usize] {
            best[*d as usize] = bd;
        }
    }
    best
}

/// (best digit, its score, best score of any other digit) for each slot.
fn read_slots(canon: &Img, slots: &[(usize, usize, f64)]) -> Vec<(u8, f64, f64)> {
    slots
        .iter()
        .map(|&(ci, i, sq)| {
            let crop = slot_crop(canon, ci, i, sq);
            let best = slot_scores(&crop);
            let mut order: Vec<usize> = (0..10).collect();
            order.sort_by(|a, b| best[*b].partial_cmp(&best[*a]).unwrap());
            (order[0] as u8, best[order[0]], best[order[1]])
        })
        .collect()
}

#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct DigitLayout {
    pub n: [usize; 4],
    pub squeeze: [f64; 4],
}

fn choose_layout(canons: &[&Img]) -> DigitLayout {
    use rayon::prelude::*;
    // every counter's slot scores at every squeeze, in parallel
    let combos: Vec<(usize, usize)> = (0..4).flat_map(|ci| (0..SQUEEZE.len()).map(move |q| (ci, q))).collect();
    let scores: Vec<Vec<f64>> = combos
        .par_iter()
        .map(|&(ci, q)| {
            let maxn = GEOM[ci].3;
            let slots: Vec<(usize, usize, f64)> = (0..maxn).map(|i| (ci, i, SQUEEZE[q])).collect();
            let mut sc = vec![0.0; maxn];
            for cv in canons {
                for (j, r) in read_slots(cv, &slots).iter().enumerate() {
                    sc[j] += r.1 - 0.5;
                }
            }
            sc
        })
        .collect();
    let mut n_out = [0; 4];
    let mut sq_out = [1.0; 4];
    for ci in 0..4 {
        let maxn = GEOM[ci].3;
        let mut best: Option<(f64, usize, f64)> = None;
        for (q, &sq) in SQUEEZE.iter().enumerate() {
            let sc = &scores[ci * SQUEEZE.len() + q];
            let mut cum = 0.0;
            for n in 1..=maxn {
                cum += sc[n - 1];
                if sq < 1.0 && n < 4 {
                    continue;
                }
                let val = cum / canons.len() as f64;
                if best.is_none_or(|b| val > b.0 + 1e-9) {
                    best = Some((val, n, sq));
                }
            }
        }
        let b = best.unwrap();
        n_out[ci] = b.1;
        sq_out[ci] = b.2;
    }
    DigitLayout { n: n_out, squeeze: sq_out }
}

/// Per counter, (digit, score, margin) from the ones digit up.
type Reading = [Vec<(u8, f64, f64)>; 4];

fn read_frame(canon: &Img, lay: &DigitLayout) -> Reading {
    let slots: Vec<(usize, usize, f64)> = (0..4).flat_map(|ci| (0..lay.n[ci]).map(move |i| (ci, i, lay.squeeze[ci]))).collect();
    let res = read_slots(canon, &slots);
    let mut out: Reading = Default::default();
    for ((ci, _, _), (d, v, v2)) in slots.iter().zip(res) {
        out[*ci].push((d, v, v - v2));
    }
    out
}

// ------------------------------------------------------------------------------------------
// roll tracking

const MATCH: f64 = 2.1972245773362196; // ln 9
const MISMATCH: f64 = -3.5;
const LOCK_OK: f64 = 0.6;
const SKIP: f64 = -4.0;
const SKIP_AFTER_REPEAT: f64 = -0.5;
const EXTRA: f64 = -4.0;
const REPEAT: f64 = -2.0;
const L_DISAGREE: f64 = -3.0;
const MAX_STREAM: usize = 6000;

#[derive(Clone)]
struct RFrame {
    index: usize,
    reading: Reading,
    dup: bool,
}

type K = [u8; 4];
type T = [i16; 4];
type L = [Option<i16>; 4];

fn ndraws(k: &K, ncs: &[usize; 4]) -> usize {
    (0..4).map(|i| ncs[i].saturating_sub(k[i] as usize)).sum()
}

fn emission(fr: &RFrame, k: &K, fin: &[bool; 4], p: usize, stream: &[u8], ncs: &[usize; 4], finals: &[Vec<Option<u8>>; 4]) -> (f64, u32, u32) {
    let (mut score, mut good, mut bad) = (0.0, 0u32, 0u32);
    let mut off = p;
    for ci in 0..4 {
        let n = ncs[ci];
        let kc = k[ci] as usize;
        for j in 0..n {
            let (d, v, _) = fr.reading[ci][j];
            if v < MIN_DIGIT_SCORE {
                continue;
            }
            if fin[ci] && j >= kc {
                continue;
            }
            if j < kc || kc >= n {
                let Some(f) = finals[ci].get(j).copied().flatten() else { continue };
                if d == f {
                    score += LOCK_OK;
                } else {
                    score += MISMATCH;
                    bad += 1;
                }
            } else {
                let q = off + (j - kc);
                if q >= stream.len() {
                    return (-1e9, 0, 0);
                }
                if d == stream[q] {
                    score += MATCH;
                    good += 1;
                } else {
                    score += MISMATCH;
                    bad += 1;
                }
            }
        }
        if kc < n {
            off += n - kc;
        }
    }
    (score, good, bad)
}

fn counter_moves(k: u8, t: i16, l: Option<i16>, n: usize) -> Vec<(u8, i16, Option<i16>)> {
    if k as usize >= n {
        return vec![(0, t, l)];
    }
    let t1 = t + 1;
    if k == 0 || t < 0 {
        return vec![(0, 0, l), (1, 0, l)];
    }
    match l {
        None => vec![(0, t1, None), (1, 0, Some(t1))],
        Some(lv) => {
            if t1 >= lv {
                vec![(1, 0, l)]
            } else {
                vec![(0, t1, l)]
            }
        }
    }
}

/// [(k after, t after, L after, penalty, finishing)] for one drawn frame.
fn transitions(k: &K, t: &T, l: &L, ncs: &[usize; 4]) -> Vec<(K, T, L, f64, [bool; 4])> {
    let opts: Vec<Vec<(u8, i16, Option<i16>)>> = (0..4).map(|i| counter_moves(k[i], t[i], l[i], ncs[i])).collect();
    let mut combos: Vec<([u8; 4], T, L)> = vec![([0; 4], [0; 4], [None; 4])];
    for (i, o) in opts.iter().enumerate() {
        let mut next = Vec::with_capacity(combos.len() * o.len());
        for (d, tt, ll) in &combos {
            for m in o {
                let (mut d2, mut t2, mut l2) = (*d, *tt, *ll);
                d2[i] = m.0;
                t2[i] = m.1;
                l2[i] = m.2;
                next.push((d2, t2, l2));
            }
        }
        combos = next;
    }
    combos
        .into_iter()
        .map(|(d, tt, ll)| {
            let mut pen = 0.0;
            for i in 0..4 {
                if l[i].is_none() {
                    if let Some(li) = ll[i] {
                        if (0..4).any(|j| j != i && ll[j].is_some_and(|x| x != li)) {
                            pen += L_DISAGREE;
                        }
                    }
                }
            }
            let mut k2 = *k;
            let mut fin = [false; 4];
            for i in 0..4 {
                k2[i] += d[i];
                fin[i] = k[i] as usize + 1 == ncs[i] && d[i] == 1;
            }
            (k2, tt, ll, pen, fin)
        })
        .collect()
}

/// One step of a path: (frame list index, position, locked, finishing, matches, mismatches).
#[derive(Clone, Copy, Debug)]
struct Step {
    fi: usize,
    k: K,
    good: u32,
    bad: u32,
}

#[derive(Clone)]
struct Entry {
    score: f64,
    p: usize,
    k: K,
    t: T,
    l: L,
    rep: u8,
    path: Vec<Step>,
    last: Option<(usize, K, [bool; 4])>,
}

#[allow(clippy::too_many_arguments)]
fn track(g: Gen, frames: &[RFrame], start: usize, s0: u64, ncs: &[usize; 4], finals: &[Vec<Option<u8>>; 4], k0: K, beam: usize) -> Vec<Entry> {
    let stream = digit_stream_gen(g, s0, MAX_STREAM);
    let t_init: T = std::array::from_fn(|i| if 0 < k0[i] as usize && (k0[i] as usize) < ncs[i] { -1 } else { 0 });
    let mut entries = vec![Entry { score: 0.0, p: 0, k: k0, t: t_init, l: [None; 4], rep: 0, path: Vec::new(), last: None }];
    let mut emis_cache: HashMap<(usize, usize, K, [bool; 4]), (f64, u32, u32)> = HashMap::new();
    for fi in start..frames.len() {
        let fr = &frames[fi];
        let mut new: HashMap<(usize, K, T, L, u8), Entry> = HashMap::new();
        let mut put = |e: Entry| {
            let key = (e.p, e.k, e.t, e.l, e.rep);
            if new.get(&key).is_none_or(|o| o.score < e.score) {
                new.insert(key, e);
            }
        };
        for e in &entries {
            if fr.dup {
                let mut e2 = e.clone();
                e2.rep = (e.rep + 1).min(2);
                put(e2);
                continue;
            }
            if let Some((pp, kk, fin)) = e.last {
                let (_, _, b) = *emis_cache.entry((fi, pp, kk, fin)).or_insert_with(|| emission(fr, &kk, &fin, pp, &stream, ncs, finals));
                let mut e2 = e.clone();
                e2.score += REPEAT + MISMATCH * b as f64;
                e2.rep = (e.rep + 1).min(2);
                e2.path.push(Step { fi, k: kk, good: 0, bad: b });
                put(e2);
            }
            // (p, k, t, L, score, rep)
            let mut starts: Vec<(usize, K, T, L, f64, u8)> = vec![(e.p, e.k, e.t, e.l, e.score, e.rep)];
            if ndraws(&e.k, ncs) > 0 {
                let mut frontier = starts.clone();
                for depth in 0..2 {
                    let mut nxt = Vec::new();
                    for &(pp, kk, tk, lk, sc0, r) in &frontier {
                        let nd = ndraws(&kk, ncs);
                        if nd == 0 {
                            continue;
                        }
                        let sk = if r > 0 { SKIP_AFTER_REPEAT } else { SKIP };
                        let trs = transitions(&kk, &tk, &lk, ncs);
                        let take = if r > 0 && depth == 0 { trs.len() } else { 1 };
                        for (k2, tt, ll, pen, _) in trs.into_iter().take(take) {
                            nxt.push((pp + nd, k2, tt, ll, sc0 + sk + pen, r.saturating_sub(1)));
                        }
                    }
                    starts.extend(nxt.iter().cloned());
                    frontier = nxt;
                }
                let extra: Vec<_> = starts.iter().map(|&(pp, kk, tk, lk, b, r)| (pp + 1, kk, tk, lk, b + EXTRA, r)).collect();
                starts.extend(extra);
            }
            for (pp, kk, tk, lk, base, r) in starts {
                let nd = ndraws(&kk, ncs);
                for (k2, tt, ll, pen, fin) in transitions(&kk, &tk, &lk, ncs) {
                    let (em, g, b) = *emis_cache.entry((fi, pp, kk, fin)).or_insert_with(|| emission(fr, &kk, &fin, pp, &stream, ncs, finals));
                    let mut path = e.path.clone();
                    path.push(Step { fi, k: kk, good: g, bad: b });
                    put(Entry { score: base + em + pen, p: pp + nd, k: k2, t: tt, l: ll, rep: r, path, last: Some((pp, kk, fin)) });
                }
            }
        }
        let mut v: Vec<Entry> = new.into_values().collect();
        v.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap());
        v.truncate(beam);
        entries = v;
    }
    entries
}

fn rolling_obs(fr: &RFrame, k: &K, ncs: &[usize; 4]) -> Vec<(usize, u8)> {
    let mut out = Vec::new();
    let mut off = 0;
    for ci in 0..4 {
        let n = ncs[ci];
        for j in k[ci] as usize..n {
            let (d, v, _) = fr.reading[ci][j];
            if v >= MIN_DIGIT_SCORE {
                out.push((off + j - k[ci] as usize, d));
            }
        }
        off += n.saturating_sub(k[ci] as usize);
    }
    out
}

fn locked_at(frames: &[RFrame], idx: &[usize], ncs: &[usize; 4]) -> K {
    let mut k = [0u8; 4];
    for ci in 0..4 {
        let mut kc = 0;
        for j in 0..ncs[ci] {
            let mut counts = [0usize; 10];
            for &i in idx {
                counts[frames[i].reading[ci][j].0 as usize] += 1;
            }
            let top = *counts.iter().max().unwrap();
            if top as f64 >= 0.75 * idx.len() as f64 {
                kc += 1;
            } else {
                break;
            }
        }
        k[ci] = kc;
    }
    k
}

fn solve_robust(g: Gen, obs: &[(usize, u8)], leave_one_out: bool) -> Vec<u64> {
    let nfit = solve_len(g);
    let mut cands: Vec<u64> = Vec::new();
    let first: Vec<_> = obs.iter().take(nfit).cloned().collect();
    if let Some(sol) = solve_digits_gen(g, &first, solve_nodes(g)) {
        if sol.len() <= 50 {
            cands.extend(sol);
        }
    }
    // (Switch: a 24-digit solve takes about 0.2 s, so 25 retries are too slow; a misread is left
    // to the next window instead)
    if cands.is_empty() && leave_one_out && g == Gen::Gc {
        let head: Vec<_> = obs.iter().take(nfit + 1).cloned().collect();
        for drop in 0..head.len().min(nfit + 1) {
            let sub: Vec<_> = head.iter().enumerate().filter(|(t, _)| *t != drop).map(|(_, o)| *o).take(nfit).collect();
            if let Some(sol) = solve_digits_gen(g, &sub, solve_nodes(g)) {
                if sol.len() <= 50 {
                    cands.extend(sol);
                }
            }
        }
    }
    let mut out: Vec<(usize, u64)> = Vec::new();
    let uniq: HashSet<u64> = cands.into_iter().collect();
    for s0 in uniq {
        let st = digit_stream_gen(g, s0, obs.last().unwrap().0 + 1);
        let bad = obs.iter().filter(|(i, d)| st[*i] != *d).count();
        if bad <= 1 {
            out.push((bad, s0));
        }
    }
    out.sort();
    out.into_iter().map(|x| x.1).collect()
}

#[allow(clippy::too_many_arguments)]
fn confirm(g: Gen, frames: &[RFrame], fi: usize, s0: u64, ncs: &[usize; 4], k0: &K, p_last: usize, n: usize) -> bool {
    let stream = digit_stream_gen(g, s0, p_last + n * 14 + 64);
    let mut ok = 0;
    let mut p = p_last + n;
    for fr in frames.iter().skip(fi + 1).take(8) {
        if fr.dup {
            continue;
        }
        let obs = rolling_obs(fr, k0, ncs);
        if obs.len() < 4.min(n) {
            return false;
        }
        let mut hit = None;
        for q in [p as i64, (p + n) as i64, p as i64 - n as i64] {
            if q < 0 {
                continue;
            }
            let q = q as usize;
            let bad = obs.iter().filter(|(i, d)| stream.get(q + i).is_none_or(|s| s != d)).count();
            let pass = if obs.len() >= 6 { bad <= 1.max(obs.len() / 6) } else { bad == 0 };
            if pass {
                hit = Some(q);
                break;
            }
        }
        let Some(h) = hit else {
            return ok >= 1 && n < 6;
        };
        if h + n == p {
            continue;
        }
        ok += 1;
        p = h + n;
        if ok >= 2 {
            return true;
        }
    }
    ok >= 1
}

fn find_anchor(g: Gen, frames: &[RFrame], ncs: &[usize; 4]) -> Option<(usize, u64, K)> {
    // digits for a solve: 11+ on GC (12 used), 24 on Switch
    let (need, min_obs) = match g {
        Gen::Gc => (11usize, 9usize),
        Gen::Switch => (24, 22),
    };
    let nondup: Vec<usize> = (0..frames.len()).filter(|&i| !frames[i].dup).collect();
    let mut tried = 0;
    for pos in 0..nondup.len() {
        let window: Vec<usize> = nondup[pos..(pos + 6).min(nondup.len())].to_vec();
        if window.len() < 3 {
            break;
        }
        let k0 = locked_at(frames, &window, ncs);
        let n = ndraws(&k0, ncs);
        if n == 0 {
            continue;
        }
        let m = 1.max(need.div_ceil(n));
        if m > window.len() - 1 {
            continue;
        }
        let mut obs = Vec::new();
        for q in 0..m {
            obs.extend(rolling_obs(&frames[window[q]], &k0, ncs).into_iter().map(|(i, d)| (q * n + i, d)));
        }
        if obs.len() < min_obs {
            continue;
        }
        tried += 1;
        if tried > 12 {
            break;
        }
        for s0 in solve_robust(g, &obs, tried <= 3) {
            if confirm(g, frames, window[m - 1], s0, ncs, &k0, (m - 1) * n, n) {
                return Some((nondup[pos], s0, k0));
            }
        }
    }
    None
}

/// Like find_anchor, but the state is looked up in the digit stream after a known earlier state
/// `anchor` (up to ANCHOR_MAX_DRAWS draws) instead of solved, so poorly read digits do: a frame's
/// digits only need to agree mostly (a rolling digit matches by chance 1 time in 9), and the
/// following frames, each 1-3 frames of draws later, must agree too. Returns (frame, state of its
/// first draw, locked digits, draws from the anchor).
fn find_from_anchor(g: Gen, frames: &[RFrame], ncs: &[usize; 4], anchor: u64) -> Option<(usize, u64, K, u64)> {
    let stream = digit_stream_gen(g, g.step(anchor), ANCHOR_MAX_DRAWS + 4096);
    let dbg = std::env::var("P2LIVE_DEBUG_ANCHOR").is_ok();
    let nondup: Vec<usize> = (0..frames.len()).filter(|&i| !frames[i].dup).collect();
    let mut tried = 0;
    for pos in 0..nondup.len() {
        let window: Vec<usize> = nondup[pos..(pos + 6).min(nondup.len())].to_vec();
        if window.len() < 3 {
            break;
        }
        let k0 = locked_at(frames, &window, ncs);
        let n = ndraws(&k0, ncs);
        if n < 8 {
            continue;
        }
        let obs = rolling_obs(&frames[nondup[pos]], &k0, ncs);
        if obs.len() < 8 {
            continue;
        }
        tried += 1;
        if tried > 20 {
            break;
        }
        // the next frames with the same digits rolling, to check a candidate against
        let follow: Vec<Vec<(usize, u8)>> = nondup[pos + 1..].iter().take(10).map(|&f| rolling_obs(&frames[f], &k0, ncs)).take_while(|o| o.len() >= 6).collect();
        if follow.len() < 4 {
            continue;
        }
        // stage 1: at least 60% of this frame's digits (chance: about 1 in 30,000 positions)
        let need = (obs.len() * 6).div_ceil(10);
        let max_bad = obs.len() - need;
        let mut best: Option<(f64, usize)> = None;
        for p in 0..ANCHOR_MAX_DRAWS {
            let mut bad = 0;
            for &(i, d) in &obs {
                if stream[p + i] != d {
                    bad += 1;
                    if bad > max_bad {
                        break;
                    }
                }
            }
            if bad > max_bad {
                continue;
            }
            // stage 2: follow the next frames (each 1-3 frames of draws on), keeping the best fit
            let (mut q, mut ok, mut tot) = (p, obs.len() - bad, obs.len());
            for o in &follow {
                let mut bf = (0usize, q + n);
                for step in 1..=3 {
                    let qq = q + step * n;
                    if qq + n + 64 >= stream.len() {
                        break;
                    }
                    let m = o.iter().filter(|&&(i, d)| stream[qq + i] == d).count();
                    if m > bf.0 {
                        bf = (m, qq);
                    }
                }
                ok += bf.0;
                tot += o.len();
                q = bf.1;
            }
            let rate = ok as f64 / tot as f64;
            if best.is_none_or(|b| rate > b.0) {
                best = Some((rate, p));
            }
        }
        if dbg {
            eprintln!("    anchor window at frame {}: {} digits, k {:?}, best {:?}", frames[nondup[pos]].index, obs.len(), k0, best);
        }
        // the true position agrees on most digits; chance agreement is about 1 in 9 (a little
        // more, as each following frame picks the best of three)
        if let Some((rate, p)) = best {
            if rate >= 0.5 {
                let s0 = g.next(anchor, p as i64 + 1);
                return Some((nondup[pos], s0, k0, p as u64 + 1));
            }
        }
    }
    None
}

// ------------------------------------------------------------------------------------------
// one screen

/// What a results screen's roll gives.
#[derive(Clone, Debug, serde::Serialize)]
pub struct RollResult {
    pub first_frame: usize,
    pub last_frame: usize,
    pub placement: Placement,
    pub layout: DigitLayout,
    pub final_display: String,
    pub decoded: bool,
    /// the frame whose first draw is `first_roll_state`
    pub first_roll_frame: Option<usize>,
    pub first_roll_state: Option<String>,
    /// the same state as a number (a later screen's anchor when the end is not known)
    pub first_state: Option<u64>,
    /// the state of the roll's last draw (the global RNG after the roll), and its frame
    pub end_state: Option<u64>,
    pub end_frame: Option<usize>,
    pub roll_complete: bool,
    /// the end extrapolated from the lock timers when the roll was cut off
    pub extrapolated: bool,
    pub digits_matched: u32,
    pub digits_mismatched: u32,
    pub end_margin: Option<f64>,
    /// draws from the anchor to the roll's first decoded draw, when within ANCHOR_MAX_DRAWS
    pub from_anchor: Option<u64>,
    /// the screen was found by the search after the anchor (its digits were too poor to solve)
    pub found_by_anchor: bool,
    pub note: String,
}

/// Frames of one results screen: (capture index, gray picture of the game). GC, no anchor.
pub fn decode_screen(frames_in: &[(usize, Gray)], placement_hint: Option<&Placement>) -> Option<RollResult> {
    decode_screen_with(frames_in, placement_hint, Gen::Gc, None)
}

/// decode_screen for either generator, with an optional anchor: a known RNG state before this
/// screen (the previous roll's end, or one the runner entered).
pub fn decode_screen_with(frames_in: &[(usize, Gray)], placement_hint: Option<&Placement>, g: Gen, anchor: Option<u64>) -> Option<RollResult> {
    if frames_in.len() < 15 {
        return None;
    }
    let dbg = std::env::var("P2LIVE_DEBUG").is_ok();
    let t0 = std::time::Instant::now();
    let lap = |what: &str| {
        if dbg {
            eprintln!("    {what}: {:.2} s", t0.elapsed().as_secs_f64());
        }
    };
    let mid = &frames_in[frames_in.len() / 2].1;
    let mut pl = placement_hint.map(|h| register(mid, Some(h))).filter(|p| p.score >= REG_MIN);
    if pl.is_none() {
        let p = register(mid, None);
        if p.score < REG_MIN {
            if dbg {
                eprintln!("    registration failed: {p:?}");
            }
            return None;
        }
        pl = Some(p);
    }
    let pl = pl.unwrap();
    lap("register");
    let canons: Vec<Img> = {
        use rayon::prelude::*;
        frames_in.par_iter().map(|(_, g)| rectify(g, &pl)).collect()
    };
    let mut frames: Vec<RFrame> = Vec::with_capacity(canons.len());
    for (i, (idx, _)) in frames_in.iter().enumerate() {
        let dup = i > 0 && is_dup(&canons[i], &canons[i - 1]);
        frames.push(RFrame { index: *idx, reading: Default::default(), dup });
    }
    // layout from frames spread over the first half (all digits present)
    let half = 3.max(canons.len() / 2).min(canons.len());
    let step = 1.max(half / 8);
    let picks: Vec<&Img> = canons[..half].iter().step_by(step).take(8).collect();
    lap("rectify");
    let lay = choose_layout(&picks);
    lap("layout");
    {
        use rayon::prelude::*;
        let readings: Vec<Reading> = canons.par_iter().map(|cv| read_frame(cv, &lay)).collect();
        for (f, r) in frames.iter_mut().zip(readings) {
            f.reading = r;
        }
    }
    lap("read");
    let ncs = lay.n;
    // final values: majority over the last frames
    let tail = &frames[frames.len().saturating_sub(25)..];
    let finals: [Vec<Option<u8>>; 4] = std::array::from_fn(|ci| {
        (0..ncs[ci])
            .map(|j| {
                let mut counts = [0usize; 10];
                let mut any = false;
                for fr in tail {
                    let (d, v, _) = fr.reading[ci][j];
                    if v >= MIN_DIGIT_SCORE {
                        counts[d as usize] += 1;
                        any = true;
                    }
                }
                // ties go to the value seen first, as Python's max(set(...)) roughly does
                any.then(|| (0..10).max_by_key(|&d| (counts[d], std::cmp::Reverse(d))).unwrap() as u8)
            })
            .collect()
    });
    let final_display = (0..4)
        .map(|ci| finals[ci].iter().rev().map(|d| d.map(|x| char::from(b'0' + x)).unwrap_or('?')).collect::<String>())
        .collect::<Vec<_>>()
        .join(" ");
    let mut res = RollResult {
        first_frame: frames_in[0].0,
        last_frame: frames_in.last().unwrap().0,
        placement: pl,
        layout: lay.clone(),
        final_display,
        decoded: false,
        first_roll_frame: None,
        first_roll_state: None,
        first_state: None,
        end_state: None,
        end_frame: None,
        roll_complete: false,
        extrapolated: false,
        digits_matched: 0,
        digits_mismatched: 0,
        end_margin: None,
        from_anchor: None,
        found_by_anchor: false,
        note: String::new(),
    };
    let found = match find_anchor(g, &frames, &ncs) {
        Some(f) => Some(f),
        None => match anchor.and_then(|a| find_from_anchor(g, &frames, &ncs, a)) {
            Some((fi, s0, k0, _)) => {
                res.found_by_anchor = true;
                Some((fi, s0, k0))
            }
            None => None,
        },
    };
    let Some((fi, s0, k0)) = found else {
        res.note = if anchor.is_some() {
            format!("no frame solved to a state confirmed by the next frames, nor found within {ANCHOR_MAX_DRAWS} draws after the anchor")
        } else {
            "no frame solved to a state confirmed by the next frames".into()
        };
        return Some(res);
    };
    lap("anchor");
    // a screen found from the anchor has poorly read digits: a wider beam keeps the roll through
    // the locks (on cmal09, 32 loses it; 128 and 512 agree)
    let beam = if res.found_by_anchor { 128 } else { 32 };
    let entries = track(g, &frames, fi, s0, &ncs, &finals, k0, beam);
    lap("track");
    let best = &entries[0];
    if std::env::var("P2LIVE_DEBUG_ANCHOR").is_ok() {
        let line: Vec<String> = best.path.iter().map(|st| format!("{}:{:?}:{}/{}", frames[st.fi].index, st.k, st.good, st.bad)).collect();
        eprintln!("    path {}", line.join(" "));
    }
    let last_draw_end = best.p;
    res.end_margin = entries.iter().skip(1).find(|e| e.p != last_draw_end).map(|e| ((best.score - e.score) * 10.0).round() / 10.0);
    for st in &best.path {
        res.digits_matched += st.good;
        res.digits_mismatched += st.bad;
    }
    // the frame of the last draw
    res.end_frame = best.path.iter().rev().find(|st| ndraws(&st.k, &ncs) > 0).map(|st| frames[st.fi].index);
    // extend backwards with every digit rolling
    let n0 = ndraws(&k0, &ncs);
    let (mut first_idx, mut pos) = (fi, 0i64);
    let mut j = fi as i64 - 1;
    while j >= 0 {
        let fr = &frames[j as usize];
        j -= 1;
        if fr.dup {
            continue;
        }
        let obs = rolling_obs(fr, &k0, &ncs);
        let st = digit_stream_gen(g, g.next(s0, pos - n0 as i64), n0);
        let bad = obs.iter().filter(|(i, d)| st.get(*i).is_none_or(|s| s != d)).count();
        if obs.len() >= 6 && bad <= 1.max(obs.len() / 6) {
            pos -= n0 as i64;
            first_idx = (j + 1) as usize;
        } else {
            break;
        }
    }
    res.first_roll_frame = Some(frames[first_idx].index);
    let first_state = g.next(s0, pos) & g.seed_mask();
    res.first_roll_state = Some(format!("0x{}", g.hex(first_state)));
    res.first_state = Some(first_state);
    let mut anchor_note = None;
    if let Some(a) = anchor {
        let d = g.distance(a, first_state);
        if d >= 1 && d <= ANCHOR_MAX_DRAWS as u64 {
            res.from_anchor = Some(d);
        } else {
            anchor_note = Some(format!("not within {ANCHOR_MAX_DRAWS} draws after the anchor"));
        }
    }
    let mut end = last_draw_end;
    if ndraws(&best.k, &ncs) > 0 {
        // cut off before the end: finish with the lock timers when they are known
        let known: Vec<i16> = best.l.iter().flatten().cloned().collect();
        if (0..4).all(|i| best.k[i] >= 1 || best.k[i] as usize >= ncs[i]) && !known.is_empty() {
            let mode = *known.iter().max_by_key(|x| known.iter().filter(|y| y == x).count()).unwrap();
            let lc: Vec<i16> = (0..4).map(|i| best.l[i].unwrap_or(mode)).collect();
            let (mut k, mut t, mut px) = (best.k, best.t, last_draw_end);
            while ndraws(&k, &ncs) > 0 {
                px += ndraws(&k, &ncs);
                for i in 0..4 {
                    if (k[i] as usize) < ncs[i] {
                        t[i] += 1;
                        if t[i] >= lc[i] {
                            k[i] += 1;
                            t[i] = 0;
                        }
                    }
                }
            }
            end = px;
            res.extrapolated = true;
        }
        res.roll_complete = false;
    } else {
        res.roll_complete = true;
    }
    res.decoded = res.roll_complete || res.extrapolated;
    // a screen found from the anchor has poor digits: its end counts only when most digits agree
    // along the roll and no other end comes close (its start is exact either way)
    let untrusted = res.found_by_anchor && (res.digits_matched < res.digits_mismatched || res.end_margin.is_some_and(|m| m < 3.0));
    if untrusted {
        res.decoded = false;
    }
    res.end_state = res.decoded.then(|| g.next(s0, end as i64 - 1) & g.seed_mask());
    let mut notes = Vec::new();
    if res.found_by_anchor {
        notes.push(format!("found {} draws after the anchor", res.from_anchor.unwrap_or(0)));
    }
    notes.extend(anchor_note);
    if res.digits_mismatched as f64 > 0.05 * res.digits_matched.max(1) as f64 {
        notes.push(format!("{} digit mismatches vs {} matches", res.digits_mismatched, res.digits_matched));
    }
    if res.end_margin.is_some_and(|m| m < 3.0) {
        notes.push(format!("roll end ambiguous (another end scores within {:.1})", res.end_margin.unwrap()));
    }
    if untrusted {
        notes.push("start found from the anchor, but the roll's end could not be followed on these digits".into());
    } else if !res.roll_complete {
        notes.push(if res.extrapolated { "roll cut off; end extrapolated from the lock timers".into() } else { "roll cut off before its end; end unknown".into() });
    }
    res.note = if notes.is_empty() { "ok".into() } else { notes.join("; ") };
    Some(res)
}

/// Same picture (the capture repeated a frame): no 6x6-px block of the panel changed.
fn is_dup(a: &Img, b: &Img) -> bool {
    let mut d = Img::zeros(a.w, a.h);
    for i in 0..a.d.len() {
        d.d[i] = (a.d[i] - b.d[i]).abs();
    }
    let s = resize_to(&d, a.w / 6, a.h / 6);
    s.d.iter().cloned().fold(0.0f32, f32::max) < 15.0
}

/// Share of a small RGB picture that is the results screen's blue.
pub fn blue_fraction(rgb: &[u8], w: usize, h: usize) -> f64 {
    let n = w * h;
    let mut c = 0;
    for i in 0..n {
        let (r, b) = (rgb[i * 3] as i32, rgb[i * 3 + 2] as i32);
        if b - r > 35 && b > 140 {
            c += 1;
        }
    }
    c as f64 / n.max(1) as f64
}

/// Groups frames into results screens as they arrive (`iter_screens`): a screen starts on a
/// frame that is at least `BLUE_MIN` blue, and ends `GAP` non-blue frames later (or at `MAX_LEN`).
pub struct Screens {
    buf: Vec<(usize, Gray)>,
    trailing: usize,
}

pub const BLUE_MIN: f64 = 0.25;
const GAP: usize = 20;
const MAX_LEN: usize = 900;

impl Default for Screens {
    fn default() -> Self {
        Self::new()
    }
}

impl Screens {
    pub fn new() -> Self {
        Screens { buf: Vec::new(), trailing: 0 }
    }
    pub fn active(&self) -> bool {
        !self.buf.is_empty()
    }
    /// Feed one frame with its blue share; returns a finished screen's frames.
    pub fn push(&mut self, index: usize, blue: f64, gray: impl FnOnce() -> Gray) -> Option<Vec<(usize, Gray)>> {
        let active = self.active();
        if blue >= BLUE_MIN {
            self.trailing = 0;
            self.buf.push((index, gray()));
        } else if active {
            self.trailing += 1;
            self.buf.push((index, gray()));
        } else {
            return None;
        }
        if self.trailing > GAP || self.buf.len() >= MAX_LEN {
            let mut b = std::mem::take(&mut self.buf);
            b.truncate(b.len() - self.trailing);
            self.trailing = 0;
            return Some(b);
        }
        None
    }
    /// The screen so far (the roll may be over before the screen ends).
    pub fn so_far(&self) -> &[(usize, Gray)] {
        &self.buf[..self.buf.len() - self.trailing]
    }
    pub fn finish(&mut self) -> Option<Vec<(usize, Gray)>> {
        if self.buf.is_empty() {
            return None;
        }
        let mut b = std::mem::take(&mut self.buf);
        b.truncate(b.len() - self.trailing);
        self.trailing = 0;
        Some(b)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn solves_known_digits() {
        // 2P GC frame 6590 of the challenge write-up, listed in draw order: 5817 187 562 6228
        // -> 0x423CDA79
        let drawn = ["5817", "187", "562", "6228"];
        let mut obs = Vec::new();
        for s in drawn {
            for c in s.chars() {
                obs.push((obs.len(), c.to_digit(10).unwrap() as u8));
            }
        }
        let sol = solve_robust(Gen::Gc, &obs, true);
        assert!(sol.contains(&0x423CDA79), "{sol:X?}");
    }

    #[test]
    fn slot_scores_match_template_matching() {
        // the dot-product scorer equals TM_CCOEFF_NORMED via match_direct
        let (_, t) = &templates()[7];
        let mut crop = Img::zeros(TW + 2 * PAD_X, TH + 2 * PAD_Y);
        for (i, v) in crop.d.iter_mut().enumerate() {
            *v = ((i * 37 % 101) as f32) + if i % 7 == 0 { 60.0 } else { 0.0 };
        }
        for y in 0..TH {
            for x in 0..TW {
                crop.d[(y + 2) * crop.w + x + 3] = t.at(x, y);
            }
        }
        let fast = slot_scores(&crop);
        for (d, t) in templates() {
            let (v, _) = max_loc(&_md(&crop, t));
            assert!(fast[*d as usize] >= v as f64 - 1e-3, "digit {d}: {} vs {v}", fast[*d as usize]);
        }
    }

    #[test]
    fn switch_digits_solve() {
        // synthetic Switch roll: 24 consecutive digits pin the 64-bit state
        let g = Gen::Switch;
        let s0 = 0x2DEC_AB0E_1234_5678u64;
        let st = digit_stream_gen(g, s0, 40);
        let obs: Vec<(usize, u8)> = st.iter().enumerate().map(|(i, &d)| (i, d)).collect();
        let sol = solve_robust(g, &obs, false);
        assert_eq!(sol, vec![s0]);
        // from a later draw too (positions need not start at 0)
        let later: Vec<(usize, u8)> = obs[7..].to_vec();
        assert!(solve_robust(g, &later, false).contains(&s0));
    }

    #[test]
    fn gc_digit_stream_unchanged() {
        assert_eq!(digit_stream(0x423CDA79, 5), digit_stream_gen(Gen::Gc, 0x423CDA79, 5));
    }

    #[test]
    fn templates_load() {
        assert_eq!(templates().len(), 38);
        assert_eq!((panel_reference().w, panel_reference().h), (CANON_W, CANON_H));
    }
}
