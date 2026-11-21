//! Seed search by lattice reduction (lattice.py), candidate scoring (search._score) and the
//! search near a known seed (search.search_near).

use crate::img::{median, pyround};
use crate::rng;

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

/// lattice.search (k_tol 4, max_bias 0.5, cap 16, top 5, max_dim 8).
pub fn search(v: &[f64], sigma: &[f64], leave_out: &[usize], max_nodes: usize) -> Result<Vec<Candidate>, SearchError> {
    let (k_tol, max_bias, cap, top, max_dim) = (4.0, 0.5, 16.0, 5, 8);
    let measured: Vec<usize> = (0..v.len()).filter(|&i| v[i].is_finite() && sigma[i].is_finite() && !leave_out.contains(&i)).collect();
    if measured.len() < 3 {
        return Err(SearchError);
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

/// search._score: robust chi-square of each state (the state after the pivot's rand).
pub fn score(states: &[u64], v: &[f64], sigma: &[f64], measured: &[usize], jumps: &[(u64, u64)], pivot: usize, cap: f64, max_bias: f64) -> Vec<Candidate> {
    let w: Vec<f64> = measured.iter().map(|&i| 1.0 / sigma[i].powi(2)).collect();
    let mut rows: Vec<(f64, f64, Vec<f64>, u64)> = states
        .iter()
        .map(|&st| {
            let dm: Vec<f64> = measured
                .iter()
                .map(|&i| rng::rand_of_state(rng::apply(jumps[i], st)) as f64 * V_PER_RAND - v[i])
                .collect();
            let bias = median(&dm).clamp(-max_bias, max_bias);
            let res: Vec<f64> = dm.iter().map(|x| x - bias).collect();
            let total: f64 = res.iter().zip(&w).map(|(r, w)| (r * r * w).min(cap)).sum();
            (total, bias, res, st)
        })
        .collect();
    rows.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
    rows.truncate(10);
    let back = rng::jump(-(pivot as i64 + 1));
    rows.into_iter()
        .map(|(total, bias, res, st)| {
            let mut r = vec![f64::NAN; v.len()];
            for (k, &i) in measured.iter().enumerate() {
                r[i] = res[k];
            }
            Candidate { letter_seed: rng::apply(back, st) & rng::MASK31, score: total, bias, residuals: r, distance: None }
        })
        .collect()
}

/// search.search_near: letter seeds within `max_dist` steps after `anchor`, all scored.
pub fn search_near(v: &[f64], sigma: &[f64], anchor: u64, max_dist: u64, top: usize) -> Result<Vec<Candidate>, SearchError> {
    let (max_bias, cap) = (0.5, 16.0);
    let m: Vec<usize> = (0..v.len()).filter(|&i| v[i].is_finite() && sigma[i].is_finite()).collect();
    if m.len() < 2 {
        return Err(SearchError);
    }
    let n = v.len();
    let w: Vec<f64> = m.iter().map(|&i| 1.0 / sigma[i].powi(2)).collect();
    // rolling window of the next n rands after each candidate letter seed
    let mut s = rng::step(anchor & rng::MASK32);
    let mut window: std::collections::VecDeque<(u64, f64)> = std::collections::VecDeque::new();
    let mut t = s;
    for _ in 0..=n {
        window.push_back((t, rng::rand_of_state(t) as f64 * V_PER_RAND));
        t = rng::step(t);
    }
    let mut best: Vec<Candidate> = Vec::new();
    let mut worst_kept = f64::INFINITY;
    let mut dm = vec![0.0; m.len()];
    for d in 0..max_dist {
        // letter seed = anchor advanced d+1 = window[0].0; character i reads window[1+i]
        for (k, &i) in m.iter().enumerate() {
            dm[k] = window[1 + i].1 - v[i];
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
            best.push(Candidate { letter_seed: window[0].0 & rng::MASK31, score: total, bias, residuals: rr, distance: Some(d + 1) });
            best.sort_by(|a, b| a.score.partial_cmp(&b.score).unwrap());
            best.truncate(top);
            worst_kept = if best.len() < top { f64::INFINITY } else { best[best.len() - 1].score };
        }
        window.pop_front();
        window.push_back((t, rng::rand_of_state(t) as f64 * V_PER_RAND));
        t = rng::step(t);
        s = window[0].0;
    }
    let _ = s;
    Ok(best)
}
