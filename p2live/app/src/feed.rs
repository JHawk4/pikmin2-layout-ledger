//! Finding the game picture inside a capture (p2seeds' feed.py). Splits, timers, borders and
//! backgrounds barely change; the game picture changes all the time. The feed is the largest
//! region with high per-pixel variation across frames sampled over a while of play.

use p2live::img::Gray;

use crate::capture::Crop;

/// Running per-pixel mean and variance of small gray frames.
pub struct FeedFinder {
    w: usize,
    h: usize,
    /// capture pixels per small-frame pixel
    step: usize,
    sum: Vec<f64>,
    sum2: Vec<f64>,
    pub samples: usize,
}

impl FeedFinder {
    pub fn new() -> FeedFinder {
        FeedFinder { w: 0, h: 0, step: 1, sum: Vec::new(), sum2: Vec::new(), samples: 0 }
    }

    pub fn add(&mut self, g: &Gray, step: usize) {
        if g.w != self.w || g.h != self.h || step != self.step {
            *self = FeedFinder { w: g.w, h: g.h, step, sum: vec![0.0; g.w * g.h], sum2: vec![0.0; g.w * g.h], samples: 0 };
        }
        for (i, &v) in g.d.iter().enumerate() {
            let v = v as f64;
            self.sum[i] += v;
            self.sum2[i] += v * v;
        }
        self.samples += 1;
    }

    /// The game picture, in capture pixels (None before a few samples).
    pub fn find(&self) -> Option<Crop> {
        if self.samples < 8 {
            return None;
        }
        let (w, h, n) = (self.w, self.h, self.samples as f64);
        let std: Vec<f64> = (0..w * h)
            .map(|i| {
                let m = self.sum[i] / n;
                (self.sum2[i] / n - m * m).max(0.0).sqrt()
            })
            .collect();
        let mut sorted = std.clone();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let p99 = sorted[((sorted.len() - 1) as f64 * 0.99) as usize];
        let thr = 12.0f64.max(0.35 * p99);
        let mut active: Vec<bool> = std.iter().map(|&s| s > thr).collect();
        let k = 3usize.max((w.min(h) / 60) | 1);
        active = dilate(&active, w, h, k, true);
        active = dilate(&active, w, h, k, false); // close
        active = dilate(&active, w, h, k, false);
        active = dilate(&active, w, h, k, true); // open
        let mask = largest_component(&active, w, h)?;
        let (mut y0, mut y1, mut x0, mut x1) = (0, h, 0, w);
        for _ in 0..3 {
            let cols: Vec<bool> = (0..w).map(|x| (y0..y1).filter(|&y| mask[y * w + x]).count() as f64 > 0.7 * (y1 - y0) as f64).collect();
            (x0, x1) = longest_run(&cols);
            let rows: Vec<bool> = (0..h).map(|y| (x0..x1).filter(|&x| mask[y * w + x]).count() as f64 > 0.7 * (x1 - x0) as f64).collect();
            (y0, y1) = longest_run(&rows);
        }
        if x1 <= x0 + 4 || y1 <= y0 + 4 {
            return None;
        }
        let (x0, x1, y0, y1) = tighten(&std, w, x0, x1, y0, y1);
        let (x0, x1, y0, y1) = grow(&std, w, h, x0, x1, y0, y1);
        let s = self.step;
        Some(Crop { x0: x0 * s, y0: y0 * s, x1: x1 * s, y1: y1 * s })
    }
}

/// k x k max filter (`grow`) or min filter, separable.
fn dilate(m: &[bool], w: usize, h: usize, k: usize, grow: bool) -> Vec<bool> {
    let r = k / 2;
    let pass = |src: &[bool], horiz: bool| -> Vec<bool> {
        let mut out = vec![false; w * h];
        for y in 0..h {
            for x in 0..w {
                let (lo, hi, at): (usize, usize, Box<dyn Fn(usize) -> bool>) = if horiz {
                    (x.saturating_sub(r), (x + r).min(w - 1), Box::new(|i| src[y * w + i]))
                } else {
                    (y.saturating_sub(r), (y + r).min(h - 1), Box::new(|i| src[i * w + x]))
                };
                out[y * w + x] = if grow { (lo..=hi).any(&at) } else { (lo..=hi).all(&at) };
            }
        }
        out
    };
    pass(&pass(m, true), false)
}

fn largest_component(m: &[bool], w: usize, h: usize) -> Option<Vec<bool>> {
    let mut label = vec![0u32; w * h];
    let mut best = (0usize, 0u32);
    let mut next = 0u32;
    let mut stack = Vec::new();
    for start in 0..w * h {
        if !m[start] || label[start] != 0 {
            continue;
        }
        next += 1;
        let mut size = 0;
        stack.push(start);
        label[start] = next;
        while let Some(i) = stack.pop() {
            size += 1;
            let (x, y) = (i % w, i / w);
            let mut try_push = |j: usize| {
                if m[j] && label[j] == 0 {
                    label[j] = next;
                    stack.push(j);
                }
            };
            if x > 0 {
                try_push(i - 1);
            }
            if x + 1 < w {
                try_push(i + 1);
            }
            if y > 0 {
                try_push(i - w);
            }
            if y + 1 < h {
                try_push(i + w);
            }
        }
        if size > best.0 {
            best = (size, next);
        }
    }
    (best.0 > 0).then(|| label.iter().map(|&l| l == best.1).collect())
}

fn longest_run(flags: &[bool]) -> (usize, usize) {
    let (mut best, mut best_len, mut start) = ((0, flags.len()), 0usize, None);
    for (i, &f) in flags.iter().chain(std::iter::once(&false)).enumerate() {
        match (f, start) {
            (true, None) => start = Some(i),
            (false, Some(s)) => {
                if i - s > best_len {
                    best = (s, i);
                    best_len = i - s;
                }
                start = None;
            }
            _ => {}
        }
    }
    best
}

/// Pull each edge inward (at most 8% of the size) past columns/rows clearly calmer than the
/// interior: a busy splits column can pass the activity threshold.
fn tighten(std: &[f64], w: usize, mut x0: usize, mut x1: usize, mut y0: usize, mut y1: usize) -> (usize, usize, usize, usize) {
    fn edge(profile: &[f64], forward: bool) -> usize {
        let mut s = profile.to_vec();
        s.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let reference = s[s.len() / 2];
        let lim = ((0.08 * profile.len() as f64) as usize).max(1);
        let n = profile.len();
        for j in 0..lim {
            let i = if forward { j } else { n - 1 - j };
            if profile[i] >= 0.75 * reference {
                return i;
            }
        }
        if forward { 0 } else { n - 1 }
    }
    for _ in 0..2 {
        let cols: Vec<f64> = (x0..x1).map(|x| (y0..y1).map(|y| std[y * w + x]).sum::<f64>() / (y1 - y0) as f64).collect();
        let (a, b) = (edge(&cols, true), edge(&cols, false));
        (x0, x1) = (x0 + a, x0 + b + 1);
        let rows: Vec<f64> = (y0..y1).map(|y| (x0..x1).map(|x| std[y * w + x]).sum::<f64>() / (x1 - x0) as f64).collect();
        let (a, b) = (edge(&rows, true), edge(&rows, false));
        (y0, y1) = (y0 + a, y0 + b + 1);
    }
    (x0, x1, y0, y1)
}

/// Push each edge outward while the next column/row still varies: Pikmin 2 darkens the edges of
/// its picture, so the busiest region stops short of them. A stream layout around the game is
/// still (a running timer is a small part of a column), so growth stops at the layout.
fn grow(std: &[f64], w: usize, h: usize, mut x0: usize, mut x1: usize, mut y0: usize, mut y1: usize) -> (usize, usize, usize, usize) {
    let col = |x: usize, y0: usize, y1: usize| (y0..y1).map(|y| std[y * w + x]).sum::<f64>() / (y1 - y0) as f64;
    let row = |y: usize, x0: usize, x1: usize| (x0..x1).map(|x| std[y * w + x]).sum::<f64>() / (x1 - x0) as f64;
    let mut inner: Vec<f64> = (x0..x1).map(|x| col(x, y0, y1)).collect();
    inner.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let reference = inner[inner.len() / 2];
    let lim = 3.0f64.max(0.15 * reference);
    for _ in 0..3 {
        while x0 > 0 && col(x0 - 1, y0, y1) >= lim {
            x0 -= 1;
        }
        while x1 < w && col(x1, y0, y1) >= lim {
            x1 += 1;
        }
        while y0 > 0 && row(y0 - 1, x0, x1) >= lim {
            y0 -= 1;
        }
        while y1 < h && row(y1, x0, x1) >= lim {
            y1 += 1;
        }
    }
    (x0, x1, y0, y1)
}
