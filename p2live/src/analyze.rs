//! One entry-screen event: cave, letter fall, seed (analyze.py).

use std::collections::{BTreeMap, HashMap};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

/// Time spent per stage (ns), summed over all threads: calibrate, track, fit, step refits, search, timing.
pub static STAGE_NS: [AtomicU64; 6] = [const { AtomicU64::new(0) }; 6];
pub const STAGES: [&str; 6] = ["calibrate", "track", "fit", "step_refits", "search", "game_times"];

fn timed<T>(i: usize, f: impl FnOnce() -> T) -> T {
    let t = Instant::now();
    let r = f();
    STAGE_NS[i].fetch_add(t.elapsed().as_nanos() as u64, Ordering::Relaxed);
    r
}

use crate::calibrate::{calibrate, entry_runs, Calibration};
use crate::digits;
use crate::fit::{fit, FitResult, Segment};
use crate::lattice::{self, Candidate};
use crate::templates::{caves, layout_seed, Cave, POD_CAVES};
use crate::track::{track_all, Blend, Track};
use crate::img::Gray;

pub const MIN_CAVE_SCORE: f64 = 0.38;
pub const MIN_CAVE_MARGIN: f64 = 0.12;
pub const RESCUE_SCORE: f64 = 0.33;
pub const RESCUE_MARGIN: f64 = 0.06;
pub const MIN_CAVE_SCORE_JA: f64 = 0.48;
pub const FALL_LEAD: usize = 110;
pub const FALL_TAIL: usize = 40;
pub const LOW_MATCH: f64 = 0.4;
pub const MAX_FIT_RMS_PX: f64 = 0.6;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Conf {
    None,
    Low,
    Medium,
    High,
}

#[derive(Clone, Debug, Default)]
pub struct Event {
    pub first: usize,
    pub last: usize,
}

#[derive(Clone, Debug)]
pub struct EntryResult {
    pub settled_frame: Option<usize>,
    pub cave: Option<Cave>,
    pub cave_score: f64,
    pub runner_up: Option<(String, f64)>,
    pub fit: Option<FitResult>,
    pub candidates: Vec<Candidate>,
    pub letter_seed: Option<u64>,
    pub layout_seed: Option<u64>,
    pub confidence: Conf,
    pub note: String,
    pub digit_value: Option<u32>,
    pub digit_votes: BTreeMap<u32, u32>,
    pub best_cave: Option<String>,
    pub best_margin: f64,
    pub near: Vec<(String, f64, f64)>,
}

impl EntryResult {
    fn empty(note: &str) -> Self {
        EntryResult {
            settled_frame: None,
            cave: None,
            cave_score: 0.0,
            runner_up: None,
            fit: None,
            candidates: Vec::new(),
            letter_seed: None,
            layout_seed: None,
            confidence: Conf::None,
            note: note.to_string(),
            digit_value: None,
            digit_votes: BTreeMap::new(),
            best_cave: None,
            best_margin: 0.0,
            near: Vec::new(),
        }
    }
}

/// Frame source: cropped feed frames [start, stop) (clipped to the video).
pub trait Frames {
    fn frames(&self, start: usize, stop: usize) -> Vec<Gray>;
    fn count(&self) -> usize;
}

fn mean_abs_diff(a: &Gray, b: &Gray) -> f64 {
    let mut s: u64 = 0;
    for y in 0..a.h {
        for (p, q) in a.row(y).iter().zip(b.row(y).iter()) {
            s += (*p as i32 - *q as i32).unsigned_abs() as u64;
        }
    }
    s as f64 / (a.w * a.h).max(1) as f64
}

/// analyze.game_times: drop repeated frames and give each kept one its game-frame time.
/// Returns (indices of kept frames, their times).
pub fn game_times(frames: &[Gray], wall: bool) -> (Vec<usize>, Vec<f64>) {
    let (thr, rel, jump) = (0.1f64, 0.25f64, 1.35f64);
    if frames.is_empty() {
        return (Vec::new(), Vec::new());
    }
    let d: Vec<f64> = frames.windows(2).map(|w| mean_abs_diff(&w[0], &w[1])).collect();
    let n = d.len();
    let local: Vec<f64> = (0..n)
        .map(|j| {
            let around: Vec<f64> = d[j.saturating_sub(3)..j].iter().chain(d[(j + 1).min(n)..(j + 4).min(n)].iter()).cloned().collect();
            if around.is_empty() { 0.0 } else { crate::img::median(&around) }
        })
        .collect();
    let repeat: Vec<bool> = (0..n).map(|j| d[j] <= thr.max(rel * local[j])).collect();
    let mut inc: Vec<u32> = repeat.iter().map(|&r| if r { 0 } else { 1 }).collect();
    for j in 0..n {
        let near = (j > 0 && repeat[j - 1]) || (j + 1 < n && repeat[j + 1]);
        if !repeat[j] && near && local[j] > 0.5 && d[j] >= jump * local[j] {
            inc[j] = 2;
        }
    }
    let mut t = vec![0.0f64; n + 1];
    for j in 0..n {
        t[j + 1] = t[j] + inc[j] as f64;
    }
    if wall {
        t = (0..=n).map(|i| i as f64).collect();
    }
    let mut keep = vec![0usize];
    keep.extend((0..n).filter(|&j| !repeat[j]).map(|j| j + 1));
    let times = keep.iter().map(|&k| t[k]).collect();
    (keep, times)
}

fn to_time(frames: &[f64], times: &[f64]) -> Vec<f64> {
    frames
        .iter()
        .map(|&f| {
            let k = f.floor();
            times[k as usize] + if f - k > 0.0 { 1.0 } else { 0.0 }
        })
        .collect()
}

pub fn confidence(c: &[Candidate]) -> Conf {
    let Some(best) = c.first() else { return Conf::None };
    let n = best.n_measured();
    let gap = if c.len() > 1 { c[1].score - best.score } else { f64::INFINITY };
    let per = best.score / n.max(1) as f64;
    if n >= 10 && per < 4.0 && gap > 30.0 {
        Conf::High
    } else if n >= 7 && per < 6.0 && gap > 15.0 {
        Conf::Medium
    } else {
        Conf::Low
    }
}

fn combinations(items: &[usize], k: usize) -> Vec<Vec<usize>> {
    if k == 0 {
        return vec![vec![]];
    }
    let mut out = Vec::new();
    for i in 0..items.len() {
        for mut rest in combinations(&items[i + 1..], k - 1) {
            rest.insert(0, items[i]);
            out.push(rest);
        }
    }
    out
}

/// analyze._search: lattice search; when inconclusive, retry leaving out one letter, then two.
pub fn search_fit(f: &FitResult, retries: bool) -> (Vec<Candidate>, Conf) {
    let measured: Vec<usize> = (0..f.v.len()).filter(|&i| f.v[i].is_finite() && f.sigma[i].is_finite()).collect();
    let attempt = |out: &[usize]| -> (Vec<Candidate>, Conf) {
        match lattice::search(&f.v, &f.sigma, out, if out.is_empty() { 500_000 } else { 100_000 }) {
            Ok(c) => {
                let conf = confidence(&c);
                (c, conf)
            }
            Err(_) => (Vec::new(), Conf::None),
        }
    };
    let key = |c: &(Vec<Candidate>, Conf)| (c.1, -(c.0.first().map(|x| x.score).unwrap_or(1e9)));
    let mut best = attempt(&[]);
    if retries {
        for k in [1usize, 2] {
            if best.1 == Conf::High || measured.len() < 6 + k || f.rms_px > MAX_FIT_RMS_PX {
                break;
            }
            for out in combinations(&measured, k) {
                let c = attempt(&out);
                let (a, b) = (key(&c), key(&best));
                if a.0 > b.0 || (a.0 == b.0 && a.1 > b.1) {
                    best = c;
                }
            }
        }
    }
    best
}

/// analyze._fit_with_step: refits assuming one skipped (+1) or repeated (-1) game frame at k.
fn fit_with_step(tracks: &[Track], num_chars: usize, s_guess: f64, base: &FitResult, segment: Segment) -> Vec<(FitResult, i32, i64)> {
    let all: Vec<f64> = tracks.iter().flat_map(|t| t.frames.iter().cloned()).collect();
    if all.is_empty() {
        return Vec::new();
    }
    let lo = all.iter().cloned().fold(f64::INFINITY, f64::min) as i64 + 1;
    let hi = all.iter().cloned().fold(f64::NEG_INFINITY, f64::max) as i64;
    let n_old = base.n_measured();
    use rayon::prelude::*;
    let jobs: Vec<(i32, i64)> = [1, -1].iter().flat_map(|&d| (lo..hi).map(move |k| (d, k))).collect();
    let tried: Vec<(FitResult, i32, i64)> = jobs
        .par_iter()
        .filter_map(|&(d, k)| {
            let shifted: Vec<Track> = tracks
                .iter()
                .map(|t| Track { frames: t.frames.iter().map(|&f| if f >= k as f64 { f + d as f64 } else { f }).collect(), ..t.clone() })
                .collect();
            let f = fit(&shifted, num_chars, s_guess, 4, 0.55, 3, segment).ok()?;
            (f.rms_px <= MAX_FIT_RMS_PX).then_some((f, d, k))
        })
        .collect();
    let mut better: Vec<(FitResult, i32, i64)> = tried
        .into_iter()
        .filter(|(f, _, _)| f.n_measured() > n_old || (f.n_measured() == n_old && f.rms_px <= 0.8 * base.rms_px))
        .collect();
    better.sort_by(|a, b| b.0.n_measured().cmp(&a.0.n_measured()).then(a.0.rms_px.partial_cmp(&b.0.rms_px).unwrap()));
    better.truncate(40);
    better
}

pub struct Options {
    pub caves: Vec<Cave>,
}

impl Default for Options {
    fn default() -> Self {
        Options { caves: caves() }
    }
}

/// analyze.analyze_event: every sublevel entry inside one candidate window. With `only` (a cave id),
/// only that cave is accepted, at the weaker rescue thresholds.
pub fn analyze_event(src: &dyn Frames, ev: &Event, opts: &Options, only: Option<&str>) -> Vec<EntryResult> {
    let start = ev.first.saturating_sub(150);
    let stop = (ev.last + 30).min(src.count());
    let frames = src.frames(start, stop);
    if frames.is_empty() {
        return vec![EntryResult::empty("no frames decoded")];
    }
    let runs = entry_runs(&frames);
    if runs.is_empty() {
        return vec![EntryResult::empty("no settled entry screen")];
    }
    let mut entries: Vec<(Calibration, usize, usize, usize)> = Vec::new();
    let mut best_reject: Option<(Calibration, f64)> = None;
    let mut near: Vec<(String, f64, f64)> = Vec::new();
    for &(a, b) in &runs {
        let mut k = a.max(b.saturating_sub(3));
        let mut cal = timed(0, || calibrate(&frames[k], &opts.caves));
        if b - a < 90 {
            let k2 = a + (b - a) * 2 / 3;
            if k2 != k {
                if let Some(c2) = timed(0, || calibrate(&frames[k2], &opts.caves)) {
                    if cal.as_ref().is_none_or(|c| c2.score > c.score) {
                        cal = Some(c2);
                        k = k2;
                    }
                }
            }
        }
        let margin = cal.as_ref().map(|c| c.score - c.runner_up.as_ref().map(|r| r.1).unwrap_or(0.0)).unwrap_or(0.0);
        let (mut min_score, mut min_margin) = (
            if cal.as_ref().is_some_and(|c| c.cave.lang == "ja") { MIN_CAVE_SCORE_JA } else { MIN_CAVE_SCORE },
            MIN_CAVE_MARGIN,
        );
        if let Some(o) = only {
            min_score = RESCUE_SCORE;
            min_margin = RESCUE_MARGIN;
            if cal.as_ref().is_some_and(|c| c.cave.cavegen != o) {
                cal = None;
            }
        }
        let ok = cal.as_ref().is_some_and(|c| c.score >= min_score && margin >= min_margin);
        if !ok {
            if let Some(c) = cal {
                near.push((c.cave.cavegen.to_string(), c.score, margin));
                if best_reject.as_ref().is_none_or(|(b, _)| c.score > b.score) {
                    best_reject = Some((c, margin));
                }
            }
            continue;
        }
        let cal = cal.unwrap();
        if let Some(last) = entries.last_mut() {
            if last.0.cave == cal.cave && a as i64 - (last.2 as i64) < 60 {
                last.2 = b;
                if cal.score > last.0.score {
                    last.0 = cal;
                    last.3 = k;
                }
                continue;
            }
        }
        entries.push((cal, a, b, k));
    }
    if entries.is_empty() {
        if let Some((cal, margin)) = best_reject {
            let mut r = EntryResult::empty(&format!(
                "cave name not recognized (best {} {:.2}, margin {:.2})",
                cal.cave.cavegen, cal.score, margin
            ));
            r.cave_score = cal.score;
            r.best_cave = Some(cal.cave.cavegen.to_string());
            r.best_margin = margin;
            r.near = near;
            return vec![r];
        }
        return vec![EntryResult::empty("no text found")];
    }
    entries
        .into_iter()
        .map(|(cal, a, b, k)| {
            let mut r = analyze_entry(src, &frames, start, cal, a, b, k);
            r.near = near.clone();
            r
        })
        .collect()
}

/// analyze._analyze_entry. `frames` start at absolute frame `start`.
pub fn analyze_entry(src: &dyn Frames, frames: &[Gray], start: usize, cal: Calibration, a: usize, b: usize, k: usize) -> EntryResult {
    let mut r = EntryResult::empty("");
    r.settled_frame = Some(start + k);
    r.cave_score = cal.score;
    r.runner_up = cal.runner_up.clone();
    r.cave = Some(cal.cave.clone());
    let lang = cal.cave.lang;
    let (dv, votes) = digits::read_sublevel(frames, a, b, lang);
    r.digit_value = dv;
    r.digit_votes = votes;

    let mut frames: Vec<Gray> = frames.to_vec();
    let mut a = a;
    if a < FALL_LEAD {
        let extra = src.frames(start.saturating_sub(FALL_LEAD), start);
        a += extra.len();
        let mut f = extra;
        f.extend(frames);
        frames = f;
    }
    let clip: Vec<Gray> = frames[a.saturating_sub(FALL_LEAD)..(a + FALL_TAIL).min(frames.len())].to_vec();
    let ja = lang == "ja";
    let (base_score, min_letters) = if ja { (0.5f64, 2) } else { (0.55f64, 3) };
    let feed_h = frames[0].h as f64;
    let s_guess = feed_h / 480.0;
    let num_chars = cal.cave.num_chars();

    let mut first_failure: Option<String> = None;
    let mut times_cache: HashMap<bool, (Vec<usize>, Vec<f64>)> = HashMap::new();
    let mut track_cache: HashMap<(bool, u8), Vec<Track>> = HashMap::new();
    let variants: [(bool, bool, Blend, bool); 10] = [
        (false, false, Blend::No, false),
        (false, false, Blend::No, true),
        (false, true, Blend::No, false),
        (false, true, Blend::No, true),
        (true, false, Blend::No, false),
        (true, true, Blend::No, false),
        (true, false, Blend::Yes, false),
        (true, true, Blend::Yes, false),
        (true, false, Blend::Pair, false),
        (true, true, Blend::Pair, false),
    ];
    for (weak, wall, blended, first) in variants {
        if r.confidence == Conf::High {
            break;
        }
        let (keep, times) = times_cache.entry(wall).or_insert_with(|| timed(5, || game_times(&clip, wall))).clone();
        let bkey = (weak, match blended { Blend::No => 0, Blend::Yes => 1, Blend::Pair => 2 });
        let raw = track_cache
            .entry(bkey)
            .or_insert_with(|| {
                let fall: Vec<Gray> = keep.iter().map(|&i| clip[i].clone()).collect();
                timed(1, || track_all(&fall, &cal, if weak { LOW_MATCH } else { 0.5 }, blended))
            })
            .clone();
        let tracks: Vec<Track> = raw.into_iter().map(|t| Track { frames: to_time(&t.frames, &times), ..t }).collect();
        let min_score = if weak { base_score.min(LOW_MATCH) } else { base_score };
        let segment = if first { Segment::First } else { Segment::Longest };
        let f = match timed(2, || fit(&tracks, num_chars, s_guess, 4, min_score, min_letters, segment)) {
            Ok(f) => f,
            Err(e) => {
                first_failure.get_or_insert(format!("fit failed: {}", e.0));
                continue;
            }
        };
        let n_meas = f.n_measured();
        if n_meas < 4 {
            first_failure.get_or_insert("too few letters measured".to_string());
            continue;
        }
        let how: Vec<&str> = [
            if weak { "weaker letter matches allowed" } else { "" },
            if wall { "timed by the video clock" } else { "" },
            match blended {
                Blend::Pair => "blended frames (overlapping doubled letters)",
                Blend::Yes => "blended frames (letters doubled)",
                Blend::No => "",
            },
            if first { "first falling stretch" } else { "" },
        ]
        .into_iter()
        .filter(|s| !s.is_empty())
        .collect();
        let how = how.join(", ");
        let (cands, conf) = timed(4, || search_fit(&f, true));
        if r.fit.is_none() || conf > r.confidence {
            r.fit = Some(f.clone());
            r.candidates = cands;
            r.confidence = conf;
            r.note = how.clone();
        }
        if conf != Conf::High && n_meas >= 5 {
            for (f2, d, k) in timed(3, || fit_with_step(&tracks, num_chars, s_guess, &f, segment)) {
                let (c2, conf2) = search_fit(&f2, false);
                if conf2 > r.confidence {
                    r.fit = Some(f2);
                    r.candidates = c2;
                    r.confidence = conf2;
                    let step = format!("timing step of {:+} frame at fall frame {}", d, k);
                    r.note = if how.is_empty() { step } else { format!("{how}, {step}") };
                }
            }
        }
    }
    let Some(f) = &r.fit else {
        r.note = first_failure.unwrap_or_else(|| "fit failed".to_string());
        return r;
    };
    if r.candidates.is_empty() {
        r.note = if f.rms_px > MAX_FIT_RMS_PX { format!("letter fit too poor ({:.2} px)", f.rms_px) } else { "no seed matches".to_string() };
        return r;
    }
    let best = r.candidates[0].letter_seed;
    r.letter_seed = Some(best);
    r.layout_seed = Some(layout_seed(best, num_chars));
    r
}

/// events.detect over a frame source: every `step`-th frame checked, hits merged within `merge_gap`.
pub fn detect(src: &dyn Frames, start: usize, stop: usize, step: usize, merge_gap: usize) -> Vec<Event> {
    let frames = src.frames(start, stop);
    let mut events: Vec<Event> = Vec::new();
    for (j, g) in frames.iter().enumerate().step_by(step) {
        if crate::calibrate::is_entry_screen(g) {
            let i = start + j;
            match events.last_mut() {
                Some(e) if i - e.last <= merge_gap => e.last = i,
                _ => events.push(Event { first: i, last: i }),
            }
        }
    }
    events
}

pub fn is_pod(c: &str) -> bool {
    POD_CAVES.contains(&c)
}
