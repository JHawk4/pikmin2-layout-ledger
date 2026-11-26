//! Challenge Mode in the engine: results screens -> score-roll RNG state -> the manip plan, and
//! the frame the level select's timing counts from.
//!
//! Per frame: the share of results-screen blue (on a small copy of the game picture) groups
//! frames into results screens. As soon as the score digits stop changing (or the screen ends)
//! the screen is decoded on a worker (`p2live::challenge`), and the plan for the next level is
//! made from the roll's last draw (`manip::plan`). The first black frames after the screen are
//! the fade to the level select; frame 0 of the menu timing is `seconds_of_delay` before the
//! last of them, as in CaveGen.
//!
//! After that, as in CaveGen's Manip:
//! - **Level enter:** the floor's title card (dark, with the floor text, on a red band) for
//!   10 game frames. The picked option's level is then played, and the run's timer starts on
//!   the run's first one (for the splits' delta).
//! - **Title loops:** idling on the level select runs the title demo and comes back 4505 draws
//!   later. With no level enter, an even number (2+) of fades means a loop: the plan is made
//!   again from the menu's state then + 4505, timed from the next fade.
//! - **Anchor:** a known RNG state before the next roll (the last roll's end, or one the user
//!   enters). It lets an unreadable roll be found from a few digits, near the anchor.

use std::sync::{Arc, Mutex};

use p2live::challenge::{blue_fraction, decode_screen_with, register, Placement, RollResult, Screens, REG_MIN};
use p2live::img::Gray;

use crate::capture::{Crop, Frame};
use crate::rng::Gen;
use crate::manip::{menu_state_at, plan, ChMode, ManipSettings, Plan, PlanInput, RunState, ROLL_TO_MENU, TITLE_LOOP};

pub const NAMES: [&str; 30] = [
    "Explorer's Cave",
    "Novice Training",
    "Lost Toy Box",
    "Creator's Garden",
    "Green Hole",
    "Hot House",
    "Brawny Abyss",
    "Red Chasm",
    "Trampled Garden",
    "Twilight Garden",
    "Cryptic Cavern",
    "Concrete Maze",
    "Collector's Room",
    "Dweevil Nest",
    "Cavernous Abyss",
    "Snack Pit",
    "Three Color Training",
    "Hazard Training",
    "Cave of Snarls",
    "Giant's Bath",
    "Rumbling Grotto",
    "Subterranean Lair",
    "Hidden Garden",
    "Abduction Den",
    "Secret Testing Range",
    "Breeding Ground",
    "Cave of Pain",
    "Bully Den",
    "Sniper Room",
    "Emperor's Realm",
];

pub fn level_name(l: usize) -> &'static str {
    NAMES.get(l.wrapping_sub(1)).copied().unwrap_or("?")
}

/// What the GUI shows in a challenge mode.
#[derive(Clone, Debug)]
pub struct ChState {
    pub mode: ChMode,
    pub rng: Gen,
    pub settings: ManipSettings,
    pub run: RunState,
    pub roll: Option<RollResult>,
    pub plan: Option<Plan>,
    /// decoding a results screen or making a plan
    pub busy: Option<String>,
    pub error: Option<String>,
    /// capture index of frame 0 ("Don't Save") of the plan's menu timing
    pub frame0: Option<usize>,
    /// the option the runner picked (index into the plan's options)
    pub selected: usize,
    pub on_results: bool,
    pub screens: usize,
    /// a state the user marked as known: the next roll is searched near it
    pub anchor: Option<u64>,
    /// the last roll's end (the automatic anchor for the next screen)
    pub last_end: Option<u64>,
    /// capture frames per second (for the timers)
    pub fps: f64,
    /// capture index of the run's first level enter (the splits' delta counts from it)
    pub run_start: Option<usize>,
    pub level_enters: usize,
    /// fades since the results screen (CaveGen's numFadeouts)
    pub fades: usize,
    /// title loops since the results screen
    pub title_loops: usize,
    /// a level was entered since the plan
    pub entered: bool,
    /// the level of the run's newest level enter, with the capture index
    pub last_enter: Option<(Option<usize>, usize)>,
    /// the GUI made a new plan (a title loop): time it from the next fade
    pub want_fade: bool,
}

impl ChState {
    pub fn new(mode: ChMode, rng: Gen, settings: ManipSettings) -> Self {
        ChState {
            mode,
            rng,
            settings,
            run: RunState::default(),
            roll: None,
            plan: None,
            busy: None,
            error: None,
            frame0: None,
            selected: 0,
            on_results: false,
            screens: 0,
            anchor: None,
            last_end: None,
            fps: 30.0,
            run_start: None,
            level_enters: 0,
            fades: 0,
            title_loops: 0,
            entered: false,
            last_enter: None,
            want_fade: false,
        }
    }

    /// The splits' delta at capture index `idx`: seconds behind (+) or ahead (-) of the summed
    /// splits of the levels played.
    pub fn delta(&self, idx: usize) -> Option<(f64, f64)> {
        let t0 = self.run_start?;
        let elapsed = idx.saturating_sub(t0) as f64 / self.fps;
        let splits: f64 = self.run.played.iter().filter_map(|&l| self.settings.splits.get(l - 1)).map(|&s| crate::manip::split_seconds(s)).sum();
        Some((elapsed, elapsed - splits))
    }

    /// The level-select state now (capture index `idx`), from the plan's menu and frame 0.
    pub fn menu_state(&self, idx: usize) -> Option<(u64, i64)> {
        let (p, f0) = (self.plan.as_ref()?, self.frame0?);
        let frames = ((idx as f64 - f0 as f64) / self.fps * 30.0).max(0.0) as i64;
        Some(menu_state_at(p.rng, p.start(), frames))
    }
}

/// Make the plan from `end` on a worker (also used by the GUI: an entered seed, a title loop).
pub fn spawn_plan(st: &Arc<Mutex<ChState>>, end: u64, title_loops: usize, repaint: &Arc<dyn Fn() + Send + Sync>) {
    let (st, repaint) = (st.clone(), repaint.clone());
    {
        let mut s = st.lock().unwrap();
        s.busy = Some("judging the levels…".into());
        s.title_loops = title_loops;
    }
    repaint();
    std::thread::Builder::new()
        .name("plan".into())
        .spawn(move || {
            let (inp, run, cfg) = {
                let s = st.lock().unwrap();
                (PlanInput { mode: s.mode, rng: s.rng, end, title_loops }, s.run.clone(), s.settings.clone())
            };
            let t = std::time::Instant::now();
            let p = plan(&inp, &run, &cfg);
            if std::env::var("P2LIVE_DEBUG").is_ok() {
                eprintln!("plan in {:.2} s", t.elapsed().as_secs_f64());
            }
            let mut s = st.lock().unwrap();
            s.busy = None;
            match p {
                Ok(p) => {
                    s.plan = Some(p);
                    s.selected = 0;
                    s.error = None;
                }
                Err(e) => s.error = Some(e),
            }
            drop(s);
            repaint();
        })
        .ok();
}

/// Decode a results screen, near `anchor` when the roll alone does not give its state.
fn decode(frames: &[(usize, Gray)], hint: Option<&Placement>, rng: Gen, anchor: Option<u64>) -> Option<RollResult> {
    decode_screen_with(frames, hint, rng.core(), anchor)
}

pub struct ChPipe {
    screens: Screens,
    hint: Arc<Mutex<Option<Placement>>>,
    decoded: bool,
    prev_band: Option<Vec<u8>>,
    static_run: usize,
    /// waiting for the fade after a results screen (or after a title loop)
    await_fade: bool,
    /// in a black run: its last frame
    black_last: Option<usize>,
    /// the last black frame of the previous fade (debounce: 1 s)
    fade_end: Option<usize>,
    /// the current blue run is long enough to be a results screen
    real: bool,
    /// consecutive frames that look like a floor's title card
    enter_run: usize,
    enter_last: Option<usize>,
    /// the current blue run is not the results panel (Switch's level select is as blue)
    rejected: bool,
}

/// Blue frames before a run counts as a results screen.
const REAL_SCREEN: usize = 15;
/// Game frames of title card before it counts as a level enter (CaveGen: 10).
const ENTER_FRAMES: usize = 10;

fn small_rgb(f: &Frame, c: Crop, sw: usize, sh: usize) -> Vec<u8> {
    let c = c.clamp(f.w, f.h);
    let (w, h) = (c.w(), c.h());
    let mut out = vec![0u8; sw * sh * 3];
    for sy in 0..sh {
        let y = c.y0 + (sy * h + h / (2 * sh)) / sh;
        for sx in 0..sw {
            let x = c.x0 + (sx * w + w / (2 * sw)) / sw;
            let i = (y * f.w + x) * 3;
            out[(sy * sw + sx) * 3..(sy * sw + sx) * 3 + 3].copy_from_slice(&f.rgb[i..i + 3]);
        }
    }
    out
}

/// A small gray copy of the band where the score digits are (to see when the roll stops).
fn digit_band(f: &Frame, c: Crop) -> Vec<u8> {
    let s = small_rgb(f, c, 96, 72);
    (72 * 25 / 100..72 * 62 / 100).flat_map(|y| (0..96).map(move |x| (y, x))).map(|(y, x)| {
        let i = (y * 96 + x) * 3;
        ((s[i] as u32 + s[i + 1] as u32 + s[i + 2] as u32) / 3) as u8
    }).collect()
}

fn is_black(f: &Frame, c: Crop) -> bool {
    let s = small_rgb(f, c, 64, 48);
    let bright = s.chunks(3).filter(|p| (p[0] as u32 + p[1] as u32 + p[2] as u32) / 3 > 28).count();
    // most of the picture dark (a capture may keep a splits bar or a timer in its crop)
    bright < 64 * 48 * 15 / 100
}

/// A Challenge Mode floor's title card: the level's name in orange letters over "Sublevel N", on
/// black. CaveGen's test: the band of the name (rows 4/20..8/20, middle half) is red
/// (red - blue > 15 on average). Gameplay can be that red too, so the picture must also be dark
/// (mostly black, like a fade: a splits bar or timer in the crop is allowed).
fn is_level_card(f: &Frame, c: Crop) -> bool {
    let (sw, sh) = (160, 120);
    let s = small_rgb(f, c, sw, sh);
    let bright = s.chunks(3).filter(|p| (p[0] as u32 + p[1] as u32 + p[2] as u32) / 3 > 28).count();
    if bright * 100 >= sw * sh * 15 {
        return false;
    }
    let (mut r, mut b, mut n) = (0i64, 0i64, 0i64);
    for y in sh * 4 / 20..sh * 8 / 20 {
        for x in sw / 4..sw * 3 / 4 {
            let i = (y * sw + x) * 3;
            r += s[i] as i64;
            b += s[i + 2] as i64;
            n += 1;
        }
    }
    (r - b) as f64 / n as f64 > 15.0
}

/// The screen tests on one frame, for `--probe-card`.
pub fn probe(f: &Frame, c: Crop) -> String {
    let (sw, sh) = (160, 120);
    let s = small_rgb(f, c, sw, sh);
    let bright = s.chunks(3).filter(|p| (p[0] as u32 + p[1] as u32 + p[2] as u32) / 3 > 28).count() as f64 / (sw * sh) as f64;
    let (mut r, mut b, mut n) = (0i64, 0i64, 0i64);
    for y in sh * 4 / 20..sh * 8 / 20 {
        for x in sw / 4..sw * 3 / 4 {
            let i = (y * sw + x) * 3;
            r += s[i] as i64;
            b += s[i + 2] as i64;
            n += 1;
        }
    }
    format!(
        "blue {:.2} black {} bright {:.3} red {:.1} entry {} card {}",
        blue_fraction(&small_rgb(f, c, 160, 90), 160, 90),
        is_black(f, c),
        bright,
        (r - b) as f64 / n as f64,
        p2live::calibrate::is_entry_screen(&f.gray(c)),
        is_level_card(f, c)
    )
}

impl ChPipe {
    pub fn new() -> Self {
        ChPipe { screens: Screens::new(), hint: Arc::new(Mutex::new(None)), decoded: false, prev_band: None, static_run: 0, await_fade: false, black_last: None, fade_end: None, real: false, enter_run: 0, enter_last: None, rejected: false }
    }

    /// One captured frame (capture index `idx`, `fps` capture frames a second).
    pub fn push(&mut self, idx: usize, f: &Frame, crop: Crop, fps: f64, st: &Arc<Mutex<ChState>>, repaint: &Arc<dyn Fn() + Send + Sync>) {
        let dbg = std::env::var("P2LIVE_DEBUG").is_ok();
        let mult = ((fps / 30.0).round() as usize).max(1);
        let active = self.screens.active();
        let blue = if active || idx % 3 == 0 { blue_fraction(&small_rgb(f, crop, 160, 90), 160, 90) } else { 0.0 };
        let was_active = active;
        let finished = self.screens.push(idx, blue, || f.gray(crop));
        if !was_active && self.screens.active() {
            self.real = false;
            self.rejected = false;
            st.lock().unwrap().on_results = true;
            repaint();
        }
        // a blue run long enough to be a results screen (the Save / Don't Save dialog splits a
        // screen; the short blue run after it is not a new one)
        if self.screens.active() && !self.real && !self.rejected && self.screens.so_far().len() >= REAL_SCREEN {
            // once the panel's place is known, the run must show it
            let known = *self.hint.lock().unwrap();
            if let Some(h) = known {
                let g = &self.screens.so_far()[REAL_SCREEN - 1].1;
                let p = register(g, Some(&h));
                if p.score < REG_MIN {
                    self.rejected = true;
                    if dbg {
                        eprintln!("[{idx}] blue, but not the results panel ({:.2}): skipped", p.score);
                    }
                }
            }
        }
        if self.screens.active() && !self.real && !self.rejected && self.screens.so_far().len() >= REAL_SCREEN {
            self.real = true;
            if dbg {
                eprintln!("[{idx}] results screen from {}", self.screens.so_far()[0].0);
            }
            let mut s = st.lock().unwrap();
            s.screens += 1;
            s.fps = fps;
            // a results screen after a plan whose menu timing started, with no level enter
            // seen: the picked level was played
            if !s.entered {
                if let (Some(p), Some(_)) = (&s.plan, s.frame0) {
                    if let Some(o) = p.options.get(s.selected) {
                        let l = o.level;
                        mark_played(&mut s, l);
                    }
                }
            }
            s.frame0 = None;
            s.fades = 0;
            s.title_loops = 0;
            s.entered = false;
            drop(s);
            self.decoded = false;
            self.prev_band = None;
            self.static_run = 0;
            self.await_fade = false;
            self.black_last = None;
            self.fade_end = None;
            repaint();
        }
        if let Some(frames) = finished {
            st.lock().unwrap().on_results = false;
            if self.real {
                if dbg {
                    eprintln!("[{idx}] results screen ends ({} frames, {}..{})", frames.len(), frames.first().map(|f| f.0).unwrap_or(0), frames.last().map(|f| f.0).unwrap_or(0));
                }
                if !self.decoded {
                    self.spawn(frames, st, repaint);
                }
                self.decoded = false;
                self.await_fade = true;
                self.black_last = None;
            }
            self.real = false;
            repaint();
        } else if self.screens.active() && self.real && !self.decoded {
            // find the panel early (the first screen of a session), so decoding is quick
            if self.screens.so_far().len() == REAL_SCREEN && self.hint.lock().unwrap().is_none() {
                let g = self.screens.so_far()[REAL_SCREEN - 1].1.clone();
                let hint = self.hint.clone();
                std::thread::spawn(move || {
                    let p = register(&g, None);
                    if p.score >= REG_MIN {
                        hint.lock().unwrap().get_or_insert(p);
                    }
                });
            }
            // the roll is over when the digits have not changed for a while
            let band = digit_band(f, crop);
            let still = self.prev_band.as_ref().is_some_and(|p| p.iter().zip(&band).all(|(a, b)| (*a as i16 - *b as i16).abs() < 10));
            self.static_run = if still { self.static_run + 1 } else { 0 };
            self.prev_band = Some(band);
            let need = (0.8 * fps).round() as usize;
            if self.screens.so_far().len() >= (2.0 * fps) as usize && self.static_run >= need {
                self.decoded = true;
                if dbg {
                    eprintln!("[{idx}] digits still for {} frames: decoding", self.static_run);
                }
                let frames = self.screens.so_far().to_vec();
                self.spawn(frames, st, repaint);
            }
        }
        // (a blue run that is not a results screen, like Switch's level select, still has fades)
        if self.screens.active() && self.real {
            return;
        }
        {
            let mut s = st.lock().unwrap();
            if s.want_fade {
                s.want_fade = false;
                s.fades = 0;
                self.await_fade = true;
            }
        }

        // fades: frame 0 is seconds_of_delay before the last black frame of the first fade
        // after the results screen (or after a title loop)
        let black = is_black(f, crop);
        if black {
            if self.black_last.is_none() && dbg {
                eprintln!("[{idx}] black");
            }
            self.black_last = Some(idx);
        } else if let Some(last) = self.black_last.take() {
            // a fade ended (fades within 1 s of each other are one, as in CaveGen)
            let new_fade = self.fade_end.is_none_or(|e| last.saturating_sub(e) as f64 > fps);
            self.fade_end = Some(last);
            let mut s = st.lock().unwrap();
            if new_fade {
                s.fades += 1;
            }
            if self.await_fade {
                self.await_fade = false;
                let back = (s.settings.seconds_of_delay * fps).round() as usize;
                s.frame0 = Some(last.saturating_sub(back));
                if dbg {
                    eprintln!("[{idx}] fade over (last black {last}): frame 0 = {:?}", s.frame0);
                }
                repaint();
            }
        }

        // level enters: the floor's title card for ENTER_FRAMES game frames
        // (the card is dark: it may count as black, inside the fade into the level)
        let card = idx % mult == 0 && is_level_card(f, crop);
        if idx % mult == 0 {
            self.enter_run = if card { self.enter_run + 1 } else { 0 };
        }
        if self.enter_run == ENTER_FRAMES && self.enter_last.is_none_or(|e| idx.saturating_sub(e) as f64 > fps) {
            self.enter_last = Some(idx);
            let mut s = st.lock().unwrap();
            s.level_enters += 1;
            if s.run_start.is_none() {
                s.run_start = Some(idx.saturating_sub(ENTER_FRAMES * mult));
            }
            // the option the runner picked was entered (the plan's timing must have started)
            let mut level = None;
            if !s.entered && s.frame0.is_some() {
                if let Some(l) = s.plan.as_ref().and_then(|p| p.options.get(s.selected)).map(|o| o.level) {
                    mark_played(&mut s, l);
                    level = Some(l);
                }
            }
            s.entered = true;
            s.last_enter = Some((level, idx));
            if dbg {
                eprintln!("[{idx}] level enter {} ({level:?})", s.level_enters);
            }
            drop(s);
            repaint();
        }

        // title loops (CaveGen: 2+ fades, an even number, the last over 1 s ago, no level enter,
        // the timer running)
        if let Some(e) = self.fade_end {
            let mut s = st.lock().unwrap();
            let due = s.settings.detect_title_loops && !black && !s.entered && s.fades >= 2 && s.fades % 2 == 0 && s.frame0.is_some() && idx.saturating_sub(e) as f64 > fps;
            if due {
                let menu = s.menu_state(e).map(|m| m.0);
                let loops = s.title_loops + 1;
                s.fades = 0;
                s.frame0 = None;
                drop(s);
                if let Some(m) = menu {
                    if dbg {
                        eprintln!("[{idx}] title loop {loops}: menu state {m:X} + {TITLE_LOOP}");
                    }
                    // the menu's first state is then menu + 4505 = end + 4
                    let g = st.lock().unwrap().rng;
                    spawn_plan(st, g.next(m, TITLE_LOOP - ROLL_TO_MENU), loops, repaint);
                    self.await_fade = true;
                }
            }
        }
    }

    fn spawn(&mut self, frames: Vec<(usize, Gray)>, st: &Arc<Mutex<ChState>>, repaint: &Arc<dyn Fn() + Send + Sync>) {
        let (st, repaint, hint) = (st.clone(), repaint.clone(), self.hint.clone());
        st.lock().unwrap().busy = Some("reading the score roll…".into());
        std::thread::Builder::new()
            .name("challenge".into())
            .spawn(move || {
                let h = *hint.lock().unwrap();
                let (rng, anchor) = {
                    let s = st.lock().unwrap();
                    (s.rng, s.anchor.or(s.last_end))
                };
                let mut res = decode(&frames, h.as_ref(), rng, anchor);
                // the panel's place from an early frame can be off: try once more without it
                if res.is_none() && h.is_some() {
                    res = decode(&frames, None, rng, anchor);
                }
                let mut s = st.lock().unwrap();
                let Some(r) = res else {
                    s.busy = None;
                    s.error = Some("the results screen did not match the reference panel".into());
                    drop(s);
                    repaint();
                    return;
                };
                *hint.lock().unwrap() = Some(r.placement);
                let end = r.end_state;
                // the next screen is searched near this one (its start, when the end is unsure)
                if let Some(a) = r.end_state.or(r.first_state) {
                    s.last_end = Some(a);
                    if s.anchor.is_some() {
                        s.anchor = Some(a);
                    }
                }
                s.roll = Some(r);
                s.error = None;
                let Some(end) = end else {
                    s.busy = None;
                    s.error = Some("could not read the roll (no seed for this screen): enter the seed by hand, or wait for the next screen".into());
                    drop(s);
                    repaint();
                    return;
                };
                drop(s);
                spawn_plan(&st, end, 0, &repaint);
            })
            .ok();
    }
}

fn mark_played(s: &mut ChState, l: usize) {
    if !s.run.played.contains(&l) {
        s.run.played.push(l);
    }
    s.run.last = Some(l);
}
