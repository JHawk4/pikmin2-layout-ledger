//! Challenge Mode manip (CaveGen's `Manip.java` / `Seed.java`, modes attk, key, cmat, 700k).
//!
//! From the RNG state at the end of a results-screen score roll, every challenge level's floor 1
//! is generated for the next N seeds the level select can give, judged, and ranked. Each
//! (level, seed) option gets the frame window in which pressing A on the level select gives
//! that seed. The runner scrolls to the level and presses A when the countdown reaches zero.
//!
//! Timing (GameCube, 30 fps): frame 0 is the "Don't Save" press after the results screen. The
//! level select stays on `end + 4` for 61 + `seed_duration_first` frames, then on each next
//! state for `seed_duration` frames. Pressing A adds 1000 draws (the Pikmin dive), and the
//! menu keeps advancing for `frames_A_to_enter` frames before the level loads. Frame 0 is placed
//! `seconds_of_delay` before the last black frame of the fade that follows the results screen.

use std::collections::HashMap;
use std::io::{Read, Seek, SeekFrom};
use std::sync::OnceLock;

use cavegen3::jhawk_judge::{JhawkJudge, JudgeType};
use cavegen3::{GameData, Layout};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};

const MASK31: u64 = 0x7FFF_FFFF;

#[inline]
fn adv(s: u64, n: i64) -> u64 {
    p2live::rng::next_seed(s, n) & MASK31
}

#[inline]
fn rand15(s: u64) -> u64 {
    (s >> 16) & 0x7FFF
}

/// Frames the level select stays on state `s` before the next draw.
pub fn seed_duration(s: u64) -> i64 {
    16 + ((rand15(s) as f64 / 32768.0 * 0.9 + 0.1) * 300.0) as i64
}

/// The first wait on entering the level select.
pub fn seed_duration_first(s: u64) -> i64 {
    (rand15(s) as f64 / 32768.0 * 300.0) as i64
}

const DELAY_DONT_SAVE_TO_FIRST_ADVANCE: i64 = 61;
/// Frames between pressing A and the level loading, per level (CaveGen: "a rough estimation").
const FRAMES_BY_CAVE: [i64; 31] = [-1, 76, 76, 76, 84, 58, 56, 88, 68, 78, 82, 65, 61, 90, 79, 79, 77, 82, 80, 81, 96, 86, 79, 9, 80, 80, 64, 92, 97, 89, 85];

fn frames_a_to_enter(level: usize) -> i64 {
    8 + FRAMES_BY_CAVE[level]
}

/// The level seed from pressing A on menu state `cur` with `left` frames before its next draw.
#[allow(dead_code)]
pub fn seed_from_a(level: usize, cur: u64, left: i64) -> u64 {
    let mut frames_left = frames_a_to_enter(level);
    let mut s = adv(cur, 1000);
    let mut left = left;
    while left < frames_left {
        frames_left -= left;
        s = adv(s, 1);
        left = seed_duration(s);
    }
    s
}

/// (frame to press A, counted from "Don't Save", and the window in frames) to get `target` on
/// `level`, from the menu's first state `start`; `steps` = draws from `start` to `target - 1000`.
pub fn best_timing(level: usize, start: u64, target: u64, steps: i64) -> (i64, i64) {
    let (m1, m2, p1, p2) = (adv(target, -1), adv(target, -2), adv(target, 1), adv(target, 2));
    let mut cur = start;
    let mut before = DELAY_DONT_SAVE_TO_FIRST_ADVANCE + seed_duration_first(start);
    let mut frame = 0i64;
    let mut good: Vec<i64> = Vec::new();
    let (mut latest_early, mut earliest_late) = (-1i64, i64::MAX);
    let enter = frames_a_to_enter(level);
    let mut d = steps;
    if d < 0 {
        return (0, 0);
    }
    while d >= 0 {
        if d <= 3 {
            let mut thresh = before - enter;
            let mut res = adv(cur, 1000);
            for i in 0..before {
                while i > thresh {
                    res = adv(res, 1);
                    thresh += seed_duration(res);
                }
                if res == target {
                    good.push(frame + i);
                } else if res == m1 || res == m2 {
                    latest_early = latest_early.max(frame + i);
                } else if res == p1 || res == p2 {
                    earliest_late = earliest_late.min(frame + i);
                }
            }
        }
        frame += before;
        cur = adv(cur, 1);
        before = seed_duration(cur);
        d -= 1;
    }
    if good.is_empty() {
        return ((earliest_late.saturating_add(latest_early)) / 2, 0.min(earliest_late.saturating_sub(latest_early)));
    }
    let (mut best_start, mut best_len, mut cur_start) = (0usize, 0usize, 0usize);
    for i in 0..good.len() {
        if !(i > 0 && good[i] == good[i - 1] + 1) {
            cur_start = i;
        }
        if i - cur_start + 1 > best_len {
            best_len = i - cur_start + 1;
            best_start = cur_start;
        }
    }
    (good[best_start + best_len / 2], best_len as i64)
}

// ------------------------------------------------------------------------------------------
// ranks (CaveGen's rank_file: 1000 ascending score breakpoints per sublevel and judge; lower
// scores are better)

const RANK_FILE: &str = include_str!("../data/ch_rank_file.txt");

fn rank_file() -> &'static HashMap<String, Vec<f64>> {
    static R: OnceLock<HashMap<String, Vec<f64>>> = OnceLock::new();
    R.get_or_init(|| {
        RANK_FILE
            .lines()
            .filter_map(|l| {
                let (k, rest) = l.split_once(';')?;
                let v: Vec<f64> = rest.split(';').filter_map(|x| x.trim().parse().ok()).collect();
                (v.len() >= 1000).then(|| (k.to_string(), v[..1000].to_vec()))
            })
            .collect()
    })
}

/// Judge.scoreToRank: the percentile (0 best .. 100) of a score among random seeds.
pub fn score_to_rank(bp: &[f64], score: f64) -> f64 {
    let score = (100.0 * score).round() / 100.0;
    if score < bp[0] {
        return 0.0;
    }
    if score > bp[999] {
        return 100.0;
    }
    let (mut lo, mut hi) = (0usize, 999usize);
    while lo + 1 < hi {
        let mid = (hi + lo) / 2;
        if score <= bp[mid] {
            hi = mid;
        } else {
            lo = mid;
        }
    }
    if bp[hi] == score {
        lo = hi;
    }
    let mut dupes = 0;
    for v in &bp[lo + 1..] {
        if *v == score {
            dupes += 1;
        } else {
            break;
        }
    }
    (lo + dupes / 2) as f64 / 10.0
}

#[derive(Clone, Debug, Default)]
struct Stats {
    mean: f64,
    stddev: f64,
    top: f64,
}

fn stats(id: &str, kind: &str) -> Option<Stats> {
    let r = rank_file().get(&format!("{id}-{kind}"))?;
    let (mut x, mut x2) = (0.0, 0.0);
    for &v in r {
        let k = if v >= 100000.0 { r[500] + 40.0 } else { v };
        x += k;
        x2 += k * k;
    }
    x /= r.len() as f64;
    Some(Stats { mean: x, stddev: (x2 / r.len() as f64 - x * x).max(0.0).sqrt(), top: r[r.len() * 5 / 100] })
}

/// sqrt of the summed variance of a level's floors 2+ (what cannot be manipulated).
fn late_stdev(level: usize, kind: &str) -> f64 {
    let mut v = 0.0;
    for f in 2..=10 {
        match stats(&format!("CH{level}-{f}"), kind) {
            Some(s) => v += s.stddev * s.stddev,
            None => break,
        }
    }
    v.sqrt()
}

// ------------------------------------------------------------------------------------------
// settings

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ChMode {
    /// Score attack: single levels, the best-ranked layouts of the levels you want to play.
    Attk,
    /// Full-game runs to the key, all 30 levels (CMAL "key").
    Key,
    /// Full-game runs collecting all treasures (CMAL "cmat").
    Cmat,
    /// 700k: scored with the score-attack judge (CaveGen's own 700k judge was never finished).
    #[serde(rename = "700k")]
    K700,
}

impl ChMode {
    pub fn kind(self) -> &'static str {
        match self {
            ChMode::Attk | ChMode::K700 => "attk",
            ChMode::Key => "key",
            ChMode::Cmat => "cmat",
        }
    }
    pub fn realtime(self) -> bool {
        self != ChMode::Attk
    }
    pub fn label(self) -> &'static str {
        match self {
            ChMode::Attk => "Challenge: score attack (attk)",
            ChMode::Key => "Challenge: all levels, key (key)",
            ChMode::Cmat => "Challenge: all levels, treasures (cmat)",
            ChMode::K700 => "Challenge: 700k",
        }
    }
}

/// CaveGen's manip parameters (config.txt), with its defaults.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ManipSettings {
    /// score attack: levels to play (preferred) and to ignore
    pub levels_to_play: Vec<usize>,
    pub levels_to_ignore: Vec<usize>,
    /// score attack: only layouts in the best this-many percent
    pub rank_threshold: f64,
    /// score attack: how far ahead (seconds of menu waiting) seeds are considered
    pub max_wait_s: f64,
    /// full-game modes: seconds of menu waiting considered for the first level
    pub first_level_wait_s: f64,
    pub give_up_per_second_vol: f64,
    pub give_up_per_second_wait: f64,
    /// frame 0 ("Don't Save") is this long before the last black frame after the results
    pub seconds_of_delay: f64,
    pub frames_needed_for_window: i64,
    pub frames_to_select_level: i64,
    pub frames_to_scroll_level: i64,
    /// CaveGen's times tables (4 GiB each), per kind; without one, full-game modes plan greedily
    pub times_tables: HashMap<String, String>,
}

impl Default for ManipSettings {
    fn default() -> Self {
        ManipSettings {
            levels_to_play: vec![4, 9, 10, 12, 24, 27],
            levels_to_ignore: vec![1, 2, 3, 5, 6, 7, 11, 13, 14, 16, 17, 19, 22, 23, 25, 26, 30],
            rank_threshold: 3.0,
            max_wait_s: 180.0,
            first_level_wait_s: 180.0,
            give_up_per_second_vol: 0.5,
            give_up_per_second_wait: 0.03,
            seconds_of_delay: 2.0,
            frames_needed_for_window: 10,
            frames_to_select_level: 60,
            frames_to_scroll_level: 20,
            times_tables: HashMap::new(),
        }
    }
}

/// CaveGen's times table: 2^30 big-endian f32, indexed by the set of levels still to play.
fn times_table(path: &str, mask: u32) -> Option<f64> {
    let mut f = std::fs::File::open(path).ok()?;
    f.seek(SeekFrom::Start(4 * mask as u64)).ok()?;
    let mut b = [0u8; 4];
    f.read_exact(&mut b).ok()?;
    Some(f32::from_be_bytes(b) as f64)
}

// ------------------------------------------------------------------------------------------
// the plan

#[derive(Clone, Debug, Serialize)]
pub struct Option_ {
    pub level: usize,
    /// draws after the first seed considered (end + 1004)
    pub advances: usize,
    pub seed: u64,
    pub score: f64,
    pub rank: f64,
    /// the score against the level's top 5% (attk) or its average (full-game modes)
    pub delta: f64,
    /// level select moves from the last level's cell
    pub scroll: String,
    /// press A this many frames after frame 0 ("Don't Save"), within `window` frames
    pub target_frame: i64,
    pub window: i64,
    pub cost: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Plan {
    pub mode: ChMode,
    /// the roll's last draw (31 bits)
    pub end_state: u64,
    pub options: Vec<Option_>,
    /// full-game modes planned without a times table
    pub greedy: bool,
}

/// Levels played so far and the level the menu cursor is on.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct RunState {
    pub played: Vec<usize>,
    /// the cursor's level (CaveGen assumes CH8 before the first level)
    pub last: Option<usize>,
}

fn game() -> Option<&'static GameData> {
    static G: OnceLock<Option<GameData>> = OnceLock::new();
    G.get_or_init(|| GameData::from_dir(crate::engine::cavegen_data()).ok()).as_ref()
}

/// Judge floor 1 of every level for `n` seeds from `first`: (level, i) -> score.
fn judge_all(first: u64, n: usize, kind: &str) -> Result<HashMap<(usize, usize), f64>, String> {
    let data = game().ok_or("CaveGen3 data not found")?;
    let jt: JudgeType = kind.parse()?;
    let jobs: Vec<(usize, usize)> = (1..=30).flat_map(|l| (0..n).map(move |i| (l, i))).collect();
    let infos: HashMap<usize, &cavegen3::caveinfo::CaveInfo> = (1..=30)
        .filter_map(|l| {
            let sl = data.sublevel(&format!("CH{l}-1")).ok()?;
            Some((l, data.caveinfo(&sl).ok()?))
        })
        .collect();
    let judges: HashMap<usize, JhawkJudge> = infos.iter().map(|(&l, ci)| (l, JhawkJudge::new(jt, ci))).collect();
    Ok(jobs
        .par_iter()
        .filter_map(|&(l, i)| {
            let ci = infos.get(&l)?;
            let seed = adv(first, i as i64) as u32;
            Some(((l, i), judges[&l].judge(&Layout::generate(seed, ci))))
        })
        .collect())
}

/// The options after a roll that ended on `end` (the state of its last draw).
pub fn plan(mode: ChMode, end: u64, run: &RunState, cfg: &ManipSettings) -> Result<Plan, String> {
    let end = end & MASK31;
    let first_level = run.played.is_empty();
    let n = if mode.realtime() {
        if first_level { (cfg.first_level_wait_s / 5.0) as usize } else { 5 }
    } else {
        (cfg.max_wait_s / 5.0) as usize
    }
    .max(1);
    let kind = mode.kind();
    let start = adv(end, 4);
    let first = adv(end, 1004);
    let scores = judge_all(first, n, kind)?;
    let last = run.last.unwrap_or(8);

    // menu waits before each seed, in frames
    let mut waits = vec![0i64; n];
    if n > 1 {
        waits[1] = seed_duration_first(start);
        for i in 2..n {
            waits[i] = waits[i - 1] + seed_duration(adv(end, 4 + i as i64 - 1));
        }
    }
    if mode.realtime() && first_level {
        for w in waits.iter_mut() {
            *w = (*w as f64 * cfg.give_up_per_second_wait) as i64;
        }
    }
    let scroll = |l: usize| -> (i64, String) {
        let (rl, cl) = ((last - 1) / 5, (last - 1) % 5);
        let (ri, ci) = ((l - 1) / 5, (l - 1) % 5);
        let rd = (ri + 6 - rl) % 6;
        let cd = (ci + 5 - cl) % 5;
        let steps = rd.min(6 - rd) + cd.min(5 - cd);
        let s = format!("{}{}", ["", "D", "DD", "DDD", "UU", "U"][rd], ["", "R", "RR", "LL", "L"][cd]);
        (cfg.frames_to_scroll_level * steps as i64, s)
    };

    let unplayed: u32 = (1..=30).filter(|l| !run.played.contains(l)).fold(0u32, |m, l| m | 1 << (l - 1));
    let table = cfg.times_tables.get(kind).filter(|p| std::path::Path::new(p).is_file());
    let mut options = Vec::new();
    for l in 1..=30 {
        let Some(st) = stats(&format!("CH{l}-1"), kind) else { continue };
        let bp = &rank_file()[&format!("CH{l}-1-{kind}")];
        let (scroll_frames, scroll_seq) = scroll(l);
        let orpg = late_stdev(l, kind) * cfg.give_up_per_second_vol * (1.0 - run.played.len() as f64 / 30.0);
        let remaining = if mode.realtime() { table.and_then(|p| times_table(p, unplayed & !(1 << (l - 1)))).unwrap_or(0.0) } else { 0.0 };
        for i in 0..n {
            let Some(&score) = scores.get(&(l, i)) else { continue };
            let rank = score_to_rank(bp, score);
            let (delta, cost) = if mode.realtime() {
                let delta = score - st.mean;
                let wait = scroll_frames.max(waits[i]) as f64 / 30.0;
                (delta, wait + remaining + delta - orpg + if run.played.contains(&l) { 1000.0 } else { 0.0 })
            } else {
                let delta = score - st.top;
                let mut t = delta + (rank - cfg.rank_threshold);
                if cfg.levels_to_play.contains(&l) {
                    t -= 15.0;
                }
                if cfg.levels_to_ignore.contains(&l) || run.played.contains(&l) {
                    t += 100000.0;
                }
                if rank > cfg.rank_threshold {
                    t += 100000.0;
                }
                (delta, t)
            };
            options.push(Option_ { level: l, advances: i, seed: adv(first, i as i64), score, rank, delta, scroll: scroll_seq.clone(), target_frame: 0, window: 0, cost });
        }
    }
    options.sort_by(|a, b| a.cost.partial_cmp(&b.cost).unwrap());
    let show = if !mode.realtime() || first_level { 30 } else { 5 };
    let mut out = Vec::new();
    for mut o in options {
        if out.len() >= show {
            break;
        }
        let (f, w) = best_timing(o.level, start, o.seed, o.advances as i64);
        if w <= cfg.frames_needed_for_window || f + w / 2 < cfg.frames_to_select_level + scroll(o.level).0 {
            continue;
        }
        o.target_frame = f;
        o.window = w;
        out.push(o);
    }
    Ok(Plan { mode, end_state: end, options: out, greedy: mode.realtime() && table.is_none() })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn durations_in_range() {
        for s in [0u64, 0x7FFF_FFFF, 0x1234_5678] {
            assert!((46..=316).contains(&seed_duration(s)));
            assert!((0..300).contains(&seed_duration_first(s)));
        }
    }

    #[test]
    fn a_press_adds_1000() {
        // with plenty of frames left before the next draw, A gives cur + 1000
        let s = 0x0404_7550;
        assert_eq!(seed_from_a(11, s, 10_000), adv(s, 1000));
    }

    #[test]
    fn timing_window_exists() {
        // the first seed considered (end + 1004): A on the menu's first state
        let end = 0x0404_7550u64;
        let start = adv(end, 4);
        let target = adv(end, 1004);
        let (f, w) = best_timing(11, start, target, 0);
        assert!(w > 0 && f >= 0, "{f} {w}");
    }

    #[test]
    fn rank_of_extremes() {
        let bp = &rank_file()["CH4-1-attk"];
        assert_eq!(score_to_rank(bp, -1e9), 0.0);
        assert_eq!(score_to_rank(bp, 1e9), 100.0);
    }
}
