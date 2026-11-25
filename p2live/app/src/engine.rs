//! The engine thread: reads the source, keeps a preview frame, feeds the live detector, and has
//! CaveGen3 draw each seed's layout (on a thread of its own). The GUI and the Browser Source
//! server only read `Shared` and send `Cmd`s.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{channel, Receiver, Sender, TryRecvError};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use p2live::calibrate::ScaleHint;
use p2live::live::{Live, LiveConfig, LiveResult};
use p2live::templates::{caves, Cave, POD_CAVES};

use crate::capture::{Crop, Frame, Source, SourceSpec};
use crate::feed::FeedFinder;
use crate::settings::{Category, Language, LayoutView};

/// What the detector needs from a profile.
#[derive(Clone, Debug)]
pub struct DetectCfg {
    pub category: Category,
    pub language: Language,
    pub hint: Option<(f64, f64)>,
    pub view: LayoutView,
}

pub enum Cmd {
    /// Open this source (closing the current one), or none.
    Source(Option<SourceSpec>),
    Crop(Option<Crop>),
    /// Start or stop detecting (a new config also starts a new run).
    Detect(Option<DetectCfg>),
    /// Forget this run's sublevels (the next seed is not chained to the last one).
    NewRun,
    /// Start (true) or stop collecting frames to find the game picture.
    FindFeed(bool),
    /// Draw the current run's layouts again (the layout options changed).
    View(LayoutView),
}

#[derive(Clone, Debug, Default)]
pub struct Status {
    pub source: Option<String>,
    pub error: Option<String>,
    pub w: usize,
    pub h: usize,
    pub fps: f64,
    /// frames per second actually received over the last second or so
    pub received_fps: f64,
    pub detecting: bool,
    pub on_entry_screen: bool,
    /// entry screens seen (whether or not they gave a seed)
    pub screens: usize,
}

/// One sublevel of the run.
#[derive(Clone, Debug)]
pub struct Entry {
    /// the entry screen's first frame (identifies the entry across updates)
    pub key: usize,
    pub cave: String,
    pub cave_name: String,
    pub sublevel: Option<u32>,
    /// the sublevel is the order of play's guess, not read on screen yet
    pub sublevel_guess: bool,
    pub layout_seed: Option<u64>,
    pub confidence: String,
    pub chained: bool,
    pub ready_s: f64,
    pub png: Option<Arc<Vec<u8>>>,
    pub score: Option<f64>,
    pub render_error: Option<String>,
    /// bumped whenever this entry's picture changes
    pub version: u64,
}

impl Entry {
    pub fn sublevel_id(&self) -> Option<String> {
        self.sublevel.map(|s| format!("{}-{s}", self.cave))
    }
    pub fn title(&self) -> String {
        match self.sublevel {
            Some(s) => format!("{} {}{}", self.cave_name, s, if self.sublevel_guess { "?" } else { "" }),
            None => self.cave_name.clone(),
        }
    }
    pub fn seed_text(&self) -> String {
        self.layout_seed.map(|s| format!("{s:08X}")).unwrap_or_else(|| "no seed".into())
    }
}

pub struct Shared {
    pub status: Mutex<Status>,
    pub preview: Mutex<Option<Arc<Frame>>>,
    pub preview_n: AtomicU64,
    pub entries: Mutex<Vec<Entry>>,
    /// bumped on any change to `entries`
    pub version: AtomicU64,
    pub feed: Mutex<(usize, Option<Crop>)>,
    pub hint: Mutex<Option<(f64, f64)>>,
    pub log: Mutex<VecDeque<String>>,
    pub cavegen: Mutex<Result<(), String>>,
}

impl Shared {
    pub fn log(&self, s: impl Into<String>) {
        let mut l = self.log.lock().unwrap();
        l.push_back(s.into());
        while l.len() > 300 {
            l.pop_front();
        }
    }
    /// The newest entry with a seed.
    pub fn current(&self) -> Option<Entry> {
        self.entries.lock().unwrap().iter().rev().find(|e| e.layout_seed.is_some()).cloned()
    }
}

pub struct Engine {
    pub shared: Arc<Shared>,
    tx: Sender<Cmd>,
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

impl Engine {
    pub fn start(repaint: Box<dyn Fn() + Send + Sync>) -> Engine {
        let shared = Arc::new(Shared {
            status: Mutex::new(Status::default()),
            preview: Mutex::new(None),
            preview_n: AtomicU64::new(0),
            entries: Mutex::new(Vec::new()),
            version: AtomicU64::new(0),
            feed: Mutex::new((0, None)),
            hint: Mutex::new(None),
            log: Mutex::new(VecDeque::new()),
            cavegen: Mutex::new(Ok(())),
        });
        let (tx, rx) = channel();
        let stop = Arc::new(AtomicBool::new(false));
        let thread = {
            let (shared, stop) = (shared.clone(), stop.clone());
            std::thread::Builder::new().name("engine".into()).spawn(move || run(shared, rx, stop, Arc::from(repaint))).unwrap()
        };
        Engine { shared, tx, stop, thread: Some(thread) }
    }

    pub fn send(&self, c: Cmd) {
        let _ = self.tx.send(c);
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }
}

fn cave_list(cat: Category, lang: Language) -> Vec<Cave> {
    caves()
        .into_iter()
        .filter(|c| match lang {
            Language::Auto => true,
            Language::En => c.lang == "en",
            Language::Ja => c.lang == "ja",
        })
        .filter(|c| cat != Category::Pod || POD_CAVES.contains(&c.cavegen))
        .collect()
}

struct RenderJob {
    key: usize,
    sublevel: String,
    seed: u64,
    judge: &'static str,
    view: LayoutView,
}

fn cavegen_data() -> std::path::PathBuf {
    if let Some(d) = std::env::var_os("CAVEGEN3_DATA") {
        return d.into();
    }
    if let Some(d) = std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.join("cavegen3-data"))) {
        if d.is_dir() {
            return d;
        }
    }
    cavegen3_cli::default_data_dir()
}

/// CaveGen3 on its own thread: draws the layouts and judges them.
fn render_thread(shared: Arc<Shared>, rx: Receiver<RenderJob>, repaint: Arc<dyn Fn() + Send + Sync>) {
    let painter = match cavegen3_cli::Painter::new(&cavegen_data()) {
        Ok(p) => p,
        Err(e) => {
            *shared.cavegen.lock().unwrap() = Err(format!("CaveGen3 data not found ({e}); layouts will not be drawn"));
            return;
        }
    };
    // warm up: the first layout loads the map pictures
    let _ = painter.png("EC-1", 0, &cavegen3_cli::render::Options::default());
    while let Ok(mut job) = rx.recv() {
        // only the newest job for an entry matters
        while let Ok(j) = rx.try_recv() {
            job = j;
        }
        let t0 = Instant::now();
        let opts = cavegen3_cli::render::Options { quick_glance: job.view.quick_glance, pretty: job.view.pretty, ..Default::default() };
        let res = painter.png(&job.sublevel, job.seed, &opts);
        let score = painter
            .query(&["judge", &job.sublevel, job.judge, &job.seed.to_string()])
            .ok()
            .and_then(|v| v["score"].as_f64());
        let took = t0.elapsed().as_secs_f64();
        let mut entries = shared.entries.lock().unwrap();
        if let Some(e) = entries.iter_mut().find(|e| e.key == job.key && e.layout_seed == Some(job.seed) && e.sublevel_id().as_deref() == Some(&job.sublevel)) {
            match res {
                Ok((_, png)) => {
                    e.png = Some(Arc::new(png));
                    e.render_error = None;
                }
                Err(err) => e.render_error = Some(err),
            }
            e.score = score;
            e.version += 1;
            drop(entries);
            shared.version.fetch_add(1, Ordering::SeqCst);
            shared.log(format!("drew {} {:08X} in {:.2} s", job.sublevel, job.seed, took));
            repaint();
        }
    }
}

fn run(shared: Arc<Shared>, rx: Receiver<Cmd>, stop: Arc<AtomicBool>, repaint: Arc<dyn Fn() + Send + Sync>) {
    let (rtx, rrx) = channel::<RenderJob>();
    {
        let (shared, repaint) = (shared.clone(), repaint.clone());
        std::thread::Builder::new().name("cavegen".into()).spawn(move || render_thread(shared, rrx, repaint)).unwrap();
    }
    let mut source: Option<Source> = None;
    let mut crop: Option<Crop> = None;
    let mut detect: Option<DetectCfg> = None;
    let mut live: Option<(Live, Receiver<LiveResult>)> = None;
    let mut finder: Option<FeedFinder> = None;
    let mut idx = 0usize;
    let mut fps_window: VecDeque<Instant> = VecDeque::new();
    let mut last_preview = Instant::now() - Duration::from_secs(1);
    let mut was_on_screen = false;

    let new_live = |shared: &Arc<Shared>, d: &DetectCfg, fps: f64| -> (Live, Receiver<LiveResult>) {
        let mut cfg = LiveConfig::new(fps, cave_list(d.category, d.language));
        cfg.hint = shared.hint.lock().unwrap().or(d.hint).map(|(sy, ratio)| ScaleHint { sy, ratio });
        let sh = shared.clone();
        Live::new(cfg, Box::new(move |s| sh.log(s.trim().to_string())))
    };

    while !stop.load(Ordering::SeqCst) {
        // commands
        loop {
            match rx.try_recv() {
                Ok(Cmd::Source(spec)) => {
                    source = None;
                    live = None;
                    let mut st = shared.status.lock().unwrap();
                    *st = Status { detecting: st.detecting, ..Default::default() };
                    *shared.preview.lock().unwrap() = None;
                    if let Some(spec) = spec {
                        st.source = Some(spec.label());
                        match Source::open(&spec) {
                            Ok(s) => {
                                (st.w, st.h, st.fps) = (s.w, s.h, s.fps);
                                shared.log(format!("opened {} ({}x{} at {:.2} fps)", spec.label(), s.w, s.h, s.fps));
                                source = Some(s);
                            }
                            Err(e) => {
                                shared.log(format!("could not open {}: {e}", spec.label()));
                                st.error = Some(e);
                            }
                        }
                    }
                    drop(st);
                    repaint();
                }
                Ok(Cmd::Crop(c)) => crop = c,
                Ok(Cmd::Detect(d)) => {
                    live = None;
                    if let Some(d) = &d {
                        *shared.hint.lock().unwrap() = d.hint;
                    }
                    detect = d;
                    shared.status.lock().unwrap().detecting = detect.is_some();
                }
                Ok(Cmd::NewRun) => {
                    live = None; // a fresh detector: no previous seed to chain from
                    shared.entries.lock().unwrap().clear();
                    shared.version.fetch_add(1, Ordering::SeqCst);
                    shared.status.lock().unwrap().screens = 0;
                    repaint();
                }
                Ok(Cmd::FindFeed(on)) => {
                    finder = on.then(FeedFinder::new);
                    *shared.feed.lock().unwrap() = (0, None);
                }
                Ok(Cmd::View(v)) => {
                    if let Some(d) = detect.as_mut() {
                        d.view = v.clone();
                    }
                    let entries = shared.entries.lock().unwrap();
                    for e in entries.iter() {
                        if let (Some(sub), Some(seed), Some(d)) = (e.sublevel_id(), e.layout_seed, detect.as_ref()) {
                            let _ = rtx.send(RenderJob { key: e.key, sublevel: sub, seed, judge: d.category.judge(), view: v.clone() });
                        }
                    }
                }
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => return,
            }
        }

        let Some(src) = source.as_ref() else {
            std::thread::sleep(Duration::from_millis(30));
            continue;
        };
        let frame = match src.rx.recv_timeout(Duration::from_millis(100)) {
            Ok(f) => f,
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                let mut st = shared.status.lock().unwrap();
                st.received_fps = 0.0;
                continue;
            }
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                shared.status.lock().unwrap().error = Some("the source stopped".into());
                source = None;
                continue;
            }
        };
        idx += 1;
        let now = Instant::now();
        fps_window.push_back(now);
        while fps_window.front().is_some_and(|t| now - *t > Duration::from_secs(2)) {
            fps_window.pop_front();
        }

        if let Some(f) = finder.as_mut() {
            // about four samples a second
            if idx % ((src.fps / 4.0).round().max(1.0) as usize) == 0 {
                let (g, step) = frame.small_gray(320);
                f.add(&g, step);
                *shared.feed.lock().unwrap() = (f.samples, f.find());
                repaint();
            }
        }

        if let (Some(d), Some(c)) = (detect.as_ref(), crop) {
            let (lv, _) = live.get_or_insert_with(|| new_live(&shared, d, src.fps));
            lv.push(idx, frame.gray(c));
            let on = lv.on_entry_screen();
            if on != was_on_screen {
                was_on_screen = on;
                let mut st = shared.status.lock().unwrap();
                st.on_entry_screen = on;
                if on {
                    st.screens += 1;
                }
                drop(st);
                repaint();
            }
        }

        // results
        if let (Some((lv, results)), Some(d)) = (live.as_ref(), detect.as_ref()) {
            let mut changed = false;
            while let Ok(r) = results.try_recv() {
                changed = true;
                let entry = apply(&shared, &r);
                if let (Some(sub), Some(seed)) = (entry.sublevel_id(), entry.layout_seed) {
                    if entry.png.is_none() {
                        let _ = rtx.send(RenderJob { key: entry.key, sublevel: sub, seed, judge: d.category.judge(), view: d.view.clone() });
                    }
                }
                if let Some(h) = lv.hint() {
                    *shared.hint.lock().unwrap() = Some((h.sy, h.ratio));
                }
            }
            if changed {
                shared.version.fetch_add(1, Ordering::SeqCst);
                repaint();
            }
        }

        {
            let mut st = shared.status.lock().unwrap();
            st.received_fps = fps_window.len() as f64 / 2.0;
            st.error = None;
        }
        // the preview: about 15 a second is plenty
        if now - last_preview > Duration::from_millis(66) {
            last_preview = now;
            *shared.preview.lock().unwrap() = Some(Arc::new(frame));
            shared.preview_n.fetch_add(1, Ordering::SeqCst);
            repaint();
        }
    }
}

fn parse_hex(s: &Option<String>) -> Option<u64> {
    s.as_deref().and_then(|t| u64::from_str_radix(t.trim_start_matches("0x"), 16).ok())
}

/// Fold a detector result into the run; returns the entry as it now is.
fn apply(shared: &Shared, r: &LiveResult) -> Entry {
    let mut entries = shared.entries.lock().unwrap();
    let seed = parse_hex(&r.layout_seed);
    let guess = r.sublevel_source != "digit";
    let i = match entries.iter().position(|e| e.key == r.run_start && e.cave == r.cave) {
        Some(i) => i,
        None => {
            entries.push(Entry {
                key: r.run_start,
                cave: r.cave.clone(),
                cave_name: r.cave_name.clone(),
                sublevel: None,
                sublevel_guess: true,
                layout_seed: None,
                confidence: String::new(),
                chained: false,
                ready_s: r.ready_after_s,
                png: None,
                score: None,
                render_error: None,
                version: 0,
            });
            entries.len() - 1
        }
    };
    let e = &mut entries[i];
    let redraw = e.layout_seed != seed || e.sublevel != r.sublevel;
    e.sublevel = r.sublevel;
    e.sublevel_guess = guess;
    e.layout_seed = seed;
    e.confidence = format!("{:?}", r.confidence).to_lowercase();
    e.chained = r.chained.is_some();
    if !r.update {
        e.ready_s = r.ready_after_s;
    }
    if redraw {
        e.png = None;
        e.score = None;
        e.version += 1;
    }
    shared.log(format!(
        "{} {}: {} ({}{})",
        e.title(),
        if r.update { "update" } else { "seed" },
        e.seed_text(),
        e.confidence,
        if e.chained { ", chained" } else { "" }
    ));
    e.clone()
}
