//! Challenge Mode manip (CaveGen's `Manip.java` / `Seed.java`, modes attk, key, cmat, 700k).
//!
//! From the RNG state at the end of a results-screen score roll, every challenge level's floor 1
//! is generated for the next N seeds the level select can give, judged, and ranked. Each
//! (level, seed) option gets the frame window in which pressing A on the level select gives
//! that seed. The runner scrolls to the level and presses A when the countdown reaches zero.
//!
//! Timing (30 fps): frame 0 is the "Don't Save" press after the results screen. The level select
//! stays on `end + 4` for 61 + `seed_duration_first` frames, then on each next state for
//! `seed_duration` frames. Pressing A adds 1000 draws (the Pikmin dive), and the menu keeps
//! advancing for `frames_A_to_enter` frames before the level loads. Frame 0 is placed
//! `seconds_of_delay` before the last black frame of the fade that follows the results screen.
//!
//! On Switch the same code runs with musl's `rand()` (`Gen::Switch`): the durations read
//! `rand() / RAND_MAX` at 31 bits. CaveGen's frame tables are GameCube's; that they hold on
//! Switch (an emulator at a locked 30 fps) is an assumption, not checked on video.

use std::collections::HashMap;
use std::io::{Read, Seek, SeekFrom};
use std::sync::OnceLock;

use cavegen3::jhawk_judge::{JhawkJudge, JudgeType};
use cavegen3::{GameData, Layout};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};

use crate::rng::Gen;
use crate::times::{self, missing_key, TimesTable, NO_KEY_PENALTY_S};

/// Frames the level select stays on state `s` before the next draw.
pub fn seed_duration(g: Gen, s: u64) -> i64 {
    16 + ((g.frac(s) * 0.9 + 0.1) * 300.0) as i64
}

/// The first wait on entering the level select.
pub fn seed_duration_first(g: Gen, s: u64) -> i64 {
    (g.frac(s) * 300.0) as i64
}

pub const DELAY_DONT_SAVE_TO_FIRST_ADVANCE: i64 = 61;
/// Draws from pressing A on the level select to the level's seed (the Pikmin dive).
pub const A_PRESS: i64 = 1000;
/// Draws from the roll's last digit to the level select's first state.
pub const ROLL_TO_MENU: i64 = 4;
/// Draws one title-screen loop adds (idling on the level select into the title demo and back).
pub const TITLE_LOOP: i64 = 4505;
/// Frames between pressing A and the level loading, per level (CaveGen: "a rough estimation").
pub const FRAMES_BY_CAVE: [i64; 31] = [-1, 76, 76, 76, 84, 58, 56, 88, 68, 78, 82, 65, 61, 90, 79, 79, 77, 82, 80, 81, 96, 86, 79, 9, 80, 80, 64, 92, 97, 89, 85];

pub fn frames_a_to_enter(level: usize) -> i64 {
    8 + FRAMES_BY_CAVE[level]
}

/// The level seed from pressing A on menu state `cur` with `left` frames before its next draw.
#[allow(dead_code)]
pub fn seed_from_a(g: Gen, level: usize, cur: u64, left: i64) -> u64 {
    let mut frames_left = frames_a_to_enter(level);
    let mut s = g.next(cur, A_PRESS);
    let mut left = left;
    while left < frames_left {
        frames_left -= left;
        s = g.next(s, 1);
        left = seed_duration(g, s);
    }
    s
}

/// The menu's state `frames` frames after "Don't Save", from its first state `start`, and the
/// draws taken (the menu advances at 61 + seed_duration_first, then every seed_duration).
pub fn menu_state_at(g: Gen, start: u64, frames: i64) -> (u64, i64) {
    let mut cur = start;
    let mut at = DELAY_DONT_SAVE_TO_FIRST_ADVANCE + seed_duration_first(g, start);
    let mut n = 0;
    while at <= frames {
        cur = g.next(cur, 1);
        n += 1;
        at += seed_duration(g, cur);
    }
    (cur, n)
}

/// (frame to press A, counted from "Don't Save", and the window in frames) to get `target` on
/// `level`, from the menu's first state `start`; `steps` = draws from `start` to `target - 1000`.
pub fn best_timing(g: Gen, level: usize, start: u64, target: u64, steps: i64) -> (i64, i64) {
    let (m1, m2, p1, p2) = (g.next(target, -1), g.next(target, -2), g.next(target, 1), g.next(target, 2));
    let mut cur = start;
    let mut before = DELAY_DONT_SAVE_TO_FIRST_ADVANCE + seed_duration_first(g, start);
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
            let mut res = g.next(cur, A_PRESS);
            for i in 0..before {
                while i > thresh {
                    res = g.next(res, 1);
                    thresh += seed_duration(g, res);
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
        cur = g.next(cur, 1);
        before = seed_duration(g, cur);
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
    /// the mean over floors that have a key
    mean_valid: f64,
    stddev: f64,
    top: f64,
}

/// A sublevel's score stats from the rank file. The judges' "no key" values (CaveGen's 100000,
/// CaveGen3's 300 for key and 500 for cmat) count as the average + NO_KEY_PENALTY_S.
fn stats(id: &str, kind: &str) -> Option<Stats> {
    let r = rank_file().get(&format!("{id}-{kind}"))?;
    let no_key = |v: f64| v >= 100000.0 || (kind == "key" && v >= 300.0) || (kind == "cmat" && v == 500.0);
    let valid: Vec<f64> = r.iter().copied().filter(|&v| !no_key(v)).collect();
    let mv = valid.iter().sum::<f64>() / valid.len().max(1) as f64;
    let (mut x, mut x2) = (0.0, 0.0);
    for &v in r {
        let k = if no_key(v) { mv + NO_KEY_PENALTY_S } else { v };
        x += k;
        x2 += k * k;
    }
    x /= r.len() as f64;
    Some(Stats { mean: x, mean_valid: mv, stddev: (x2 / r.len() as f64 - x * x).max(0.0).sqrt(), top: r[r.len() * 5 / 100] })
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

/// CaveGen's default `splits` (m.ss per level, CH1..CH30).
pub const DEFAULT_SPLITS: [f64; 30] = [
    1.20, 1.40, 1.20, 1.10, 1.50, 2.00, 1.40, 1.00, 0.50, 1.00, 3.50, 4.20, 4.00, 0.50, 1.45, 1.20, 1.00, 1.45, 1.50, 1.30, 1.40, 0.50, 1.50, 0.50, 2.00, 3.57, 0.52, 2.10, 1.35, 4.15,
];

/// A split in CaveGen's m.ss notation, in seconds (1.20 = 1:20 = 80 s).
pub fn split_seconds(m_ss: f64) -> f64 {
    let m = m_ss.floor();
    60.0 * m + ((m_ss - m) * 100.0).round()
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
    /// CaveGen's own times tables (4 GiB each), per kind, instead of the built-in ones
    pub times_tables: HashMap<String, String>,
    /// special targets, CaveGen's `@CH18,151AC72B,...` lines (or `CH18 151AC72B ...`)
    pub special_targets: String,
    /// special targets further than this many draws are not shown
    pub max_dist_to_consider: u64,
    /// per level CH1..CH30, m.ss (CaveGen's `splits`), for the run's delta
    pub splits: Vec<f64>,
    /// detect title-screen loops (+4505 draws) from the fades on the level select
    pub detect_title_loops: bool,
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
            special_targets: String::new(),
            max_dist_to_consider: 10_000_000,
            splits: DEFAULT_SPLITS.to_vec(),
            detect_title_loops: true,
        }
    }
}

/// CaveGen's times table file: 2^30 big-endian f32, indexed by the set of levels still to play.
fn times_table_file(path: &str, mask: u32) -> Option<f64> {
    let mut f = std::fs::File::open(path).ok()?;
    f.seek(SeekFrom::Start(4 * mask as u64)).ok()?;
    let mut b = [0u8; 4];
    f.read_exact(&mut b).ok()?;
    Some(f32::from_be_bytes(b) as f64)
}

/// Special targets: (level, seed) from lines like `@CH18,151AC72B,195B5B5E` or `CH18 151AC72B`.
/// Anything after `#` is a comment.
pub fn parse_targets(text: &str, g: Gen) -> Vec<(usize, u64)> {
    let mut out = Vec::new();
    for line in text.lines() {
        let line = line.split('#').next().unwrap_or("").trim().trim_start_matches('@');
        let mut parts = line.split(|c: char| c == ',' || c.is_whitespace()).filter(|p| !p.is_empty());
        let Some(level) = parts.next().and_then(|p| p.trim_start_matches(['C', 'H', 'c', 'h']).parse::<usize>().ok()) else { continue };
        if !(1..=30).contains(&level) {
            continue;
        }
        for p in parts {
            if p.len() >= 8 {
                if let Some(s) = g.parse(p) {
                    out.push((level, s));
                }
            }
        }
    }
    out
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
    /// the floor spawned no key (scored as the average + NO_KEY_PENALTY_S)
    pub no_key: bool,
    /// the score against the level's top 5% (attk) or its average (full-game modes)
    pub delta: f64,
    /// level select moves from the last level's cell
    pub scroll: String,
    /// press A this many frames after frame 0 ("Don't Save"), within `window` frames
    pub target_frame: i64,
    pub window: i64,
    pub cost: f64,
}

/// The nearest special target ahead.
#[derive(Clone, Debug, Serialize)]
pub struct Special {
    pub level: usize,
    pub seed: u64,
    /// draws from the first seed considered
    pub dist: u64,
    /// when to press A (frames from frame 0) and the window, if it is near enough to time
    pub target_frame: i64,
    pub window: i64,
}

/// Where the full-game modes' "cost of the levels still to play" comes from.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub enum TableSource {
    /// attk: no table
    None,
    /// the built-in 900-number table
    Builtin { samples: usize },
    /// CaveGen's 4 GiB file
    File(String),
    /// full-game mode with no table: greedy
    Greedy,
}

#[derive(Clone, Debug, Serialize)]
pub struct Plan {
    pub mode: ChMode,
    pub rng: Gen,
    /// the state the menu timing counts from: the roll's last draw, or after a title loop the
    /// menu's state + 4501 (so the menu's first state is `end + 4`)
    pub end_state: u64,
    pub options: Vec<Option_>,
    pub special: Option<Special>,
    pub table: TableSource,
    /// title loops since the results screen
    pub title_loops: usize,
}

impl Plan {
    pub fn start(&self) -> u64 {
        self.rng.next(self.end_state, ROLL_TO_MENU)
    }
    pub fn greedy(&self) -> bool {
        self.table == TableSource::Greedy
    }
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

/// Judge floor 1 of every level for `n` seeds from `first`: (level, i) -> (score, no key).
fn judge_all(g: Gen, first: u64, n: usize, kind: &str) -> Result<HashMap<(usize, usize), (f64, bool)>, String> {
    let data = game().ok_or("CaveGen3 data not found")?;
    let jt: JudgeType = kind.parse()?;
    let jc: JudgeType = "cmat".parse()?;
    let jobs: Vec<(usize, usize)> = (1..=30).flat_map(|l| (0..n).map(move |i| (l, i))).collect();
    let infos: HashMap<usize, &cavegen3::caveinfo::CaveInfo> = (1..=30)
        .filter_map(|l| {
            let sl = data.sublevel(&format!("CH{l}-1")).ok()?;
            Some((l, data.caveinfo(&sl).ok()?))
        })
        .collect();
    let judges: HashMap<usize, (JhawkJudge, JhawkJudge)> = infos.iter().map(|(&l, ci)| (l, (JhawkJudge::new(jt, ci), JhawkJudge::new(jc, ci)))).collect();
    Ok(jobs
        .par_iter()
        .filter_map(|&(l, i)| {
            let ci = infos.get(&l)?;
            let seed = g.next(first, i as i64);
            let layout = Layout::generate_with(g.cavegen(), seed, ci);
            let (judge, cmat) = &judges[&l];
            let s = judge.judge(&layout);
            Some(((l, i), (s, missing_key(kind, s, &layout, cmat))))
        })
        .collect())
}

/// What a plan starts from.
#[derive(Clone, Debug)]
pub struct PlanInput {
    pub mode: ChMode,
    pub rng: Gen,
    pub end: u64,
    pub title_loops: usize,
}

/// The options after a roll that ended on `end` (the state of its last draw).
pub fn plan(inp: &PlanInput, run: &RunState, cfg: &ManipSettings) -> Result<Plan, String> {
    let (mode, g) = (inp.mode, inp.rng);
    let end = inp.end & g.mask();
    let first_level = run.played.is_empty();
    let n = if mode.realtime() {
        if first_level { (cfg.first_level_wait_s / 5.0) as usize } else { 5 }
    } else {
        (cfg.max_wait_s / 5.0) as usize
    }
    .max(1);
    let kind = mode.kind();
    let start = g.next(end, ROLL_TO_MENU);
    let first = g.next(end, ROLL_TO_MENU + A_PRESS);
    let scores = judge_all(g, first, n, kind)?;
    let last = run.last.unwrap_or(8);

    // menu waits before each seed, in frames
    let mut waits = vec![0i64; n];
    if n > 1 {
        waits[1] = seed_duration_first(g, start);
        for i in 2..n {
            waits[i] = waits[i - 1] + seed_duration(g, g.next(start, i as i64 - 1));
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
    let file = cfg.times_tables.get(kind).filter(|p| std::path::Path::new(p).is_file()).cloned();
    let builtin: Option<&TimesTable> = times::embedded(kind);
    let table = if !mode.realtime() {
        TableSource::None
    } else if let Some(f) = &file {
        TableSource::File(f.clone())
    } else if let Some(t) = builtin {
        TableSource::Builtin { samples: t.samples }
    } else {
        TableSource::Greedy
    };
    let mut options = Vec::new();
    for l in 1..=30 {
        let Some(st) = stats(&format!("CH{l}-1"), kind) else { continue };
        let bp = &rank_file()[&format!("CH{l}-1-{kind}")];
        // the level's average and no-key score: CaveGen3's (the table's) when built in
        // (with CaveGen's own table file, the rank file's, as that table was built from it)
        let (mean, mean_valid) = match builtin.and_then(|t| t.level(l)).filter(|_| matches!(table, TableSource::Builtin { .. })) {
            Some(ls) => (ls.mean, ls.mean_valid),
            None => (st.mean, st.mean_valid),
        };
        let (scroll_frames, scroll_seq) = scroll(l);
        let orpg = late_stdev(l, kind) * cfg.give_up_per_second_vol * (1.0 - run.played.len() as f64 / 30.0);
        let rest = unplayed & !(1 << (l - 1));
        let remaining = match &table {
            TableSource::File(p) => times_table_file(p, rest).unwrap_or(0.0),
            TableSource::Builtin { .. } => builtin.map(|t| t.value(rest)).unwrap_or(0.0),
            _ => 0.0,
        };
        for i in 0..n {
            let Some(&(raw, no_key)) = scores.get(&(l, i)) else { continue };
            let score = if no_key && mode.realtime() { mean_valid + NO_KEY_PENALTY_S } else { raw };
            let rank = score_to_rank(bp, raw);
            let (delta, cost) = if mode.realtime() {
                let delta = score - mean;
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
            options.push(Option_ { level: l, advances: i, seed: g.next(first, i as i64), score, rank, no_key, delta, scroll: scroll_seq.clone(), target_frame: 0, window: 0, cost });
        }
    }
    options.sort_by(|a, b| a.cost.partial_cmp(&b.cost).unwrap());
    let show = if !mode.realtime() || first_level { 30 } else { 5 };
    let mut out = Vec::new();
    for mut o in options {
        // score attack: ignored and played levels and layouts outside the rank threshold are out
        if out.len() >= show || (!mode.realtime() && o.cost >= 50000.0) {
            break;
        }
        let (f, w) = best_timing(g, o.level, start, o.seed, o.advances as i64);
        if w <= cfg.frames_needed_for_window || f + w / 2 < cfg.frames_to_select_level + scroll(o.level).0 {
            continue;
        }
        o.target_frame = f;
        o.window = w;
        out.push(o);
    }
    let special = special_target(g, start, first, cfg);
    Ok(Plan { mode, rng: g, end_state: end, options: out, special, table, title_loops: inp.title_loops })
}

/// CaveGen's special target: the nearest listed seed ahead of the first seed considered.
fn special_target(g: Gen, start: u64, first: u64, cfg: &ManipSettings) -> Option<Special> {
    let targets = parse_targets(&cfg.special_targets, g);
    let (level, seed, dist) = targets.iter().map(|&(l, s)| (l, s, g.distance(first, s))).filter(|t| t.2 < cfg.max_dist_to_consider).min_by_key(|t| t.2)?;
    // timing it walks the menu draw by draw: only for targets a menu wait can reach
    let (f, w) = if dist <= 20_000 { best_timing(g, level, start, seed, dist as i64) } else { (0, 0) };
    Some(Special { level, seed, dist, target_frame: f, window: w })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn durations_in_range() {
        for g in [Gen::Gc, Gen::Switch] {
            for s in [0u64, 0x7FFF_FFFF, 0x1234_5678, u64::MAX] {
                assert!((46..=316).contains(&seed_duration(g, s)));
                assert!((0..300).contains(&seed_duration_first(g, s)));
            }
        }
    }

    #[test]
    fn a_press_adds_1000() {
        // with plenty of frames left before the next draw, A gives cur + 1000
        let s = 0x0404_7550;
        assert_eq!(seed_from_a(Gen::Gc, 11, s, 10_000), Gen::Gc.next(s, 1000));
    }

    #[test]
    fn timing_window_exists() {
        // the first seed considered (end + 1004): A on the menu's first state
        for g in [Gen::Gc, Gen::Switch] {
            let end = 0x0404_7550u64;
            let start = g.next(end, 4);
            let target = g.next(end, 1004);
            let (f, w) = best_timing(g, 11, start, target, 0);
            assert!(w > 0 && f >= 0, "{g:?} {f} {w}");
        }
    }

    #[test]
    fn cmal04_window_holds_the_runners_press() {
        // cmal04 at 3:00: roll end 0x2DECAB0E, the runner got Cryptic Cavern 1 = 0F129F12 by
        // pressing A about 79 frames after frame 0
        let g = Gen::Gc;
        let end = 0x2DEC_AB0E;
        let target = 0x0F12_9F12;
        assert_eq!(g.next(end, 1004), target);
        let (f, w) = best_timing(g, 11, g.next(end, 4), target, 0);
        assert!((f - w / 2..=f + w / 2).contains(&79), "{f} {w}");
    }

    #[test]
    fn menu_tracker_agrees_with_timing() {
        let g = Gen::Gc;
        let start = 0x1234_5678;
        let first = DELAY_DONT_SAVE_TO_FIRST_ADVANCE + seed_duration_first(g, start);
        assert_eq!(menu_state_at(g, start, first - 1), (start, 0));
        assert_eq!(menu_state_at(g, start, first), (g.next(start, 1), 1));
    }

    #[test]
    fn targets_parse() {
        let t = parse_targets("@CH18,151AC72B,195B5B5E # eggs\nCH4 0x0F129F12\nnonsense", Gen::Gc);
        assert_eq!(t, vec![(18, 0x151A_C72B), (18, 0x195B_5B5E), (4, 0x0F12_9F12)]);
    }

    #[test]
    fn splits() {
        assert_eq!(split_seconds(1.20), 80.0);
        assert_eq!(split_seconds(3.57), 237.0);
        assert_eq!(split_seconds(0.5), 50.0);
    }

    #[test]
    fn rank_of_extremes() {
        let bp = &rank_file()["CH4-1-attk"];
        assert_eq!(score_to_rank(bp, -1e9), 0.0);
        assert_eq!(score_to_rank(bp, 1e9), 100.0);
    }
}
