//! Fit each letter's starting velocity from its tracked fall (fit.py).

use crate::templates::{delay_frames, pos, START_POS};
use crate::track::Track;

pub const BOUNCE_PX: f64 = 25.0;
pub const PRUNE_RMS: f64 = 0.5;
pub const MAX_PRUNED: usize = 2;

#[derive(Clone, Debug)]
pub struct FitResult {
    pub v: Vec<f64>,
    pub sigma: Vec<f64>,
    pub n_points: Vec<usize>,
    pub f0: f64,
    pub s: f64,
    pub y_floor: f64,
    pub rms_px: f64,
    /// (character index, residuals px), in fit order
    pub residuals: Vec<(usize, Vec<f64>)>,
}

impl FitResult {
    pub fn n_measured(&self) -> usize {
        self.v.iter().filter(|x| x.is_finite()).count()
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Segment {
    Longest,
    First,
}

fn filtered(t: &Track, min_score: f64) -> (Vec<f64>, Vec<f64>) {
    let mut f = Vec::new();
    let mut y = Vec::new();
    for i in 0..t.frames.len() {
        if t.score[i] >= min_score && t.score[i] < 0.995 {
            f.push(t.frames[i]);
            y.push(t.y[i]);
        }
    }
    (f, y)
}

pub fn free_fall(t: &Track, min_score: f64, segment: Segment) -> (Vec<f64>, Vec<f64>) {
    if segment == Segment::First {
        return first_fall(t, min_score);
    }
    let (fr, y) = filtered(t, min_score);
    let mut segments: Vec<(Vec<f64>, Vec<f64>)> = Vec::new();
    let (mut kf, mut ky): (Vec<f64>, Vec<f64>) = (Vec::new(), Vec::new());
    let mut prev: Option<f64> = None;
    for (&f, &yy) in fr.iter().zip(y.iter()) {
        if let (Some(&lf), Some(&ly)) = (kf.last(), ky.last()) {
            let gap = f - lf;
            if gap <= 0.0 {
                continue;
            }
            let dy = (yy - ly) / gap;
            if dy <= 0.5 || prev.is_some_and(|p| dy < 0.8 * p) || prev.is_some_and(|p| dy > p + 4.0) {
                segments.push((std::mem::take(&mut kf), std::mem::take(&mut ky)));
                kf.push(f);
                ky.push(yy);
                prev = None;
                continue;
            }
            prev = Some(dy);
        }
        kf.push(f);
        ky.push(yy);
    }
    segments.push((kf, ky));
    let key = |s: &(Vec<f64>, Vec<f64>)| if s.1.len() > 1 { s.1[s.1.len() - 1] - s.1[0] } else { -1.0 };
    let mut best = 0;
    for i in 1..segments.len() {
        if key(&segments[i]) > key(&segments[best]) {
            best = i;
        }
    }
    let b = segments.swap_remove(best);
    if !b.1.is_empty() && b.1[0] > t.rest_y - BOUNCE_PX {
        return (Vec::new(), Vec::new());
    }
    b
}

fn first_fall(t: &Track, min_score: f64) -> (Vec<f64>, Vec<f64>) {
    let (fr, y) = filtered(t, min_score);
    let (mut kf, mut ky): (Vec<f64>, Vec<f64>) = (Vec::new(), Vec::new());
    let mut prev: Option<f64> = None;
    for (&f, &yy) in fr.iter().zip(y.iter()) {
        if let (Some(&lf), Some(&ly)) = (kf.last(), ky.last()) {
            let gap = f - lf;
            if gap <= 0.0 {
                continue;
            }
            let dy = (yy - ly) / gap;
            if dy <= 0.5 || prev.is_some_and(|p| dy < 0.8 * p) {
                break;
            }
            if prev.is_some_and(|p| dy > p + 4.0) {
                kf = vec![f];
                ky = vec![yy];
                prev = None;
                continue;
            }
            prev = Some(dy);
        }
        kf.push(f);
        ky.push(yy);
    }
    (kf, ky)
}

#[derive(Debug)]
pub struct FitError(pub &'static str);

pub fn fit(tracks: &[Track], num_chars: usize, s_guess: f64, min_points: usize, min_score: f64, min_letters: usize, segment: Segment) -> Result<FitResult, FitError> {
    let mut best = fit_once(tracks, num_chars, s_guess, min_points, min_score, min_letters, segment)?;
    let mut dropped: Vec<usize> = Vec::new();
    while best.rms_px > PRUNE_RMS && dropped.len() < MAX_PRUNED {
        let per: Vec<(usize, f64)> = best
            .residuals
            .iter()
            .filter(|(_, r)| !r.is_empty())
            .map(|(i, r)| (*i, (r.iter().map(|x| x * x).sum::<f64>() / r.len() as f64).sqrt()))
            .collect();
        if per.len() <= min_letters.max(6) {
            break;
        }
        let mut worst = 0;
        for k in 1..per.len() {
            if per[k].1 > per[worst].1 {
                worst = k;
            }
        }
        let vals: Vec<f64> = per.iter().map(|p| p.1).collect();
        if per[worst].1 < 1.0f64.max(3.0 * crate::img::median(&vals)) {
            break;
        }
        dropped.push(per[worst].0);
        let kept: Vec<Track> = tracks.iter().filter(|t| !dropped.contains(&t.index)).cloned().collect();
        let f2 = match fit_once(&kept, num_chars, s_guess, min_points, min_score, min_letters, segment) {
            Ok(f) => f,
            Err(_) => break,
        };
        if f2.rms_px >= best.rms_px {
            break;
        }
        best = f2;
    }
    Ok(best)
}

struct Data {
    idx: usize,
    f: Vec<f64>,
    y: Vec<f64>,
}

fn resid(p: &[f64], data: &[Data], out: &mut Vec<f64>) {
    out.clear();
    let (f0, s, yf) = (p[0], p[1], p[2]);
    for (k, d) in data.iter().enumerate() {
        for (fr, y) in d.f.iter().zip(d.y.iter()) {
            let f = fr - f0;
            out.push(y - (yf - s * pos(p[3 + k], f)));
        }
    }
}

/// Jacobian, row-major (n_res x n_par).
fn jac(p: &[f64], data: &[Data], n_res: usize) -> Vec<f64> {
    let np = p.len();
    let mut j = vec![0.0; n_res * np];
    let (f0, s) = (p[0], p[1]);
    let mut r = 0;
    for (k, d) in data.iter().enumerate() {
        let v = p[3 + k];
        for fr in &d.f {
            let f = fr - f0;
            let row = &mut j[r * np..(r + 1) * np];
            row[0] = -s * (v - 0.5 - f);
            row[1] = pos(v, f);
            row[2] = -1.0;
            row[3 + k] = s * f;
            r += 1;
        }
    }
    j
}

fn soft_l1_cost(r: &[f64]) -> f64 {
    r.iter().map(|x| (1.0 + x * x).sqrt() - 1.0).sum()
}

/// Solve the symmetric positive definite system A x = b (Cholesky; A is n x n row-major).
fn solve_spd(a: &mut [f64], b: &mut [f64], n: usize) -> bool {
    for i in 0..n {
        for j in 0..=i {
            let mut s = a[i * n + j];
            for k in 0..j {
                s -= a[i * n + k] * a[j * n + k];
            }
            if i == j {
                if s <= 0.0 {
                    return false;
                }
                a[i * n + i] = s.sqrt();
            } else {
                a[i * n + j] = s / a[j * n + j];
            }
        }
    }
    for i in 0..n {
        let mut s = b[i];
        for k in 0..i {
            s -= a[i * n + k] * b[k];
        }
        b[i] = s / a[i * n + i];
    }
    for i in (0..n).rev() {
        let mut s = b[i];
        for k in i + 1..n {
            s -= a[k * n + i] * b[k];
        }
        b[i] = s / a[i * n + i];
    }
    true
}

/// Bounded robust least squares (soft_l1, f_scale 1): IRLS with Levenberg damping, projected onto
/// the bounds. Converges to the same minimum scipy's trust-region solver finds from the same start.
fn least_squares(p0: &[f64], lo: &[f64], hi: &[f64], data: &[Data]) -> (Vec<f64>, f64) {
    let np = p0.len();
    let mut p: Vec<f64> = p0.iter().zip(lo.iter().zip(hi.iter())).map(|(&x, (&l, &h))| x.clamp(l, h)).collect();
    let mut r = Vec::new();
    resid(&p, data, &mut r);
    let n = r.len();
    let mut cost = soft_l1_cost(&r);
    let mut lambda = 1e-3;
    let mut trial = vec![0.0; np];
    let mut rt = Vec::new();
    for _ in 0..500 {
        let j = jac(&p, data, n);
        // weights rho'(r^2) for soft_l1
        let mut a = vec![0.0; np * np];
        let mut g = vec![0.0; np];
        for i in 0..n {
            let w = 1.0 / (1.0 + r[i] * r[i]).sqrt();
            let row = &j[i * np..(i + 1) * np];
            for u in 0..np {
                if row[u] == 0.0 {
                    continue;
                }
                g[u] += w * row[u] * r[i];
                for v in 0..=u {
                    a[u * np + v] += w * row[u] * row[v];
                }
            }
        }
        for u in 0..np {
            for v in 0..u {
                a[v * np + u] = a[u * np + v];
            }
        }
        // parameters at a bound with the gradient pushing out stay fixed
        let free: Vec<bool> = (0..np)
            .map(|u| !((p[u] <= lo[u] && g[u] > 0.0) || (p[u] >= hi[u] && g[u] < 0.0)))
            .collect();
        let gnorm: f64 = (0..np).filter(|&u| free[u]).map(|u| g[u].abs()).fold(0.0, f64::max);
        if gnorm < 1e-10 {
            break;
        }
        let mut improved = false;
        for _ in 0..30 {
            let mut m = a.clone();
            let mut b: Vec<f64> = g.iter().map(|x| -x).collect();
            for u in 0..np {
                if !free[u] {
                    for v in 0..np {
                        m[u * np + v] = 0.0;
                        m[v * np + u] = 0.0;
                    }
                    m[u * np + u] = 1.0;
                    b[u] = 0.0;
                } else {
                    m[u * np + u] += lambda * a[u * np + u].max(1e-12);
                }
            }
            if !solve_spd(&mut m, &mut b, np) {
                lambda *= 10.0;
                continue;
            }
            for u in 0..np {
                trial[u] = (p[u] + b[u]).clamp(lo[u], hi[u]);
            }
            resid(&trial, data, &mut rt);
            let c2 = soft_l1_cost(&rt);
            if c2 < cost {
                let step: f64 = (0..np).map(|u| (trial[u] - p[u]).abs() / (1e-8 + p[u].abs())).fold(0.0, f64::max);
                let rel = (cost - c2) / cost.max(1e-300);
                p.copy_from_slice(&trial);
                std::mem::swap(&mut r, &mut rt);
                cost = c2;
                lambda = (lambda * 0.3).max(1e-12);
                improved = true;
                if rel < 1e-12 || step < 1e-10 {
                    return (p, cost);
                }
                break;
            }
            lambda *= 10.0;
        }
        if !improved {
            break;
        }
    }
    (p, cost)
}

pub fn fit_once(tracks: &[Track], num_chars: usize, s_guess: f64, min_points: usize, min_score: f64, min_letters: usize, segment: Segment) -> Result<FitResult, FitError> {
    let mut data: Vec<Data> = Vec::new();
    for t in tracks {
        let (f, y) = free_fall(t, min_score, segment);
        if f.len() >= min_points {
            let dl = delay_frames(t.index, num_chars) as f64;
            data.push(Data { idx: t.index, f: f.iter().map(|x| x - dl).collect(), y });
        }
    }
    if data.len() < min_letters {
        return Err(FitError("too few letters with a usable fall"));
    }
    let floor0 = tracks.iter().map(|t| t.rest_y).fold(f64::NEG_INFINITY, f64::max);

    let sse_at = |f0: f64| -> f64 {
        let mut tot = 0.0;
        for d in &data {
            let f: Vec<f64> = d.f.iter().map(|x| x - f0).collect();
            let target: Vec<f64> = f.iter().zip(d.y.iter()).map(|(&ff, &y)| (floor0 - y) / s_guess - START_POS + ff * (ff + 1.0) / 2.0).collect();
            let ff: f64 = f.iter().map(|x| x * x).sum();
            let ft: f64 = f.iter().zip(target.iter()).map(|(a, b)| a * b).sum();
            let v = ft / ff.max(1e-9);
            tot += f.iter().zip(target.iter()).map(|(a, b)| ((b - v * a).powi(2)).min(25.0)).sum::<f64>();
        }
        tot
    };
    let first = data.iter().flat_map(|d| d.f.iter().cloned()).fold(f64::INFINITY, f64::min);
    let (g0, g1) = ((-40.0f64).min(first - 70.0), 60.0f64.max(first + 5.0));
    let n_grid = ((g1 - g0) / 0.5).ceil().max(0.0) as usize;
    let mut f0_start = g0;
    let mut best_sse = f64::INFINITY;
    for i in 0..n_grid {
        let f0 = g0 + i as f64 * 0.5;
        let s = sse_at(f0);
        if s < best_sse {
            best_sse = s;
            f0_start = f0;
        }
    }
    let nd = data.len();
    let mut lo = vec![(-60.0f64).min(first - 90.0), s_guess * 0.7, floor0 - 30.0];
    let mut hi = vec![80.0f64.max(first + 20.0), s_guess * 1.3, floor0 + 30.0];
    lo.extend(std::iter::repeat_n(-0.5, nd));
    hi.extend(std::iter::repeat_n(5.5, nd));
    let mut best: Option<(Vec<f64>, f64)> = None;
    for f0 in [f0_start - 1.0, f0_start, f0_start + 1.0] {
        let mut p0 = vec![f0, s_guess, floor0];
        p0.extend(std::iter::repeat_n(2.5, nd));
        let (p, c) = least_squares(&p0, &lo, &hi, &data);
        if best.as_ref().is_none_or(|b| c < b.1) {
            best = Some((p, c));
        }
    }
    let p = best.unwrap().0;
    let mut res = Vec::new();
    resid(&p, &data, &mut res);
    let rms = (res.iter().map(|x| (x * x).min(9.0)).sum::<f64>() / res.len() as f64).sqrt();

    let mut v = vec![f64::NAN; num_chars];
    let mut sigma = vec![f64::NAN; num_chars];
    let mut npts = vec![0usize; num_chars];
    let mut residuals = Vec::new();
    let (f0, s) = (p[0], p[1]);
    let mut off = 0;
    for (k, d) in data.iter().enumerate() {
        let n = d.f.len();
        let r_i = &res[off..off + n];
        off += n;
        let i = d.idx;
        v[i] = p[3 + k];
        let own = (r_i.iter().map(|x| x * x).sum::<f64>() / n as f64).sqrt();
        let sig_px = 0.6f64.max(rms).max(own);
        let sf: f64 = d.f.iter().map(|x| (x - f0).powi(2)).sum();
        sigma[i] = sig_px / (s * sf.sqrt());
        npts[i] = n;
        residuals.push((i, r_i.to_vec()));
    }
    Ok(FitResult { v, sigma, n_points: npts, f0, s, y_floor: p[2], rms_px: rms, residuals })
}
