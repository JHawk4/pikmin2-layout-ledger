//! Seed search by lattice reduction (lattice.py), candidate scoring (search._score) and the
//! search near a known seed (search.search_near).

use crate::img::{median, pyround};
use crate::rng::{self, Gen};

pub const V_PER_RAND: f64 = 5.0 / 32768.0;
const M: i128 = 1 << 31;
const UNIT: i128 = 1 << 16;

#[derive(Clone, Debug)]
pub struct Candidate {
    pub letter_seed: u64,
    pub score: f64,
    pub bias: f64,
    pub residuals: Vec<f64>,
    pub distance: Option<u64>,
}

impl Candidate {
    pub fn n_measured(&self) -> usize {
        self.residuals.iter().filter(|x| x.is_finite()).count()
    }
}

fn dotf(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

/// LLL-reduce integer rows (exact integer rows, floating Gram-Schmidt).
pub fn lll(basis: &[Vec<i128>], delta: f64) -> Vec<Vec<i128>> {
    let mut b: Vec<Vec<i128>> = basis.to_vec();
    let n = b.len();
    let gs = |b: &Vec<Vec<i128>>| -> (Vec<Vec<f64>>, Vec<f64>) {
        let mut bs: Vec<Vec<f64>> = b.iter().map(|r| r.iter().map(|&x| x as f64).collect()).collect();
        let mut mu = vec![vec![0.0; n]; n];
        let mut nb = vec![0.0; n];
        for i in 0..n {
            for j in 0..i {
                let bi: Vec<f64> = b[i].iter().map(|&x| x as f64).collect();
                mu[i][j] = if nb[j] != 0.0 { dotf(&bi, &bs[j]) / nb[j] } else { 0.0 };
                let m = mu[i][j];
                let (lo, hi) = bs.split_at_mut(i);
                for (p, q) in hi[0].iter_mut().zip(lo[j].iter()) {
                    *p -= m * q;
                }
            }
            nb[i] = dotf(&bs[i], &bs[i]);
        }
        (mu, nb)
    };
    let (mut mu, mut nb) = gs(&b);
    let mut k = 1;
    while k < n {
        for j in (0..k).rev() {
            let q = mu[k][j].round_ties_even();
            if q != 0.0 {
                let qi = q as i128;
                let bj = b[j].clone();
                for (p, r) in b[k].iter_mut().zip(bj.iter()) {
                    *p -= qi * r;
                }
                for t in 0..j {
                    mu[k][t] -= q * mu[j][t];
                }
                mu[k][j] -= q;
            }
        }
        if nb[k] >= (delta - mu[k][k - 1] * mu[k][k - 1]) * nb[k - 1] {
            k += 1;
        } else {
            b.swap(k, k - 1);
            let r = gs(&b);
            mu = r.0;
            nb = r.1;
            k = (k - 1).max(1);
        }
    }
    b
}

/// All lattice points p (lattice spanned by `gens`) with lo <= p <= hi, or None past `max_nodes`.
pub fn box_points(gens: &[Vec<i128>], lo: &[i128], hi: &[i128], max_nodes: usize) -> Option<Vec<Vec<i128>>> {
    let n = lo.len();
    let half: Vec<f64> = lo.iter().zip(hi).map(|(&l, &h)| (h - l) as f64 / 2.0).collect();
    let wmax = half.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let k: Vec<i128> = half.iter().map(|&h| (pyround(wmax / h.max(1.0)) as i128).max(1)).collect();
    let scaled: Vec<Vec<i128>> = gens.iter().map(|r| r.iter().zip(&k).map(|(x, kj)| x * kj).collect()).collect();
    let red = lll(&scaled, 0.99);
    let basis: Vec<Vec<i128>> = red.iter().map(|r| r.iter().zip(&k).map(|(x, kj)| x.div_euclid(*kj)).collect()).collect();
    let bf: Vec<Vec<f64>> = red.iter().map(|r| r.iter().map(|&x| x as f64).collect()).collect();
    let mut bs: Vec<Vec<f64>> = Vec::new();
    let mut mu = vec![vec![0.0; n]; n];
    let mut nb: Vec<f64> = Vec::new();
    for i in 0..n {
        let mut v = bf[i].clone();
        for j in 0..i {
            mu[i][j] = dotf(&bf[i], &bs[j]) / nb[j];
            let m = mu[i][j];
            for (p, q) in v.iter_mut().zip(bs[j].iter()) {
                *p -= m * q;
            }
        }
        nb.push(dotf(&v, &v));
        bs.push(v);
    }
    let center: Vec<f64> = lo.iter().zip(hi).zip(&k).map(|((&l, &h), &kj)| (l + h) as f64 / 2.0 * kj as f64).collect();
    let tau: Vec<f64> = (0..n).map(|i| dotf(&center, &bs[i]) / nb[i]).collect();
    let r2 = half.iter().zip(&k).map(|(h, &kj)| (h * kj as f64).powi(2)).sum::<f64>() * (1.0 + 1e-9) + 1.0;

    struct St<'a> {
        n: usize,
        mu: &'a Vec<Vec<f64>>,
        nb: &'a Vec<f64>,
        tau: &'a Vec<f64>,
        basis: &'a Vec<Vec<i128>>,
        lo: &'a [i128],
        hi: &'a [i128],
        coef: Vec<i128>,
        nodes: usize,
        max_nodes: usize,
        out: Vec<Vec<i128>>,
    }
    fn rec(s: &mut St, i: usize, rem: f64) -> bool {
        let c = s.tau[i] - ((i + 1)..s.n).map(|j| s.coef[j] as f64 * s.mu[j][i]).sum::<f64>();
        let w = (rem.max(0.0) / s.nb[i]).sqrt();
        let (a, b) = ((c - w).ceil() as i128, (c + w).floor() as i128);
        let mut ci = a;
        while ci <= b {
            s.nodes += 1;
            if s.nodes > s.max_nodes {
                return false;
            }
            s.coef[i] = ci;
            let d = rem - (ci as f64 - c).powi(2) * s.nb[i];
            if i == 0 {
                let p: Vec<i128> = (0..s.n).map(|t| (0..s.n).map(|j| s.coef[j] * s.basis[j][t]).sum()).collect();
                if p.iter().zip(s.lo.iter().zip(s.hi.iter())).all(|(x, (l, h))| l <= x && x <= h) {
                    s.out.push(p);
                }
            } else if !rec(s, i - 1, d) {
                return false;
            }
            ci += 1;
        }
        true
    }
    let mut st = St { n, mu: &mu, nb: &nb, tau: &tau, basis: &basis, lo, hi, coef: vec![0; n], nodes: 0, max_nodes, out: Vec::new() };
    if rec(&mut st, n - 1, r2) { Some(st.out) } else { None }
}

pub struct SearchError;

/// lattice.search (k_tol 4, max_bias 0.5, cap 16, top 5, max_dim 8), GC generator.
pub fn search(v: &[f64], sigma: &[f64], leave_out: &[usize], max_nodes: usize) -> Result<Vec<Candidate>, SearchError> {
    search_gen(Gen::Gc, v, sigma, leave_out, max_nodes)
}

/// Letter speed of the draw that left state `s` (5 * randFloat).
#[inline]
pub fn speed(g: Gen, s: u64) -> f64 {
    match g {
        Gen::Gc => rng::rand_of_state(s) as f64 * V_PER_RAND,
        Gen::Switch => 5.0 * g.frac(s),
    }
}

/// lattice.search for either generator.
pub fn search_gen(g: Gen, v: &[f64], sigma: &[f64], leave_out: &[usize], max_nodes: usize) -> Result<Vec<Candidate>, SearchError> {
    let (k_tol, max_bias, cap, top, max_dim) = (4.0, 0.5, 16.0, 5, 8);
    let measured: Vec<usize> = (0..v.len()).filter(|&i| v[i].is_finite() && sigma[i].is_finite() && !leave_out.contains(&i)).collect();
    if measured.len() < 3 {
        return Err(SearchError);
    }
    if g == Gen::Switch {
        return search64(v, sigma, &measured, k_tol, max_bias, cap, top, max_nodes);
    }
    let mut pivot = measured[0];
    for &i in &measured {
        if sigma[i] < sigma[pivot] {
            pivot = i;
        }
    }
    let mut others: Vec<usize> = measured
        .iter()
        .cloned()
        .filter(|&i| i != pivot && k_tol * sigma[i].hypot(sigma[pivot]) / V_PER_RAND < 8192.0)
        .collect();
    if others.len() < 2 {
        return Err(SearchError);
    }
    others.sort_by(|&a, &b| sigma[a].partial_cmp(&sigma[b]).unwrap());
    others.truncate(max_dim - 1);
    let jumps: Vec<(u64, u64)> = (0..v.len()).map(|i| rng::jump(i as i64 - pivot as i64)).collect();

    let span = (k_tol * sigma[pivot] + max_bias) / V_PER_RAND;
    let rp = v[pivot] / V_PER_RAND;
    let mut lo: Vec<i128> = vec![0.0f64.max((rp - span).floor()) as i128 * UNIT];
    let mut hi: Vec<i128> = vec![((1i128 << 15).min((rp + span).ceil() as i128 + 1)) * UNIT - 1];
    let mut gens: Vec<Vec<i128>> = Vec::new();
    let mut first = vec![1i128];
    first.extend(others.iter().map(|&i| (jumps[i].0 as i128 - 1).rem_euclid(M)));
    gens.push(first);
    for t in 0..others.len() {
        let mut row = vec![0i128; others.len() + 1];
        row[t + 1] = M;
        gens.push(row);
    }
    for &i in &others {
        let d = (v[i] - v[pivot]) / V_PER_RAND;
        let tol = k_tol * sigma[i].hypot(sigma[pivot]) / V_PER_RAND;
        let c = (jumps[i].1 as i128).rem_euclid(M);
        lo.push((d - tol - 1.0).floor() as i128 * UNIT - c);
        hi.push((d + tol + 1.0).ceil() as i128 * UNIT - 1 - c);
    }
    let pts = match box_points(&gens, &lo, &hi, max_nodes) {
        Some(p) if !p.is_empty() => p,
        _ => return Ok(Vec::new()),
    };
    let mut states: Vec<u64> = pts.iter().map(|p| p[0].rem_euclid(M) as u64).collect();
    states.sort();
    states.dedup();
    let mut best = score(&states, v, sigma, &measured, &jumps, pivot, cap, max_bias);
    best.sort_by(|a, b| a.score.partial_cmp(&b.score).unwrap());
    best.truncate(top);
    Ok(best)
}

/// Switch letters per search (lattice._search64's SWITCH_MAX_DIM).
pub const SWITCH_MAX_DIM: usize = 16;

/// lattice._search64: the same box as the GC search over the full 64-bit musl state.
#[allow(clippy::too_many_arguments)]
fn search64(v: &[f64], sigma: &[f64], measured: &[usize], k_tol: f64, max_bias: f64, cap: f64, top: usize, max_nodes: usize) -> Result<Vec<Candidate>, SearchError> {
    let g = Gen::Switch;
    let m64: i128 = 1 << 64;
    let mf = 18446744073709551616.0f64;
    let mut pivot = measured[0];
    for &i in measured {
        if sigma[i] < sigma[pivot] {
            pivot = i;
        }
    }
    let mut others: Vec<usize> = measured.iter().cloned().filter(|&i| i != pivot).collect();
    others.sort_by(|&a, &b| sigma[a].partial_cmp(&sigma[b]).unwrap());
    others.truncate(SWITCH_MAX_DIM - 1);
    let jumps: Vec<(u64, u64)> = (0..v.len()).map(|i| g.jump(i as i64 - pivot as i64)).collect();
    let span = k_tol * sigma[pivot] + max_bias;
    let mut lo: Vec<i128> = vec![(((v[pivot] - span) / 5.0 * mf).floor() as i128).max(0)];
    let mut hi: Vec<i128> = vec![(((v[pivot] + span) / 5.0 * mf).ceil() as i128).min(m64 - 1)];
    let mut row = vec![1i128];
    for &i in &others {
        let (a, c) = jumps[i];
        row.push((a as i128 - 1).rem_euclid(m64));
        let d = v[i] - v[pivot];
        let tol = k_tol * sigma[i].hypot(sigma[pivot]) + 1e-6;
        lo.push(((d - tol) / 5.0 * mf).floor() as i128 - c as i128);
        hi.push(((d + tol) / 5.0 * mf).ceil() as i128 - c as i128);
    }
    let n = row.len();
    let mut gens = vec![row];
    for t in 1..n {
        let mut r = vec![0i128; n];
        r[t] = m64;
        gens.push(r);
    }
    let pts = match box_points(&gens, &lo, &hi, max_nodes) {
        Some(p) if !p.is_empty() => p,
        _ => return Ok(Vec::new()),
    };
    let mut states: Vec<u64> = pts.iter().map(|p| p[0].rem_euclid(m64) as u64).collect();
    states.sort();
    states.dedup();
    let mut best = score_gen(g, &states, v, sigma, measured, &jumps, pivot, cap, max_bias);
    best.sort_by(|a, b| a.score.partial_cmp(&b.score).unwrap());
    best.truncate(top);
    Ok(best)
}

/// search._score: robust chi-square of each state (the state after the pivot's rand).
pub fn score(states: &[u64], v: &[f64], sigma: &[f64], measured: &[usize], jumps: &[(u64, u64)], pivot: usize, cap: f64, max_bias: f64) -> Vec<Candidate> {
    score_gen(Gen::Gc, states, v, sigma, measured, jumps, pivot, cap, max_bias)
}

/// search._score for either generator (`jumps` from that generator).
#[allow(clippy::too_many_arguments)]
pub fn score_gen(g: Gen, states: &[u64], v: &[f64], sigma: &[f64], measured: &[usize], jumps: &[(u64, u64)], pivot: usize, cap: f64, max_bias: f64) -> Vec<Candidate> {
    let w: Vec<f64> = measured.iter().map(|&i| 1.0 / sigma[i].powi(2)).collect();
    let mut rows: Vec<(f64, f64, Vec<f64>, u64)> = states
        .iter()
        .map(|&st| {
            let dm: Vec<f64> = measured
                .iter()
                .map(|&i| speed(g, g.apply(jumps[i], st)) - v[i])
                .collect();
            let bias = median(&dm).clamp(-max_bias, max_bias);
            let res: Vec<f64> = dm.iter().map(|x| x - bias).collect();
            let total: f64 = res.iter().zip(&w).map(|(r, w)| (r * r * w).min(cap)).sum();
            (total, bias, res, st)
        })
        .collect();
    rows.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
    rows.truncate(10);
    let back = g.jump(-(pivot as i64 + 1));
    rows.into_iter()
        .map(|(total, bias, res, st)| {
            let mut r = vec![f64::NAN; v.len()];
            for (k, &i) in measured.iter().enumerate() {
                r[i] = res[k];
            }
            Candidate { letter_seed: g.apply(back, st) & g.seed_mask(), score: total, bias, residuals: r, distance: None }
        })
        .collect()
}

/// search.search_near: letter seeds within `max_dist` steps after `anchor`, all scored (GC).
pub fn search_near(v: &[f64], sigma: &[f64], anchor: u64, max_dist: u64, top: usize) -> Result<Vec<Candidate>, SearchError> {
    search_near_gen(Gen::Gc, v, sigma, anchor, max_dist, top)
}

/// search.search_near for either generator: every seed in the window is scored.
pub fn search_near_gen(g: Gen, v: &[f64], sigma: &[f64], anchor: u64, max_dist: u64, top: usize) -> Result<Vec<Candidate>, SearchError> {
    search_near_impl(g, v, sigma, anchor, max_dist, top, false)
}

/// The same over a wide window, with a quick reject on the 5 best-measured letters (7+ letters
/// only). About 5 times faster, but a true seed with 3 mistracked letters among those 5 is
/// skipped, so the normal chaining window uses `search_near_gen`.
pub fn search_near_quick(g: Gen, v: &[f64], sigma: &[f64], anchor: u64, max_dist: u64, top: usize) -> Result<Vec<Candidate>, SearchError> {
    search_near_impl(g, v, sigma, anchor, max_dist, top, true)
}

fn search_near_impl(g: Gen, v: &[f64], sigma: &[f64], anchor: u64, max_dist: u64, top: usize, quick: bool) -> Result<Vec<Candidate>, SearchError> {
    let (max_bias, cap) = (0.5, 16.0);
    let m: Vec<usize> = (0..v.len()).filter(|&i| v[i].is_finite() && sigma[i].is_finite()).collect();
    if m.len() < 2 {
        return Err(SearchError);
    }
    let n = v.len();
    let w: Vec<f64> = m.iter().map(|&i| 1.0 / sigma[i].powi(2)).collect();
    // rolling window of the next n rands after each candidate letter seed
    let anchor = if g == Gen::Gc { anchor & rng::MASK32 } else { anchor };
    let mut s = g.step(anchor);
    let mut window: std::collections::VecDeque<(u64, f64)> = std::collections::VecDeque::new();
    let mut t = s;
    for _ in 0..=n {
        window.push_back((t, speed(g, t)));
        t = g.step(t);
    }
    let mut best: Vec<Candidate> = Vec::new();
    let mut worst_kept = f64::INFINITY;
    let mut dm = vec![0.0; m.len()];
    // the 5 best-measured letters for the quick reject (only with 7+ letters, so 2 bad ones
    // among them still leave a fitting seed 3 close pairs)
    let mut pre: Vec<usize> = (0..m.len()).collect();
    pre.sort_by(|&a, &b| sigma[m[a]].partial_cmp(&sigma[m[b]]).unwrap());
    pre.truncate(if quick && m.len() >= 7 { 5 } else { 0 });
    let pre_tol = pre.iter().map(|&k| sigma[m[k]]).fold(0.0f64, f64::max) * 2.0 * 4.0 + 0.02;
    for d in 0..max_dist {
        // letter seed = anchor advanced d+1 = window[0].0; character i reads window[1+i]
        for (k, &i) in m.iter().enumerate() {
            dm[k] = window[1 + i].1 - v[i];
        }
        // quick reject: a fitting seed has nearly equal offsets on most letters (any 3 good ones
        // among the first 5 give 3 close pairs); a random one rarely does (about 2%)
        if pre.len() == 5 {
            let mut close = 0;
            for a in 0..5 {
                for b in a + 1..5 {
                    if (dm[pre[a]] - dm[pre[b]]).abs() < pre_tol {
                        close += 1;
                    }
                }
            }
            if close < 3 {
                window.pop_front();
                window.push_back((t, speed(g, t)));
                t = g.step(t);
                continue;
            }
        }
        let bias = median(&dm).clamp(-max_bias, max_bias);
        let mut total = 0.0;
        for (k, x) in dm.iter().enumerate() {
            total += ((x - bias).powi(2) * w[k]).min(cap);
        }
        if best.len() < top || total < worst_kept {
            let mut rr = vec![f64::NAN; n];
            for (k, &i) in m.iter().enumerate() {
                rr[i] = dm[k] - bias;
            }
            best.push(Candidate { letter_seed: window[0].0 & g.seed_mask(), score: total, bias, residuals: rr, distance: Some(d + 1) });
            best.sort_by(|a, b| a.score.partial_cmp(&b.score).unwrap());
            best.truncate(top);
            worst_kept = if best.len() < top { f64::INFINITY } else { best[best.len() - 1].score };
        }
        window.pop_front();
        window.push_back((t, speed(g, t)));
        t = g.step(t);
        s = window[0].0;
    }
    let _ = s;
    Ok(best)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn arr(x: &[Option<f64>]) -> Vec<f64> {
        x.iter().map(|y| y.unwrap_or(f64::NAN)).collect()
    }

    // Two real Switch entries (tcbtrio, USA: Emergence Cave 1 and 2), from p2seeds'
    // test_switch_rng.py: their seeds come from the letters alone and lie 16,424 draws apart.
    const EC1V: [Option<f64>; 14] = [Some(1.0396), Some(1.3043), Some(3.6543), Some(4.578), Some(0.6658), Some(2.4096), Some(3.282), Some(3.3495), Some(0.495), None, Some(0.4458), Some(4.8133), Some(1.8767), Some(0.8149)];
    const EC1S: [Option<f64>; 14] = [Some(0.0175), Some(0.0175), Some(0.0148), Some(0.0144), Some(0.0172), Some(0.0165), Some(0.016), Some(0.0156), Some(0.0187), None, Some(0.0187), Some(0.014), Some(0.0165), Some(0.0175)];
    const EC2V: [Option<f64>; 14] = [Some(0.872), Some(0.0331), Some(3.7353), Some(3.0966), Some(3.9416), Some(3.7342), Some(1.4785), Some(4.6278), Some(-0.0495), None, Some(1.9459), Some(1.7237), Some(3.842), Some(1.2074)];
    const EC2S: [Option<f64>; 14] = [Some(0.0182), Some(0.0189), Some(0.0149), Some(0.0162), Some(0.0149), Some(0.0149), Some(0.0167), Some(0.0141), Some(0.0189), None, Some(0.0167), Some(0.0163), Some(0.0149), Some(0.0177)];

    #[test]
    fn real_switch_entries_chain() {
        let g = Gen::Switch;
        let a = search_gen(g, &arr(&EC1V), &arr(&EC1S), &[], 2_000_000).ok().unwrap();
        let b = search_gen(g, &arr(&EC2V), &arr(&EC2S), &[], 2_000_000).ok().unwrap();
        assert!(a[0].score < 30.0 && b[0].score < 30.0, "{} {}", a[0].score, b[0].score);
        assert_eq!(a[0].letter_seed, g.next(0x306306F66F0443C4, -1));
        assert_eq!(g.distance(a[0].letter_seed, b[0].letter_seed), 16_424);
        // and EC2 from EC1 by the near search
        let c = search_near_gen(g, &arr(&EC2V), &arr(&EC2S), a[0].letter_seed, 100_000, 2).ok().unwrap();
        assert_eq!(c[0].letter_seed, b[0].letter_seed);
        assert_eq!(c[0].distance, Some(16_424));
    }

    #[test]
    fn near_search_with_quick_reject_finds_noisy_seed() {
        // 9 letters, one badly measured, offset 0.3: found 1,234,567 draws after the anchor
        for g in [Gen::Gc, Gen::Switch] {
            let anchor = 0x1357_9BDF_2468_ACE0u64 & if g == Gen::Gc { 0xFFFF_FFFF } else { u64::MAX };
            let seed = g.next(anchor, 1_234_567);
            let mut s = seed;
            let mut v = Vec::new();
            for i in 0..9 {
                s = g.step(s);
                let noise = [0.01, -0.02, 0.005, 0.015, -0.01, 0.0, 0.02, -0.005, 0.01][i];
                v.push(speed(g, s) + 0.3 + noise);
            }
            v[4] += 1.7; // a mistracked letter
            let sig = vec![0.015; 9];
            let c = search_near_gen(g, &v, &sig, anchor, 2_000_000, 2).ok().unwrap();
            assert_eq!(c[0].letter_seed, seed & g.seed_mask(), "{g:?}");
            assert_eq!(c[0].distance, Some(1_234_567));
            assert!(c[1].score - c[0].score > 15.0);
        }
    }

    #[test]
    fn switch_lattice_finds_synthetic_seed() {
        let g = Gen::Switch;
        let mut x: u64 = 0x9E37_79B9_7F4A_7C15;
        for trial in 0..5 {
            x = x.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            let seed = x;
            let mut s = seed;
            let off = ((x >> 20) % 400) as f64 / 1000.0 - 0.2;
            let mut v = Vec::new();
            for i in 0..14 {
                s = g.step(s);
                let noise = (((x >> (i * 3)) & 15) as f64 - 7.5) / 7.5 * 0.015;
                v.push(speed(g, s) - off + noise);
            }
            v[9] = f64::NAN;
            let sig: Vec<f64> = v.iter().map(|x| if x.is_nan() { f64::NAN } else { 0.015 }).collect();
            let c = search_gen(g, &v, &sig, &[], 2_000_000).ok().unwrap();
            assert_eq!(c[0].letter_seed, seed, "trial {trial}");
        }
    }
}
