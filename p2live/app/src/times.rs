//! Times tables for the full-game Challenge Mode manips (key, cmat, 700k), 900 numbers each.
//!
//! CaveGen's table (`seed timestable`) stores, for every set S of levels still to play (2^30 of
//! them, 4 GiB), the expected time the rest of the run spends against the levels' averages if
//! each round offers one random floor-1 layout per remaining level and the runner always takes
//! the best "this layout + the rest":
//!
//! ```text
//! t[S] = E_draw min_{j in S} ( x_j - avg_j + t[S \ j] )
//! ```
//!
//! `t[S]` is very nearly additive: `t[S] ~ sum_{j in S} w_j(|S|)`, one number per level and set
//! size (30 x 30). Fitted to CaveGen's real key table, that is within 0.1-0.6 s, and planning with
//! it loses about 1 s per simulated 30-level run. So the table is built that way directly
//! ("fitted value iteration"): for each set size n, sample sets of n levels, evaluate the formula
//! above with the size n-1 numbers, and fit the size n numbers by least squares.
//!
//! The layouts are CaveGen3's: `samples` random floor-1 layouts per level, judged with the
//! mode's judge. A floor that spawns no key costs the level's average + `NO_KEY_PENALTY_S`
//! (the runner resets and replays the level), not CaveGen's flat 300 (key) or 500 (cmat).
//! Draws are independent per level (CaveGen's table paired the levels' samples in one fixed
//! shuffle).
//!
//! `p2live-app --build-times OUT_DIR [--samples N]` writes `times_<kind>.json`; the app embeds
//! the ones in `data/`.

use std::sync::OnceLock;

use cavegen3::jhawk_judge::{JhawkJudge, JudgeType};
use cavegen3::{GameData, Layout};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};

/// Seconds over the level's average when floor 1 has no key: reset and play it again.
pub const NO_KEY_PENALTY_S: f64 = 120.0;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LevelStats {
    pub level: usize,
    /// mean score with no-key floors counted at `mean_valid + NO_KEY_PENALTY_S`
    pub mean: f64,
    /// mean over floors that have a key
    pub mean_valid: f64,
    pub stddev: f64,
    /// share of floors with no key
    pub no_key: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TimesTable {
    pub kind: String,
    /// random layouts judged per level
    pub samples: usize,
    pub levels: Vec<LevelStats>,
    /// `w[n][j]`: level j+1's share of t[S] for sets S of n levels (n = 0..=30)
    pub w: Vec<Vec<f64>>,
}

impl TimesTable {
    /// Expected time against the averages for the levels in `mask` (bit l-1 = level l) still
    /// to play.
    pub fn value(&self, mask: u32) -> f64 {
        let n = mask.count_ones() as usize;
        (0..30).filter(|j| mask & 1 << j != 0).map(|j| self.w[n][j]).sum()
    }

    pub fn level(&self, l: usize) -> Option<&LevelStats> {
        self.levels.iter().find(|s| s.level == l)
    }
}

/// The embedded tables (built with `--build-times`), by judge kind.
pub fn embedded(kind: &str) -> Option<&'static TimesTable> {
    static T: OnceLock<Vec<TimesTable>> = OnceLock::new();
    T.get_or_init(|| {
        [include_str!("../data/times_key.json"), include_str!("../data/times_cmat.json"), include_str!("../data/times_attk.json")]
            .iter()
            .filter_map(|s| serde_json::from_str(s).ok())
            .collect()
    })
    .iter()
    .find(|t| t.kind == kind)
}

/// Whether a judged floor has no key: CaveGen3's key judge then walks 300 s, and the cmat
/// judge returns exactly 500. `cmat` is that level's cmat judge, asked only when needed.
pub fn missing_key(kind: &str, score: f64, layout: &Layout, cmat: &JhawkJudge) -> bool {
    match kind {
        "key" => score >= 300.0 && cmat.judge(layout) == 500.0,
        "cmat" => score == 500.0,
        _ => false,
    }
}

struct SplitMix(u64);
impl SplitMix {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    fn below(&mut self, n: usize) -> usize {
        ((self.next() >> 11) as f64 / (1u64 << 53) as f64 * n as f64) as usize
    }
}

/// Judge `samples` random floor-1 layouts of every level: per level, the excess over its mean
/// of each sample (no-key floors penalized), and its stats.
fn sample_levels(data: &GameData, kind: &str, samples: usize, log: &dyn Fn(&str)) -> Result<(Vec<LevelStats>, Vec<Vec<f64>>), String> {
    let jt: JudgeType = kind.parse()?;
    let jc: JudgeType = "cmat".parse()?;
    let mut stats = Vec::new();
    let mut excess = Vec::new();
    for l in 1..=30 {
        let t = std::time::Instant::now();
        let sl = data.sublevel(&format!("CH{l}-1")).map_err(|e| e.to_string())?;
        let ci = data.caveinfo(&sl).map_err(|e| e.to_string())?;
        let (judge, cmat) = (JhawkJudge::new(jt, ci), JhawkJudge::new(jc, ci));
        let scores: Vec<(f64, bool)> = (0..samples)
            .into_par_iter()
            .map(|i| {
                let seed = SplitMix(((l as u64) << 40) ^ (i as u64) ^ 0x5EED_0000).next() as u32;
                let layout = Layout::generate(seed, ci);
                let s = judge.judge(&layout);
                (s, missing_key(kind, s, &layout, &cmat))
            })
            .collect();
        let valid: Vec<f64> = scores.iter().filter(|s| !s.1).map(|s| s.0).collect();
        let mean_valid = valid.iter().sum::<f64>() / valid.len().max(1) as f64;
        let xs: Vec<f64> = scores.iter().map(|&(s, nk)| if nk { mean_valid + NO_KEY_PENALTY_S } else { s }).collect();
        let mean = xs.iter().sum::<f64>() / xs.len() as f64;
        let var = xs.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / xs.len() as f64;
        let no_key = (samples - valid.len()) as f64 / samples as f64;
        log(&format!("CH{l}-1 {kind}: mean {mean:.2} (with a key {mean_valid:.2}), sd {:.2}, no key {:.3}% ({:.1} s)", var.sqrt(), 100.0 * no_key, t.elapsed().as_secs_f64()));
        stats.push(LevelStats { level: l, mean, mean_valid, stddev: var.sqrt(), no_key });
        excess.push(xs.iter().map(|x| x - mean).collect());
    }
    Ok((stats, excess))
}

fn binom(n: usize, k: usize) -> f64 {
    (0..k).fold(1.0, |a, i| a * (n - i) as f64 / (i + 1) as f64)
}

/// Least squares for w in A w = y, where each row of A is the 0/1 indicator of a set; a tiny
/// ridge keeps underdetermined sizes (n = 30: one set) at the even split.
fn fit(sets: &[Vec<usize>], ys: &[f64]) -> Vec<f64> {
    let mut m = vec![[0.0f64; 31]; 30];
    for (s, &y) in sets.iter().zip(ys) {
        for &i in s {
            for &j in s {
                m[i][j] += 1.0;
            }
            m[i][30] += y;
        }
    }
    let ridge = 1e-6 * sets.len() as f64;
    for (i, row) in m.iter_mut().enumerate() {
        row[i] += ridge;
    }
    // Gauss-Jordan with partial pivoting
    for c in 0..30 {
        let p = (c..30).max_by(|&a, &b| m[a][c].abs().total_cmp(&m[b][c].abs())).unwrap();
        m.swap(c, p);
        let d = m[c][c];
        for k in c..31 {
            m[c][k] /= d;
        }
        for r in 0..30 {
            if r != c && m[r][c] != 0.0 {
                let f = m[r][c];
                for k in c..31 {
                    m[r][k] -= f * m[c][k];
                }
            }
        }
    }
    m.iter().map(|r| r[30]).collect()
}

/// Fitted value iteration over set sizes 1..=30.
fn value_iteration(excess: &[Vec<f64>], sets_per_size: usize, draws: usize, seed: u64, log: &dyn Fn(&str)) -> Vec<Vec<f64>> {
    let mut w = vec![vec![0.0; 30]; 31];
    let mut rng = SplitMix(seed);
    for n in 1..=30 {
        let all = binom(30, n);
        let sets: Vec<Vec<usize>> = if all <= sets_per_size as f64 {
            // every set: the k-subsets of 0..30 in order
            let mut out = Vec::new();
            let mut c: Vec<usize> = (0..n).collect();
            loop {
                out.push(c.clone());
                let mut i = n;
                while i > 0 && c[i - 1] == 30 - n + i - 1 {
                    i -= 1;
                }
                if i == 0 {
                    break;
                }
                c[i - 1] += 1;
                for k in i..n {
                    c[k] = c[k - 1] + 1;
                }
            }
            out
        } else {
            let mut seen = std::collections::HashSet::new();
            while seen.len() < sets_per_size {
                let mut pool: Vec<usize> = (0..30).collect();
                for i in 0..n {
                    let k = i + rng.below(30 - i);
                    pool.swap(i, k);
                }
                let mut s = pool[..n].to_vec();
                s.sort();
                seen.insert(s);
            }
            seen.into_iter().collect()
        };
        let prev = &w[n - 1];
        let seeds: Vec<u64> = (0..sets.len()).map(|_| rng.next()).collect();
        let ys: Vec<f64> = sets
            .par_iter()
            .zip(&seeds)
            .map(|(s, &sd)| {
                let total: f64 = s.iter().map(|&j| prev[j]).sum();
                let mut r = SplitMix(sd);
                let mut acc = 0.0;
                for _ in 0..draws {
                    let mut best = f64::INFINITY;
                    for &j in s {
                        let x = &excess[j];
                        let v = x[r.below(x.len())] + total - prev[j];
                        best = best.min(v);
                    }
                    acc += best;
                }
                acc / draws as f64
            })
            .collect();
        w[n] = fit(&sets, &ys);
        if n % 5 == 0 || n == 1 {
            log(&format!("sets of {n:>2}: {} sets, t[all such] mean {:.1}", sets.len(), ys.iter().sum::<f64>() / ys.len() as f64));
        }
    }
    w
}

pub fn build(data: &GameData, kind: &str, samples: usize, log: &dyn Fn(&str)) -> Result<TimesTable, String> {
    let (levels, excess) = sample_levels(data, kind, samples, log)?;
    let w = value_iteration(&excess, 3000, 4000, 0x7AB1E ^ kind.len() as u64, log);
    log(&format!("{kind}: t[all 30 levels] = {:.1} s", w[30].iter().sum::<f64>()));
    Ok(TimesTable { kind: kind.to_string(), samples, levels, w })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fit_recovers_additive_values() {
        // y = sum of known w over random sets
        let truth: Vec<f64> = (0..30).map(|i| i as f64 * 0.5 - 7.0).collect();
        let mut r = SplitMix(1);
        let sets: Vec<Vec<usize>> = (0..400)
            .map(|_| {
                let mut s: Vec<usize> = (0..30).filter(|_| r.below(2) == 1).collect();
                if s.is_empty() {
                    s.push(0);
                }
                s
            })
            .collect();
        let ys: Vec<f64> = sets.iter().map(|s| s.iter().map(|&j| truth[j]).sum()).collect();
        let w = fit(&sets, &ys);
        for (a, b) in w.iter().zip(&truth) {
            assert!((a - b).abs() < 1e-3, "{a} {b}");
        }
    }

    #[test]
    fn one_level_is_its_mean_excess() {
        // a single level left: t = E[x - avg] = 0
        let excess: Vec<Vec<f64>> = (0..30).map(|j| vec![-(j as f64), j as f64]).collect();
        let w = value_iteration(&excess, 100, 20000, 3, &|_| {});
        for j in 0..30 {
            assert!(w[1][j].abs() < 0.1 * (j as f64 + 1.0), "{j} {}", w[1][j]);
        }
        // two levels: E min(x, y) < 0
        assert!(w[2].iter().sum::<f64>() < 0.0);
    }

    #[test]
    fn embedded_tables_load() {
        for k in ["key", "cmat", "attk"] {
            let t = embedded(k).expect(k);
            assert_eq!(t.w.len(), 31);
            assert!(t.value((1 << 30) - 1) < 0.0);
        }
    }
}
