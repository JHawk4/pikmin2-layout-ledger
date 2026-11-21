//! Images and the few image operations the detector needs (templates.py and the OpenCV calls it
//! makes): prep, percentiles, OpenCV-compatible INTER_AREA resizing, and TM_CCOEFF_NORMED template
//! matching (direct for small searches, FFT for the cave-name search).

use std::sync::Arc;

use realfft::{ComplexToReal, RealFftPlanner, RealToComplex};
use rustfft::{num_complex::Complex, Fft, FftPlanner};

/// 8-bit grayscale frame, row-major.
#[derive(Clone, Debug)]
pub struct Gray {
    pub w: usize,
    pub h: usize,
    pub d: Arc<Vec<u8>>,
    /// offset of (0,0) into `d` and the row stride (crops share the buffer)
    pub off: usize,
    pub stride: usize,
}

impl Gray {
    pub fn new(w: usize, h: usize, d: Vec<u8>) -> Self {
        assert_eq!(d.len(), w * h);
        Gray { w, h, d: Arc::new(d), off: 0, stride: w }
    }
    #[inline]
    pub fn at(&self, x: usize, y: usize) -> u8 {
        self.d[self.off + y * self.stride + x]
    }
    #[inline]
    pub fn row(&self, y: usize) -> &[u8] {
        let s = self.off + y * self.stride;
        &self.d[s..s + self.w]
    }
    /// Rows [y0, y1) and columns [x0, x1), clipped like numpy slicing.
    pub fn crop(&self, x0: usize, y0: usize, x1: usize, y1: usize) -> Gray {
        let x1 = x1.min(self.w);
        let y1 = y1.min(self.h);
        let x0 = x0.min(x1);
        let y0 = y0.min(y1);
        Gray { w: x1 - x0, h: y1 - y0, d: self.d.clone(), off: self.off + y0 * self.stride + x0, stride: self.stride }
    }
    pub fn mean(&self) -> f64 {
        let mut s: u64 = 0;
        for y in 0..self.h {
            s += self.row(y).iter().map(|&v| v as u64).sum::<u64>();
        }
        s as f64 / (self.w * self.h).max(1) as f64
    }
    /// numpy.percentile (linear interpolation) of the pixel values.
    pub fn percentile(&self, q: f64) -> f64 {
        let mut hist = [0u64; 256];
        for y in 0..self.h {
            for &v in self.row(y) {
                hist[v as usize] += 1;
            }
        }
        let n = (self.w * self.h) as u64;
        if n == 0 {
            return 0.0;
        }
        let pos = q / 100.0 * (n - 1) as f64;
        let lo = pos.floor() as u64;
        let frac = pos - lo as f64;
        let value_at = |k: u64| -> f64 {
            let mut acc = 0u64;
            for (v, &c) in hist.iter().enumerate() {
                acc += c;
                if acc > k {
                    return v as f64;
                }
            }
            255.0
        };
        let a = value_at(lo);
        if frac == 0.0 {
            return a;
        }
        let b = value_at((lo + 1).min(n - 1));
        a + frac * (b - a)
    }
}

/// Float image, row-major.
#[derive(Clone, Debug, Default)]
pub struct Img {
    pub w: usize,
    pub h: usize,
    pub d: Vec<f32>,
}

impl Img {
    pub fn zeros(w: usize, h: usize) -> Self {
        Img { w, h, d: vec![0.0; w * h] }
    }
    #[inline]
    pub fn at(&self, x: usize, y: usize) -> f32 {
        self.d[y * self.w + x]
    }
    #[inline]
    pub fn set(&mut self, x: usize, y: usize, v: f32) {
        self.d[y * self.w + x] = v;
    }
    pub fn rows(&self, y0: usize, y1: usize) -> Img {
        let y1 = y1.min(self.h);
        let y0 = y0.min(y1);
        Img { w: self.w, h: y1 - y0, d: self.d[y0 * self.w..y1 * self.w].to_vec() }
    }
    pub fn crop(&self, x0: usize, y0: usize, x1: usize, y1: usize) -> Img {
        let x1 = x1.min(self.w);
        let y1 = y1.min(self.h);
        let x0 = x0.min(x1);
        let y0 = y0.min(y1);
        let mut out = Img::zeros(x1 - x0, y1 - y0);
        for y in y0..y1 {
            out.d[(y - y0) * out.w..(y - y0 + 1) * out.w].copy_from_slice(&self.d[y * self.w + x0..y * self.w + x1]);
        }
        out
    }
    /// Population standard deviation (numpy .std()).
    pub fn std(&self) -> f64 {
        let n = self.d.len().max(1) as f64;
        let m: f64 = self.d.iter().map(|&v| v as f64).sum::<f64>() / n;
        (self.d.iter().map(|&v| (v as f64 - m).powi(2)).sum::<f64>() / n).sqrt()
    }
}

pub const FULL_BRIGHT: f32 = 214.0;

/// templates.prep: map to [0,1] emphasizing the bright glyph outlines; `rf` = the frame's bright level.
pub fn prep(g: &Gray, rf: Option<f64>) -> Img {
    let k: f32 = match rf {
        None => 1.0,
        Some(r) => (r.max(1.0) / FULL_BRIGHT as f64).min(1.0) as f32,
    };
    let lo = 90.0f32 * k;
    let sc = 120.0f32 * k;
    let mut out = Img::zeros(g.w, g.h);
    for y in 0..g.h {
        let row = g.row(y);
        let o = &mut out.d[y * g.w..(y + 1) * g.w];
        for x in 0..g.w {
            o[x] = ((row[x] as f32 - lo) / sc).clamp(0.0, 1.0);
        }
    }
    out
}

/// templates.prep on an image already in 0-255 floats (glyph templates).
pub fn prep_f(g: &Img) -> Img {
    Img { w: g.w, h: g.h, d: g.d.iter().map(|&v| ((v - 90.0) / 120.0).clamp(0.0, 1.0)).collect() }
}

pub fn bright_level(g: &Gray) -> f64 {
    g.percentile(99.9)
}

/// Python's round(): ties to even.
#[inline]
pub fn pyround(x: f64) -> i64 {
    x.round_ties_even() as i64
}

/// numpy.percentile with linear interpolation over an unsorted slice.
pub fn percentile(v: &[f64], q: f64) -> f64 {
    let mut s: Vec<f64> = v.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    if s.is_empty() {
        return f64::NAN;
    }
    let pos = q / 100.0 * (s.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = (lo + 1).min(s.len() - 1);
    s[lo] + (pos - lo as f64) * (s[hi] - s[lo])
}

pub fn median(v: &[f64]) -> f64 {
    percentile(v, 50.0)
}

// ---------------------------------------------------------------------------------------------
// resize (cv2.resize with INTER_AREA)

/// One axis of OpenCV's area resampling: per destination index, the (source index, weight) list.
fn area_tab(src: usize, dst: usize) -> Vec<Vec<(usize, f64)>> {
    let scale = src as f64 / dst as f64;
    let mut tab = Vec::with_capacity(dst);
    for dx in 0..dst {
        let fsx1 = dx as f64 * scale;
        let fsx2 = fsx1 + scale;
        let cell = scale.min(src as f64 - fsx1);
        let mut sx1 = fsx1.ceil() as i64;
        let mut sx2 = fsx2.floor() as i64;
        sx2 = sx2.min(src as i64 - 1);
        sx1 = sx1.min(sx2);
        let mut e = Vec::new();
        if sx1 as f64 - fsx1 > 1e-3 {
            e.push(((sx1 - 1) as usize, (sx1 as f64 - fsx1) / cell));
        }
        for sx in sx1..sx2 {
            e.push((sx as usize, 1.0 / cell));
        }
        if fsx2 - sx2 as f64 > 1e-3 {
            e.push((sx2 as usize, (fsx2 - sx2 as f64).min(1.0).min(cell) / cell));
        }
        tab.push(e);
    }
    tab
}

/// The INTER_AREA upscaling branch (OpenCV switches to linear with area-style coefficients).
fn linear_area_tab(src: usize, dst: usize) -> Vec<Vec<(usize, f64)>> {
    let scale = src as f64 / dst as f64;
    let inv = 1.0 / scale;
    let mut tab = Vec::with_capacity(dst);
    for dx in 0..dst {
        let mut sx = (dx as f64 * scale).floor() as i64;
        let mut fx = (dx as f64 + 1.0) - (sx as f64 + 1.0) * inv;
        fx = if fx <= 0.0 { 0.0 } else { fx - fx.floor() };
        if sx < 0 {
            sx = 0;
            fx = 0.0;
        }
        if sx >= src as i64 - 1 {
            sx = src as i64 - 1;
            fx = 0.0;
        }
        let s = sx as usize;
        if fx == 0.0 {
            tab.push(vec![(s, 1.0)]);
        } else {
            tab.push(vec![(s, 1.0 - fx), ((s + 1).min(src - 1), fx)]);
        }
    }
    tab
}

pub fn resize_area(src: &Img, w: usize, h: usize) -> Img {
    if w == src.w && h == src.h {
        return src.clone();
    }
    let down = src.w >= w && src.h >= h;
    let (tx, ty) = if down {
        (area_tab(src.w, w), area_tab(src.h, h))
    } else {
        (linear_area_tab(src.w, w), linear_area_tab(src.h, h))
    };
    // separable: columns first into a temp of size (w x src.h), then rows
    let mut tmp = vec![0.0f64; w * src.h];
    for y in 0..src.h {
        let row = &src.d[y * src.w..(y + 1) * src.w];
        for (x, e) in tx.iter().enumerate() {
            let mut s = 0.0;
            for &(i, wt) in e {
                s += row[i] as f64 * wt;
            }
            tmp[y * w + x] = s;
        }
    }
    let mut out = Img::zeros(w, h);
    for (y, e) in ty.iter().enumerate() {
        for x in 0..w {
            let mut s = 0.0;
            for &(i, wt) in e {
                s += tmp[i * w + x] * wt;
            }
            out.d[y * w + x] = s as f32;
        }
    }
    out
}

// ---------------------------------------------------------------------------------------------
// template matching (cv2.TM_CCOEFF_NORMED, then templates.match's zeroing of flat patches)

struct Integral {
    w1: usize,
    s: Vec<f64>,
    s2: Vec<f64>,
}

impl Integral {
    fn new(im: &Img) -> Self {
        let w1 = im.w + 1;
        let mut s = vec![0.0; w1 * (im.h + 1)];
        let mut s2 = vec![0.0; w1 * (im.h + 1)];
        for y in 0..im.h {
            let (mut r, mut r2) = (0.0, 0.0);
            for x in 0..im.w {
                let v = im.d[y * im.w + x] as f64;
                r += v;
                r2 += v * v;
                s[(y + 1) * w1 + x + 1] = s[y * w1 + x + 1] + r;
                s2[(y + 1) * w1 + x + 1] = s2[y * w1 + x + 1] + r2;
            }
        }
        Integral { w1, s, s2 }
    }
    #[inline]
    fn sums(&self, x: usize, y: usize, w: usize, h: usize) -> (f64, f64) {
        let a = y * self.w1 + x;
        let b = y * self.w1 + x + w;
        let c = (y + h) * self.w1 + x;
        let d = (y + h) * self.w1 + x + w;
        (self.s[d] - self.s[b] - self.s[c] + self.s[a], self.s2[d] - self.s2[b] - self.s2[c] + self.s2[a])
    }
}

/// Turn raw correlations corr(x,y) = sum T(i,j) I(x+i,y+j) into the normalized score.
fn normalize(corr: Vec<f64>, rw: usize, rh: usize, im: &Img, t: &Img) -> Img {
    normalize_with(corr, rw, rh, &Integral::new(im), t)
}

fn normalize_with(corr: Vec<f64>, rw: usize, rh: usize, ii: &Integral, t: &Img) -> Img {
    let n = (t.w * t.h) as f64;
    let tsum: f64 = t.d.iter().map(|&v| v as f64).sum();
    let tmean = tsum / n;
    let tnorm2: f64 = t.d.iter().map(|&v| (v as f64 - tmean).powi(2)).sum();
    let tnorm = tnorm2.sqrt();
    let mut out = Img::zeros(rw, rh);
    for y in 0..rh {
        for x in 0..rw {
            let (s, s2) = ii.sums(x, y, t.w, t.h);
            let wmean2 = s * s / n;
            let mut num = corr[y * rw + x] - tmean * s;
            let tt = (s2 - wmean2).max(0.0).sqrt() * tnorm;
            if num.abs() < tt {
                num /= tt;
            } else if num.abs() < tt * 1.125 {
                num = if num > 0.0 { 1.0 } else { -1.0 };
            } else {
                num = 0.0;
            }
            // templates.match: zero flat patches (variance of the window < 1e-4)
            let var = s2 / n - (s / n) * (s / n);
            if !num.is_finite() || var < 1e-4 {
                num = 0.0;
            }
            out.d[y * rw + x] = num as f32;
        }
    }
    out
}

/// templates.match by direct summation (small searches: letter strips).
pub fn match_direct(im: &Img, t: &Img) -> Img {
    assert!(t.w <= im.w && t.h <= im.h);
    let rw = im.w - t.w + 1;
    let rh = im.h - t.h + 1;
    // only the template's nonzero pixels contribute (glyphs are mostly zero)
    let nz: Vec<(usize, f32)> = (0..t.h)
        .flat_map(|j| (0..t.w).map(move |i| (j, i)))
        .filter_map(|(j, i)| {
            let v = t.d[j * t.w + i];
            (v != 0.0).then_some((j * im.w + i, v))
        })
        .collect();
    let mut corr = vec![0.0f64; rw * rh];
    for y in 0..rh {
        for x in 0..rw {
            let base = y * im.w + x;
            let mut s = 0.0f32;
            for &(o, v) in &nz {
                s += im.d[base + o] * v;
            }
            corr[y * rw + x] = s as f64;
        }
    }
    normalize(corr, rw, rh, im, t)
}

/// A search image prepared once for many templates (the cave-name band): its 2D spectrum (real FFT
/// along rows, complex along columns; stored column-major), the FFT plans and its integral image.
pub struct FftImage {
    pub im: Img,
    pw: usize,
    ph: usize,
    cw: usize,
    spec: Vec<Complex<f64>>, // [x * ph + y], x < cw
    r2c: Arc<dyn RealToComplex<f64>>,
    c2r: Arc<dyn ComplexToReal<f64>>,
    cf: Arc<dyn Fft<f64>>,
    ci: Arc<dyn Fft<f64>>,
    ii: Integral,
}

fn good_size(n: usize) -> usize {
    // next even size with factors 2, 3, 5 only
    let mut m = n.max(2);
    loop {
        let mut k = m;
        for p in [2, 3, 5] {
            while k % p == 0 {
                k /= p;
            }
        }
        if k == 1 && m % 2 == 0 {
            return m;
        }
        m += 1;
    }
}

impl FftImage {
    pub fn new(im: Img) -> Self {
        let pw = good_size(im.w);
        let ph = good_size(im.h);
        let cw = pw / 2 + 1;
        let mut rp = RealFftPlanner::<f64>::new();
        let r2c = rp.plan_fft_forward(pw);
        let c2r = rp.plan_fft_inverse(pw);
        let mut cp = FftPlanner::<f64>::new();
        let cf = cp.plan_fft_forward(ph);
        let ci = cp.plan_fft_inverse(ph);
        let ii = Integral::new(&im);
        let mut me = FftImage { im, pw, ph, cw, spec: Vec::new(), r2c, c2r, cf, ci, ii };
        let rows: Vec<Vec<f64>> = (0..me.im.h).map(|y| me.im.d[y * me.im.w..(y + 1) * me.im.w].iter().map(|&v| v as f64).collect()).collect();
        me.spec = me.forward(&rows);
        me
    }

    /// Spectrum of an image given by its first rows (the rest zero), column-major.
    fn forward(&self, rows: &[Vec<f64>]) -> Vec<Complex<f64>> {
        let (pw, ph, cw) = (self.pw, self.ph, self.cw);
        let mut spec = vec![Complex::new(0.0, 0.0); cw * ph];
        let mut inp = vec![0.0f64; pw];
        let mut out = vec![Complex::new(0.0, 0.0); cw];
        for (y, row) in rows.iter().enumerate() {
            inp.iter_mut().for_each(|v| *v = 0.0);
            inp[..row.len()].copy_from_slice(row);
            self.r2c.process(&mut inp, &mut out).unwrap();
            for x in 0..cw {
                spec[x * ph + y] = out[x];
            }
        }
        for col in spec.chunks_mut(ph) {
            self.cf.process(col);
        }
        spec
    }

    /// templates.match(self.im, t) via FFT (cyclic correlation; valid positions only).
    pub fn match_t(&self, t: &Img) -> Img {
        let im = &self.im;
        assert!(t.w <= im.w && t.h <= im.h);
        let (pw, ph, cw) = (self.pw, self.ph, self.cw);
        let rows: Vec<Vec<f64>> = (0..t.h).map(|y| t.d[y * t.w..(y + 1) * t.w].iter().map(|&v| v as f64).collect()).collect();
        let mut ts = self.forward(&rows);
        for (a, b) in ts.iter_mut().zip(self.spec.iter()) {
            *a = b * a.conj();
        }
        for col in ts.chunks_mut(ph) {
            self.ci.process(col);
        }
        let rw = im.w - t.w + 1;
        let rh = im.h - t.h + 1;
        let scale = 1.0 / (pw * ph) as f64;
        let mut corr = vec![0.0f64; rw * rh];
        let mut inp = vec![Complex::new(0.0, 0.0); cw];
        let mut out = vec![0.0f64; pw];
        for y in 0..rh {
            for x in 0..cw {
                inp[x] = ts[x * ph + y];
            }
            inp[0].im = 0.0;
            inp[cw - 1].im = 0.0;
            self.c2r.process(&mut inp, &mut out).unwrap();
            for x in 0..rw {
                corr[y * rw + x] = out[x] * scale;
            }
        }
        normalize_with(corr, rw, rh, &self.ii, t)
    }
}

/// cv2.minMaxLoc's max: (value, (x, y)), first in row-major order.
pub fn max_loc(r: &Img) -> (f32, (usize, usize)) {
    let mut best = f32::NEG_INFINITY;
    let mut at = (0, 0);
    for y in 0..r.h {
        for x in 0..r.w {
            let v = r.d[y * r.w + x];
            if v > best {
                best = v;
                at = (x, y);
            }
        }
    }
    (best, at)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fft_matches_direct() {
        let mut im = Img::zeros(40, 30);
        let mut x: u64 = 12345;
        for v in im.d.iter_mut() {
            x = x.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            *v = (x >> 40) as f32 / (1u64 << 24) as f32;
        }
        let t = im.crop(5, 4, 17, 13);
        let a = match_direct(&im, &t);
        let b = FftImage::new(im.clone()).match_t(&t);
        for (x, y) in a.d.iter().zip(b.d.iter()) {
            assert!((x - y).abs() < 1e-4, "{x} {y}");
        }
        assert_eq!(max_loc(&a).1, (5, 4));
    }
    #[test]
    fn area_downscale_halves() {
        let im = Img { w: 4, h: 2, d: vec![0., 2., 4., 6., 8., 10., 12., 14.] };
        let r = resize_area(&im, 2, 1);
        assert_eq!(r.d, vec![5.0, 9.0]);
    }
}
