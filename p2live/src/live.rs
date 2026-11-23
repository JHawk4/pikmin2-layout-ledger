//! Seeds from a stream of frames, as they happen (the Rust version of p2seeds/live.py).
//!
//! The capture side calls [`Live::push`] once per received frame. It only runs the cheap
//! entry-screen check and keeps a ring buffer. For each entry screen it hands three kinds of
//! job to the workers:
//!
//! 1. **Name**, `CAL_AFTER` game frames after the screen settled: read the cave name. The
//!    stream's first screen calibrates in full; after that the stream's learned scale
//!    (`ScaleHint`) needs about a tenth of the matches. Then match every letter on the buffered
//!    fall frames (`track::prefill`), so the seed attempts only match the frames that arrive
//!    after. Running it early hides it behind the wait for the fall's last frames.
//! 2. **Seed**, at each of `tails` game frames after the settle (e.g. 20, then 40): the offline
//!    analysis of the buffered fall (`analyze_entry_with`). If it is not high confidence, chain
//!    from the previous sublevel's layout seed (a bounded number of RNG steps earlier), which
//!    settles most weak fits. Attempts run the quick analysis (see `analyze_entry_with`). A high
//!    or chained seed is reported at once; otherwise the next attempt has more of the fall, and
//!    the last attempt reports whatever it has, then runs the full analysis (all variants and
//!    timing-step refits, seconds on a hard fall) and sends an update if that does better.
//! 3. **Digits**, `DIGITS_AT` game frames after the settle (or when the screen ends): read the
//!    sublevel number on the settled frames. Until then a seed reports the sublevel the order of
//!    play implies (the previous one in the same cave + 1, else 1), and the digit read sends an
//!    update if it differs.
//!
//! Nothing looks ahead: every decision uses frames already received.

use std::collections::VecDeque;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use serde::Serialize;

use crate::analyze::{analyze_entry_with, Conf, Frames, FALL_LEAD, MIN_CAVE_MARGIN, MIN_CAVE_SCORE, MIN_CAVE_SCORE_JA, STRONG_CAVE_MARGIN_JA, STRONG_CAVE_SCORE_JA};
use crate::calibrate::{calibrate, calibrate_hinted, is_entry_screen, Calibration, ScaleHint};
use crate::digits::read_sublevel;
use crate::img::{resize_area, Gray, Img};
use crate::lattice::search_near;
use crate::track::{prefill, MatchCache};
use crate::templates::{layout_seed, Cave};

/// Frames kept, in game frames (13 s at 30 fps): the fall lead plus a long title.
pub const RING: usize = 400;
/// Settled frames before the screen counts as an entry screen (analyze.entry_runs).
pub const MIN_RUN: usize = 6;
/// Game frames into the settled run before the name is first read (the bubbles fade).
pub const CAL_AFTER: usize = 8;
/// The name is read again every this many game frames until it is recognized.
pub const NAME_EVERY: usize = 4;
/// ... up to this many game frames into the settled run (then the last seed attempt decides).
pub const NAME_UNTIL: usize = 40;
/// Game frames into the settled run when the sublevel number is read.
pub const DIGITS_AT: usize = 45;
/// RNG steps searched after the previous layout seed when chaining (live.py's NEAR).
pub const NEAR: u64 = 2_000_000;
/// The same cave again within this many seconds is a flicker splitting one screen.
pub const FLICKER_S: f64 = 5.0;
/// The detector is tuned for captures of at most this many lines; taller ones are scaled down.
pub const MAX_LINES: usize = 480;

#[derive(Clone, Debug)]
pub struct LiveConfig {
    /// Frames per second of the capture (30, or 60 for a 60 fps capture of the 30 fps game).
    pub fps: f64,
    /// Cave names to recognize (the runner's category and game language).
    pub caves: Vec<Cave>,
    /// Seed attempts, in game frames after the screen settled; later ones only if no seed yet.
    /// An attempt is skipped while the previous one of the same screen is still running.
    pub tails: Vec<usize>,
    /// Worker threads; 0 = analyze on the capture thread (simulation: no pacing, timings added).
    pub workers: usize,
    /// A scale learned before (a saved profile); otherwise the first screen calibrates in full.
    pub hint: Option<ScaleHint>,
    /// Chain from the previous sublevel when a fit alone is not high confidence.
    pub chain: bool,
}

impl LiveConfig {
    pub fn new(fps: f64, caves: Vec<Cave>) -> Self {
        LiveConfig { fps, caves, tails: vec![12, 16, 20, 24, 28, 32, 40], workers: 2, hint: None, chain: true }
    }
    /// Capture frames per game frame (1 at 30 fps, 2 at 60).
    pub fn mult(&self) -> usize {
        ((self.fps / 30.0).round() as usize).max(1)
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct LiveResult {
    /// Capture frame index where the settled entry screen began (identifies the entry).
    pub run_start: usize,
    /// A correction of an earlier result for the same entry (the sublevel number was read, or
    /// the full analysis found a better seed: then `refined`).
    pub update: bool,
    pub refined: bool,
    pub cave: String,
    pub cave_name: String,
    pub sublevel: Option<u32>,
    /// "digit" (read on screen) or "sequence" (the order of play; may be corrected by an update).
    pub sublevel_source: String,
    pub letter_seed: Option<String>,
    pub layout_seed: Option<String>,
    pub confidence: Conf,
    /// RNG steps from the previous sublevel when chaining settled a weak fit.
    pub chained: Option<u64>,
    pub note: String,
    /// Game frames after the settle that the reported attempt used.
    pub tail: usize,
    /// Seconds from the screen settling to the seed being ready.
    pub ready_after_s: f64,
    pub name_s: f64,
    /// letter matching on the buffered fall right after the name read
    pub prefill_s: f64,
    pub analyze_s: f64,
    pub chain_s: f64,
    pub hinted: bool,
}

/// An entry screen that was reported: a flicker of it (the same cave again within FLICKER_S) is
/// the same entry. When the report was not trusted (low or medium, not chained) the flicker is
/// analyzed again and replaces it if it does better: a flicker can cut the first run short.
struct Found {
    cave: String,
    run_start: usize,
    trusted: bool,
    conf: Conf,
    sublevel: Option<u32>,
    source: String,
}

/// Frame source for analyze_entry: the job carries every frame it may use.
struct NoMoreFrames;
impl Frames for NoMoreFrames {
    fn frames(&self, _: usize, _: usize) -> Vec<Gray> {
        Vec::new()
    }
    fn count(&self) -> usize {
        usize::MAX
    }
}

/// What the jobs of one entry screen share.
#[derive(Default)]
struct EntryState {
    /// seed reported, or given up
    done: bool,
    not_a_cave: bool,
    name_pending: bool,
    /// calibration, its absolute frame, whether it used the scale hint, time it took
    cal: Option<(Calibration, usize, bool, f64)>,
    /// simulation: seconds after the settle when the name was ready
    name_ready_sim: Option<f64>,
    /// a seed attempt of this screen is running (real time)
    seed_running: bool,
    /// simulation: seconds after the settle when the last seed attempt finished
    sim_free_at: f64,
    digit: Option<u32>,
    reported: Option<LiveResult>,
    /// letter template matches, shared by this screen's analyses
    cache: Arc<MatchCache>,
    prefill_s: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Kind {
    Name,
    Seed { tail: usize, last: bool },
    Digits,
}

struct Job {
    kind: Kind,
    a: usize,
    first: usize,
    frames: Vec<Gray>,
    b: usize,
    t_land: Instant,
    state: Arc<Mutex<EntryState>>,
    /// simulation: seconds after the settle when this job was due
    sim_due: Option<f64>,
}

/// State the workers share.
struct Shared {
    cfg: LiveConfig,
    hint: Mutex<Option<ScaleHint>>,
    prev_layout: Mutex<Option<u64>>,
    /// (cave, sublevel) of the latest entry with a known sublevel
    last_sub: Mutex<Option<(String, u32)>>,
    found: Mutex<Vec<Found>>,
    results: Sender<LiveResult>,
    log: Box<dyn Fn(&str) + Send + Sync>,
}

#[derive(Default)]
struct Sent {
    /// name reads sent, and the run length at the last one
    name: usize,
    name_at: usize,
    seeds: usize,
    digits: bool,
}

pub struct Live {
    shared: Arc<Shared>,
    ring: VecDeque<(usize, Gray)>,
    run_start: Option<usize>,
    t_land: Option<Instant>,
    sent: Sent,
    state: Option<Arc<Mutex<EntryState>>>,
    jobs: Option<Sender<Job>>,
    workers: Vec<JoinHandle<()>>,
    pub check_s: f64,
    pub frames_seen: usize,
}

impl Live {
    /// A live detector and the receiving end of its results.
    pub fn new(cfg: LiveConfig, log: Box<dyn Fn(&str) + Send + Sync>) -> (Live, Receiver<LiveResult>) {
        let (tx, rx) = channel();
        let shared = Arc::new(Shared {
            hint: Mutex::new(cfg.hint),
            cfg,
            prev_layout: Mutex::new(None),
            last_sub: Mutex::new(None),
            found: Mutex::new(Vec::new()),
            results: tx,
            log,
        });
        let mut workers = Vec::new();
        let mut jobs = None;
        if shared.cfg.workers > 0 {
            let (jtx, jrx) = channel::<Job>();
            let jrx = Arc::new(Mutex::new(jrx));
            for _ in 0..shared.cfg.workers {
                let (jrx, sh) = (jrx.clone(), shared.clone());
                workers.push(std::thread::spawn(move || loop {
                    let job = jrx.lock().unwrap().recv();
                    match job {
                        Ok(job) => run_job(&sh, job),
                        Err(_) => return,
                    }
                }));
            }
            jobs = Some(jtx);
        }
        let live = Live { shared, ring: VecDeque::new(), run_start: None, t_land: None, sent: Sent::default(), state: None, jobs, workers, check_s: 0.0, frames_seen: 0 };
        (live, rx)
    }

    /// The stream's current name scale (to save in a profile).
    pub fn hint(&self) -> Option<ScaleHint> {
        *self.shared.hint.lock().unwrap()
    }

    /// One received frame (already cropped to the game picture), with its capture index.
    pub fn push(&mut self, index: usize, gray: Gray) {
        self.push_at(index, gray, Instant::now());
    }

    /// `push` with the receive time given (a simulation passes a fixed clock).
    pub fn push_at(&mut self, index: usize, gray: Gray, t_recv: Instant) {
        let gray = if gray.h > MAX_LINES { downscale(&gray, MAX_LINES) } else { gray };
        let t0 = Instant::now();
        let flag = is_entry_screen(&gray);
        self.check_s += t0.elapsed().as_secs_f64();
        self.frames_seen += 1;
        let m = self.shared.cfg.mult();
        self.ring.push_back((index, gray));
        while self.ring.len() > RING * m {
            self.ring.pop_front();
        }
        if !flag {
            // the screen ended before every job was sent: finish with what there is
            if self.state.is_some() && index > 0 {
                if self.sent.seeds < self.shared.cfg.tails.len() {
                    let tail = (index - self.run_start.unwrap()) / m;
                    self.submit(Kind::Seed { tail, last: true }, index - 1);
                }
                if !self.sent.digits {
                    self.submit(Kind::Digits, index - 1);
                }
            }
            self.run_start = None;
            self.state = None;
            self.sent = Sent::default();
            return;
        }
        let a = *self.run_start.get_or_insert(index);
        let run_len = index - a + 1;
        if self.state.is_none() && run_len >= MIN_RUN * m {
            self.state = Some(Arc::new(Mutex::new(EntryState::default())));
            self.t_land = Some(t_recv.checked_sub(Duration::from_secs_f64((run_len - 1) as f64 / self.shared.cfg.fps)).unwrap_or(t_recv));
        }
        if self.state.is_none() {
            return;
        }
        // the name: first after CAL_AFTER, then again every NAME_EVERY until recognized (before the
        // stream's scale is known a read is a full calibration: at most two then)
        let (name_known, name_pending) = {
            let st = self.state.as_ref().unwrap().lock().unwrap();
            (st.cal.is_some() || st.not_a_cave, st.name_pending)
        };
        let hinted = self.shared.hint.lock().unwrap().is_some();
        if !name_known
            && !name_pending
            && run_len > CAL_AFTER * m
            && run_len <= NAME_UNTIL * m
            && (self.sent.name == 0 || run_len >= self.sent.name_at + NAME_EVERY * m)
            && (hinted || self.sent.name < 2)
        {
            self.sent.name_at = run_len;
            self.submit(Kind::Name, index);
        }
        let tails = self.shared.cfg.tails.clone();
        while self.sent.seeds < tails.len() && run_len >= tails[self.sent.seeds] * m {
            let last = self.sent.seeds + 1 == tails.len();
            self.submit(Kind::Seed { tail: tails[self.sent.seeds], last }, index);
        }
        if !self.sent.digits && run_len >= DIGITS_AT * m {
            self.submit(Kind::Digits, index);
        }
    }

    fn submit(&mut self, kind: Kind, b: usize) {
        let Some(state) = self.state.clone() else { return };
        match kind {
            Kind::Name => self.sent.name += 1,
            Kind::Seed { .. } => self.sent.seeds += 1,
            Kind::Digits => self.sent.digits = true,
        }
        let a = self.run_start.unwrap();
        let sim = self.jobs.is_none();
        let due = (b - a) as f64 / self.shared.cfg.fps;
        if let Kind::Seed { last, .. } = kind {
            let st = state.lock().unwrap();
            if st.done {
                return;
            }
            // no name yet, or the previous attempt still running: wait for the next one
            let busy = if sim { st.sim_free_at > due } else { st.seed_running };
            if !last && (busy || st.cal.is_none()) {
                return;
            }
        }
        if kind == Kind::Name {
            state.lock().unwrap().name_pending = true;
        }
        if matches!(kind, Kind::Seed { .. }) {
            state.lock().unwrap().seed_running = true;
        }
        let first = self.ring.front().map(|x| x.0).unwrap_or(a);
        let frames: Vec<Gray> = self.ring.iter().filter(|(i, _)| *i <= b).map(|(_, g)| g.clone()).collect();
        let job = Job {
            kind,
            a,
            first,
            frames,
            b,
            t_land: self.t_land.unwrap_or_else(Instant::now),
            state,
            sim_due: sim.then_some(due),
        };
        match &self.jobs {
            Some(tx) => {
                let _ = tx.send(job);
            }
            None => run_job(&self.shared, job),
        }
    }

    /// Finish: let the workers drain their queue.
    pub fn close(mut self) {
        self.jobs = None;
        for w in self.workers.drain(..) {
            let _ = w.join();
        }
    }
}

/// The same frame at most `lines` tall (cv2.INTER_AREA).
pub fn downscale(g: &Gray, lines: usize) -> Gray {
    let s = lines as f64 / g.h as f64;
    let w = ((g.w as f64 * s).round() as usize).max(1);
    let mut im = Img::zeros(g.w, g.h);
    for y in 0..g.h {
        for (x, &v) in g.row(y).iter().enumerate() {
            im.d[y * g.w + x] = v as f32;
        }
    }
    let r = resize_area(&im, w, lines);
    Gray::new(w, lines, r.d.iter().map(|&v| v.round().clamp(0.0, 255.0) as u8).collect())
}

fn accept(cal: &Calibration) -> bool {
    let margin = cal.score - cal.runner_up.as_ref().map(|r| r.1).unwrap_or(0.0);
    let ja = cal.cave.lang == "ja";
    let min_score = if ja { MIN_CAVE_SCORE_JA } else { MIN_CAVE_SCORE };
    let min_margin = if ja && cal.score >= STRONG_CAVE_SCORE_JA { STRONG_CAVE_MARGIN_JA } else { MIN_CAVE_MARGIN };
    cal.score >= min_score && margin >= min_margin
}

fn hex(s: Option<u64>) -> Option<String> {
    s.map(|x| format!("0x{x:08X}"))
}

fn run_job(sh: &Shared, job: Job) {
    match job.kind {
        Kind::Name => name_job(sh, job),
        Kind::Seed { tail, last } => seed_job(sh, job, tail, last),
        Kind::Digits => digits_job(sh, job),
    }
}

/// The best accepted calibration among the newest settled frames up to `b` (relative indices).
/// `full_fallback`: when the hinted read fails, one full calibration (the capture may have changed
/// size). Only the last attempt does that: on the many dark text screens that are not cave names
/// it would cost a full calibration per read.
fn read_name(sh: &Shared, job: &Job, a: usize, b: usize, full_fallback: bool) -> Option<(Calibration, usize, bool)> {
    let m = sh.cfg.mult();
    let hint = *sh.hint.lock().unwrap();
    let mut best: Option<(Calibration, usize)> = None;
    for j in [b, b.saturating_sub(8 * m), b.saturating_sub(16 * m)] {
        if j < a + CAL_AFTER * m || best.as_ref().is_some_and(|(_, k)| *k == j) {
            continue;
        }
        let c = match hint {
            Some(h) => calibrate_hinted(&job.frames[j], &sh.cfg.caves, h),
            None => calibrate(&job.frames[j], &sh.cfg.caves),
        };
        if let Some(c) = c {
            if best.as_ref().is_none_or(|(bc, _)| c.score > bc.score) {
                best = Some((c, j));
            }
        }
        if best.as_ref().is_some_and(|(c, _)| accept(c)) {
            break;
        }
    }
    match best {
        Some((c, j)) if accept(&c) => Some((c, j, hint.is_some())),
        other if hint.is_some() && full_fallback => {
            // a hinted read can miss when the capture changed size: one full try
            let c = calibrate(&job.frames[b], &sh.cfg.caves)?;
            if std::env::var("P2LIVE_DEBUG").is_ok() {
                let d = |c: &Calibration| format!("{} {:.3} margin {:.3} sy {:.4} ratio {:.4}", c.cave.cavegen, c.score, c.score - c.runner_up.as_ref().map(|r| r.1).unwrap_or(0.0), c.sy, c.sx / c.sy);
                (sh.log)(&format!("[{}] hinted {:?}: {} | full: {}", job.a, hint, other.as_ref().map(|(c, _)| d(c)).unwrap_or_default(), d(&c)));
            }
            accept(&c).then_some((c, b, false))
        }
        _ => None,
    }
}

fn name_job(sh: &Shared, job: Job) {
    let t0 = Instant::now();
    let (a, b) = (job.a - job.first, job.b - job.first);
    let lead = FALL_LEAD * sh.cfg.mult();
    let got = if a < lead { None } else { read_name(sh, &job, a, b, false) };
    let took = t0.elapsed().as_secs_f64();
    // the seed attempts wait for this job (name_pending): match the fall so far for them
    let mut prefill_s = 0.0;
    if let Some((c, _, _)) = &got {
        let t1 = Instant::now();
        let cache = job.state.lock().unwrap().cache.clone();
        let lo = a - lead;
        // only the frames the analysis keeps (a 60 fps capture repeats every game frame)
        let keep = crate::analyze::game_times(&job.frames[lo..=b], false).0;
        let frames: Vec<Gray> = keep.iter().map(|&i| job.frames[lo + i].clone()).collect();
        let ids: Vec<usize> = keep.iter().map(|&i| job.first + lo + i).collect();
        prefill(&frames, &ids, c, &cache, false);
        prefill_s = t1.elapsed().as_secs_f64();
    }
    let mut st = job.state.lock().unwrap();
    st.name_pending = false;
    if let Some((c, k, hinted)) = got {
        if st.cal.is_none() {
            st.cal = Some((c, k + job.first, hinted, took));
            st.prefill_s = prefill_s;
            st.name_ready_sim = job.sim_due.map(|d| d + took + prefill_s);
        }
    }
}

fn seed_job(sh: &Shared, job: Job, tail: usize, last: bool) {
    let t0 = Instant::now();
    let state = job.state.clone();
    let due = job.sim_due;
    seed_attempt(sh, job, tail, last);
    let mut st = state.lock().unwrap();
    st.seed_running = false;
    if let Some(due) = due {
        let start = due.max(st.sim_free_at).max(st.name_ready_sim.unwrap_or(due));
        st.sim_free_at = start + t0.elapsed().as_secs_f64();
    }
}

fn seed_attempt(sh: &Shared, job: Job, tail: usize, last: bool) {
    let cfg = &sh.cfg;
    let m = cfg.mult();
    let t0 = Instant::now();
    // wait for the name job of this screen (real time only; in a simulation it already ran)
    while job.state.lock().unwrap().name_pending && t0.elapsed() < Duration::from_secs(5) {
        std::thread::sleep(Duration::from_millis(5));
    }
    let t_wait = Instant::now();
    if job.state.lock().unwrap().done || job.state.lock().unwrap().not_a_cave {
        return;
    }
    let (a, b) = (job.a - job.first, job.b - job.first);
    let lead = FALL_LEAD * m;
    if a < lead {
        (sh.log)(&format!("[{}] entry screen too soon after the stream started; skipped", job.a));
        job.state.lock().unwrap().done = true;
        return;
    }
    let known = job.state.lock().unwrap().cal.clone();
    let (cal, k, hinted, name_s) = match known {
        Some((c, kabs, h, took)) => (c, kabs - job.first, h, took),
        None => match read_name(sh, &job, a, b, last) {
            Some((c, k, h)) => {
                let took = t_wait.elapsed().as_secs_f64();
                job.state.lock().unwrap().cal = Some((c.clone(), k + job.first, h, took));
                (c, k, h, took)
            }
            None => {
                if !last {
                    (sh.log)(&format!("[{}] cave name not read after {tail} frames; trying again later", job.a));
                }
                if last {
                    let mut st = job.state.lock().unwrap();
                    st.not_a_cave = true;
                    st.done = true;
                    (sh.log)(&format!("[{}] dark text screen, not a cave name", job.a));
                }
                return;
            }
        },
    };
    let t_cal = Instant::now();
    let replaces = {
        let found = sh.found.lock().unwrap();
        let flicker = (FLICKER_S * cfg.fps) as usize;
        let same: Vec<&Found> = found.iter().filter(|f| f.cave == cal.cave.cavegen && job.a > f.run_start && job.a - f.run_start < flicker).collect();
        if same.iter().any(|f| f.trusted) {
            job.state.lock().unwrap().done = true;
            return;
        }
        same.last().map(|f| (f.run_start, f.conf, f.sublevel, f.source.clone()))
    };
    let (cache, prefill_s) = {
        let st = job.state.lock().unwrap();
        (st.cache.clone(), st.prefill_s)
    };
    let r = analyze_entry_with(&NoMoreFrames, &job.frames[..=b], job.first, cal.clone(), a, b, k, lead, tail * m, true, Some(&cache));
    let t_seed = Instant::now();
    let (letter, conf, chained) = settle(sh, &r);
    let t_chain = Instant::now();
    let good = conf == Conf::High || chained.is_some();
    if !good && !last {
        // the next attempt has more of the fall
        (sh.log)(&format!(
            "[{}] {} after {tail} frames: {:?}, {} letters, rms {:.2} px{}; trying again later",
            job.a,
            cal.cave.cavegen,
            conf,
            r.fit.as_ref().map(|f| f.n_measured()).unwrap_or(0),
            r.fit.as_ref().map(|f| f.rms_px).unwrap_or(f64::NAN),
            if r.note.is_empty() { String::new() } else { format!(" ({})", r.note) }
        ));
        return;
    }
    let mut st = job.state.lock().unwrap();
    if st.done {
        return; // another attempt finished this entry first
    }
    st.done = true;
    if let Some((a0, conf0, ..)) = &replaces {
        if !good && conf <= *conf0 {
            (sh.log)(&format!("[{}] flicker of the screen at {a0}; no better", job.a));
            return;
        }
    }
    let layout = letter.map(|s| layout_seed(s, cal.cave.num_chars()));
    // the sublevel: read on screen, else what the order of play implies (a flicker keeps the
    // replaced report's)
    let (sublevel, source) = match (r.digit_value.or(st.digit), &replaces) {
        (Some(d), _) => (Some(d), "digit".to_string()),
        (None, Some((_, _, s0, src0))) => (*s0, src0.clone()),
        (None, None) => {
            let last_sub = sh.last_sub.lock().unwrap().clone();
            let guess = match last_sub {
                Some((c, s)) if c == cal.cave.cavegen => s + 1,
                _ => 1,
            };
            (Some(guess.min(cal.cave.sublevels)), "sequence".to_string())
        }
    };
    if let Some(s) = sublevel {
        *sh.last_sub.lock().unwrap() = Some((cal.cave.cavegen.to_string(), s));
    }
    let run_start = replaces.as_ref().map(|r| r.0).unwrap_or(job.a);
    sh.found.lock().unwrap().push(Found { cave: cal.cave.cavegen.to_string(), run_start, trusted: good, conf, sublevel, source: source.clone() });
    if good {
        remember(sh, &cal, layout, conf);
    }
    let analysis = (t_chain - t_cal).as_secs_f64();
    let ready = match job.sim_due {
        // simulation: work starts when the job is due and the name is ready
        Some(due) => due.max(st.sim_free_at).max(st.name_ready_sim.unwrap_or(due)) + (t_chain - t_wait).as_secs_f64(),
        None => job.t_land.elapsed().as_secs_f64(),
    };
    let res = LiveResult {
        run_start,
        update: replaces.is_some(),
        refined: replaces.is_some(),
        cave: cal.cave.cavegen.to_string(),
        cave_name: cal.cave.label().to_string(),
        sublevel,
        sublevel_source: source,
        letter_seed: hex(letter),
        layout_seed: hex(layout),
        confidence: conf,
        chained,
        note: r.note.clone(),
        tail,
        ready_after_s: ready,
        name_s,
        prefill_s,
        analyze_s: analysis - (t_chain - t_seed).as_secs_f64(),
        chain_s: (t_chain - t_seed).as_secs_f64(),
        hinted,
    };
    st.reported = Some(res.clone());
    drop(st);
    let _ = sh.results.send(res);
    if conf == Conf::High {
        return;
    }
    // the full analysis; an update if it does better than the quick answer
    let t_full = Instant::now();
    let r2 = analyze_entry_with(&NoMoreFrames, &job.frames[..=b], job.first, cal.clone(), a, b, k, lead, tail * m, false, Some(&cache));
    let (letter2, conf2, chained2) = settle(sh, &r2);
    let full_s = t_full.elapsed().as_secs_f64();
    // a different seed replaces the shown one only when it can be trusted (high or chained): on a
    // weak fall the variants disagree, and an equally unsure answer is no better (replays: three
    // of four such swaps moved away from the offline answer)
    let trusted2 = conf2 == Conf::High || chained2.is_some();
    let better = if letter2 == letter { conf2 > conf } else { trusted2 && (conf2 > conf || chained.is_none()) };
    if letter2.is_none() || !better {
        (sh.log)(&format!("[{}] full analysis ({full_s:.1} s) found nothing better", job.a));
        return;
    }
    let layout2 = letter2.map(|s| layout_seed(s, cal.cave.num_chars()));
    let mut st = job.state.lock().unwrap();
    let Some(mut upd) = st.reported.clone() else { return };
    if conf2 == Conf::High || chained2.is_some() {
        remember(sh, &cal, layout2, conf2);
        let mut found = sh.found.lock().unwrap();
        if let Some(f) = found.iter_mut().rev().find(|f| f.run_start == upd.run_start && f.cave == upd.cave) {
            f.trusted = true;
            f.conf = conf2;
        }
    }
    upd.update = true;
    upd.refined = true;
    upd.letter_seed = hex(letter2);
    upd.layout_seed = hex(layout2);
    upd.confidence = conf2;
    upd.chained = chained2;
    upd.note = r2.note.clone();
    upd.ready_after_s += full_s;
    st.reported = Some(upd.clone());
    drop(st);
    (sh.log)(&format!("[{}] full analysis ({full_s:.1} s): {:?} -> {:?}", job.a, conf, conf2));
    let _ = sh.results.send(upd);
}

/// The seed an analysis settles on: its own when high confidence, else chained from the
/// previous sublevel's layout seed when that is clear, else its own at its confidence.
fn settle(sh: &Shared, r: &crate::analyze::EntryResult) -> (Option<u64>, Conf, Option<u64>) {
    let (mut letter, mut conf, mut chained) = (r.letter_seed, r.confidence, None);
    if sh.cfg.chain && conf != Conf::High {
        let prev = *sh.prev_layout.lock().unwrap();
        if let (Some(prev), Some(f)) = (prev, r.fit.as_ref()) {
            if let Ok(c) = search_near(&f.v, &f.sigma, prev, NEAR, 2) {
                if let Some(best) = c.first() {
                    if c.len() < 2 || c[1].score - best.score > 15.0 {
                        letter = Some(best.letter_seed);
                        chained = Some(best.distance.unwrap_or(0));
                        conf = conf.max(Conf::Medium);
                    }
                }
            }
        }
    }
    (letter, conf, chained)
}

/// A trusted seed: the next sublevel chains from it, and a high-confidence read teaches the
/// stream's scale.
fn remember(sh: &Shared, cal: &Calibration, layout: Option<u64>, conf: Conf) {
    if let Some(l) = layout {
        *sh.prev_layout.lock().unwrap() = Some(l);
    }
    if conf == Conf::High {
        let h = cal.hint();
        let mut g = sh.hint.lock().unwrap();
        *g = Some(match *g {
            Some(old) => old.merge(h),
            None => h,
        });
    }
}

fn digits_job(sh: &Shared, job: Job) {
    // the name is needed for the language; wait for it briefly
    let t0 = Instant::now();
    while job.state.lock().unwrap().name_pending && t0.elapsed() < Duration::from_secs(5) {
        std::thread::sleep(Duration::from_millis(5));
    }
    let Some(lang) = job.state.lock().unwrap().cal.as_ref().map(|c| c.0.cave.lang) else { return };
    let (a, b) = (job.a - job.first, job.b - job.first);
    let (value, _) = read_sublevel(&job.frames, a, b, lang);
    let Some(value) = value else { return };
    let mut st = job.state.lock().unwrap();
    st.digit = Some(value);
    let Some(prev) = st.reported.clone() else { return };
    if prev.sublevel == Some(value) && prev.sublevel_source == "digit" {
        return;
    }
    let mut upd = prev;
    upd.update = true;
    upd.sublevel = Some(value);
    upd.sublevel_source = "digit".into();
    st.reported = Some(upd.clone());
    drop(st);
    {
        let mut ls = sh.last_sub.lock().unwrap();
        if ls.as_ref().is_some_and(|(c, _)| *c == upd.cave) {
            *ls = Some((upd.cave.clone(), value));
        }
    }
    let _ = sh.results.send(upd);
}
