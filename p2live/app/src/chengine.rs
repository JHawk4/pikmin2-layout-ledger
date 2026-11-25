//! Challenge Mode in the engine: results screens -> score-roll RNG state -> the manip plan, and
//! the frame the level select's timing counts from.
//!
//! Per frame: the share of results-screen blue (on a small copy of the game picture) groups
//! frames into results screens. As soon as the score digits stop changing (or the screen ends)
//! the screen is decoded on a worker (`p2live::challenge`), and the plan for the next level is
//! made from the roll's last draw (`manip::plan`). The first black frames after the screen are
//! the fade to the level select; frame 0 of the menu timing is `seconds_of_delay` before the
//! last of them, as in CaveGen.

use std::sync::{Arc, Mutex};

use p2live::challenge::{blue_fraction, decode_screen, register, Placement, RollResult, Screens, REG_MIN};

use crate::capture::{Crop, Frame};
use crate::manip::{plan, ChMode, ManipSettings, Plan, RunState};

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
}

impl ChState {
    pub fn new(mode: ChMode, settings: ManipSettings) -> Self {
        ChState { mode, settings, run: RunState::default(), roll: None, plan: None, busy: None, error: None, frame0: None, selected: 0, on_results: false, screens: 0 }
    }
}

pub struct ChPipe {
    screens: Screens,
    hint: Arc<Mutex<Option<Placement>>>,
    decoded: bool,
    prev_band: Option<Vec<u8>>,
    static_run: usize,
    /// waiting for the fade after a results screen; then in it (last black frame)
    await_fade: bool,
    black_last: Option<usize>,
    /// the current blue run is long enough to be a results screen
    real: bool,
}

/// Blue frames before a run counts as a results screen.
const REAL_SCREEN: usize = 15;

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
    let mut sum = 0u32;
    let mut bright = 0;
    for p in s.chunks(3) {
        let v = (p[0] as u32 + p[1] as u32 + p[2] as u32) / 3;
        sum += v;
        if v > 28 {
            bright += 1;
        }
    }
    // most of the picture dark (a capture may keep a splits bar or a timer in its crop)
    let _ = sum;
    bright < 64 * 48 * 15 / 100
}

impl ChPipe {
    pub fn new() -> Self {
        ChPipe { screens: Screens::new(), hint: Arc::new(Mutex::new(None)), decoded: false, prev_band: None, static_run: 0, await_fade: false, black_last: None, real: false }
    }

    /// One captured frame (capture index `idx`, `fps` capture frames a second).
    pub fn push(&mut self, idx: usize, f: &Frame, crop: Crop, fps: f64, st: &Arc<Mutex<ChState>>, repaint: &Arc<dyn Fn() + Send + Sync>) {
        let active = self.screens.active();
        let blue = if active || idx % 3 == 0 { blue_fraction(&small_rgb(f, crop, 160, 90), 160, 90) } else { 0.0 };
        let was_active = active;
        let finished = self.screens.push(idx, blue, || f.gray(crop));
        let dbg = std::env::var("P2LIVE_DEBUG").is_ok();
        if !was_active && self.screens.active() {
            self.real = false;
            st.lock().unwrap().on_results = true;
            repaint();
        }
        // a blue run long enough to be a results screen (the Save / Don't Save dialog splits a
        // screen; the short blue run after it is not a new one)
        if self.screens.active() && !self.real && self.screens.so_far().len() >= REAL_SCREEN {
            self.real = true;
            if dbg {
                eprintln!("[{idx}] results screen from {}", self.screens.so_far()[0].0);
            }
            let mut s = st.lock().unwrap();
            s.screens += 1;
            // a results screen after a plan whose menu timing started: the picked level was played
            if let (Some(p), Some(_)) = (&s.plan, s.frame0) {
                if let Some(o) = p.options.get(s.selected) {
                    let l = o.level;
                    if !s.run.played.contains(&l) {
                        s.run.played.push(l);
                    }
                    s.run.last = Some(l);
                }
            }
            s.frame0 = None;
            drop(s);
            self.decoded = false;
            self.prev_band = None;
            self.static_run = 0;
            self.await_fade = false;
            self.black_last = None;
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
        // the fade to the level select: frame 0 is seconds_of_delay before its last black frame
        if self.await_fade {
            if is_black(f, crop) {
                if dbg && self.black_last.is_none() {
                    eprintln!("[{idx}] fade to black");
                }
                self.black_last = Some(idx);
            } else if let Some(last) = self.black_last {
                self.await_fade = false;
                let mut s = st.lock().unwrap();
                let back = (s.settings.seconds_of_delay * fps).round() as usize;
                s.frame0 = Some(last.saturating_sub(back));
                if dbg {
                    eprintln!("[{idx}] fade over (last black {last}): frame 0 = {:?}", s.frame0);
                }
                drop(s);
                repaint();
            }
        }
    }

    fn spawn(&mut self, frames: Vec<(usize, p2live::img::Gray)>, st: &Arc<Mutex<ChState>>, repaint: &Arc<dyn Fn() + Send + Sync>) {
        let (st, repaint, hint) = (st.clone(), repaint.clone(), self.hint.clone());
        st.lock().unwrap().busy = Some("reading the score roll…".into());
        std::thread::Builder::new()
            .name("challenge".into())
            .spawn(move || {
                let h = *hint.lock().unwrap();
                let res = decode_screen(&frames, h.as_ref());
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
                s.roll = Some(r);
                s.error = None;
                let Some(end) = end else {
                    s.busy = None;
                    s.error = Some("could not read the roll (no seed for this screen)".into());
                    drop(s);
                    repaint();
                    return;
                };
                s.busy = Some("judging the levels…".into());
                let (mode, run, cfg) = (s.mode, s.run.clone(), s.settings.clone());
                drop(s);
                repaint();
                let t = std::time::Instant::now();
                let p = plan(mode, end, &run, &cfg);
                if std::env::var("P2LIVE_DEBUG").is_ok() {
                    eprintln!("plan in {:.2} s", t.elapsed().as_secs_f64());
                }
                let mut s = st.lock().unwrap();
                s.busy = None;
                match p {
                    Ok(p) => {
                        s.plan = Some(p);
                        s.selected = 0;
                    }
                    Err(e) => s.error = Some(e),
                }
                drop(s);
                repaint();
            })
            .ok();
    }
}
