//! Pikmin 2 live layouts: the p2live seed detector on the OBS Virtual Camera (or any camera),
//! with a setup wizard, saved profiles, the layout drawn by CaveGen3, and an OBS Browser Source.
//!
//!   p2live-app                 the window
//!   p2live-app --cameras       list the cameras DirectShow sees
//!   p2live-app --grab NAME|VIDEO SECONDS [out.png]   read frames, report the rate
//!   p2live-app --layout SCx-3 0x1234ABCD out.png     draw one layout
//!   p2live-app --headless NAME|VIDEO [--find S] [--run S] [--category pod|at|attk|key|cmat|700k]
//!              [--console gc|switch] [--port P]
//!              the engine and the Browser Source without the window: find the game picture
//!              for --find seconds, then detect for --run seconds, printing the log
//!   p2live-app --build-times OUT_DIR [--samples N] [--kinds key,cmat,attk]
//!              the Challenge Mode times tables (times.rs), from N random layouts per level

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod capture;
mod chengine;
#[cfg(windows)]
#[allow(non_snake_case)]
mod dshow;
mod engine;
mod feed;
mod rng;
mod gui;
mod manip;
mod server;
mod settings;
mod times;

use std::time::{Duration, Instant};

use capture::{Source, SourceSpec};

fn attach_console() {
    // a windows-subsystem exe has no console; borrow the terminal's for the command-line tools
    #[cfg(all(windows, not(debug_assertions)))]
    unsafe {
        unsafe extern "system" {
            fn AttachConsole(pid: u32) -> i32;
        }
        AttachConsole(u32::MAX);
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(|s| s.as_str()) {
        None => {
            if let Err(e) = gui::run() {
                eprintln!("error: {e}");
                std::process::exit(1);
            }
        }
        Some("--cameras") => {
            attach_console();
            for c in capture::cameras() {
                println!("{c}");
            }
        }
        Some("--grab") => {
            attach_console();
            let name = args.get(2).cloned().unwrap_or_default();
            let secs: f64 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(3.0);
            let spec = if std::path::Path::new(&name).is_file() { SourceSpec::Video { path: name } } else { SourceSpec::Camera { name } };
            let src = match Source::open(&spec) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("error: {e}");
                    std::process::exit(1);
                }
            };
            println!("{}x{} at {:.2} fps", src.w, src.h, src.fps);
            let t0 = Instant::now();
            let mut n = 0;
            let mut last = None;
            while t0.elapsed().as_secs_f64() < secs {
                if let Ok(f) = src.rx.recv_timeout(Duration::from_millis(500)) {
                    n += 1;
                    last = Some(f);
                }
            }
            println!("{n} frames in {:.1} s ({:.1} fps received)", t0.elapsed().as_secs_f64(), n as f64 / t0.elapsed().as_secs_f64());
            if let (Some(f), Some(out)) = (last, args.get(4)) {
                let file = std::fs::File::create(out).unwrap();
                let mut enc = png::Encoder::new(std::io::BufWriter::new(file), f.w as u32, f.h as u32);
                enc.set_color(png::ColorType::Rgb);
                enc.write_header().unwrap().write_image_data(&f.rgb).unwrap();
                println!("wrote {out}");
            }
        }
        Some("--layout") => {
            attach_console();
            let data = cavegen3_cli::default_data_dir();
            let painter = cavegen3_cli::Painter::new(&data).expect("cavegen3 data");
            let seed = u64::from_str_radix(args[3].trim_start_matches("0x"), 16).unwrap();
            for _ in 0..2 {
                let t1 = Instant::now();
                let (_, png) = painter.png(&args[2], seed, &cavegen3_cli::render::Options::default()).expect("render");
                println!("rendered in {:.3} s, {} bytes", t1.elapsed().as_secs_f64(), png.len());
                std::fs::write(&args[4], png).unwrap();
            }
        }
        Some("--feed") => {
            // --feed VIDEO SECONDS [START]: the game picture found from SECONDS of video, read at full speed
            attach_console();
            let path = &args[2];
            let secs: f64 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(30.0);
            let start: f64 = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(0.0);
            let info = p2live::video::probe(path).expect("ffprobe");
            let full = p2live::video::Feed { x0: 0, y0: 0, x1: info.w, y1: info.h };
            let stream = p2live::video::Stream::open(path, &info, full, (start * info.fps) as usize).expect("ffmpeg");
            let mut f = feed::FeedFinder::new();
            let every = (info.fps / 4.0).round().max(1.0) as usize;
            for (i, g) in stream.take((secs * info.fps) as usize).enumerate() {
                if i % every == 0 {
                    let rgb: Vec<u8> = (0..g.h).flat_map(|y| g.row(y).to_vec()).flat_map(|v| [v, v, v]).collect();
                    let (small, step) = capture::Frame::from_rgb(g.w, g.h, rgb).small_gray(320);
                    f.add(&small, step);
                }
            }
            println!("{} samples: {:?}", f.samples, f.find());
        }
        Some("--probe-card") => {
            // --probe-card VIDEO FROM TO: the Challenge Mode screen tests, frame by frame
            attach_console();
            let path = &args[2];
            let (from, to): (usize, usize) = (args[3].parse().unwrap(), args[4].parse().unwrap());
            let info = p2live::video::probe(path).expect("ffprobe");
            let mut child = std::process::Command::new("ffmpeg")
                .args(["-v", "error", "-ss", &format!("{}", from as f64 / info.fps), "-i", path, "-frames:v", &(to - from).to_string(), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                .stdout(std::process::Stdio::piped())
                .spawn()
                .expect("ffmpeg");
            let mut out = child.stdout.take().unwrap();
            let mut buf = vec![0u8; info.w * info.h * 3];
            let mut i = from;
            while std::io::Read::read_exact(&mut out, &mut buf).is_ok() {
                let f = capture::Frame::from_rgb(info.w, info.h, buf.clone());
                println!("{i} {}", chengine::probe(&f, capture::Crop::full(info.w, info.h)));
                i += 1;
            }
        }
        Some("--build-times") => {
            // --build-times OUT_DIR [--samples N] [--kinds key,cmat,attk]
            attach_console();
            let out = std::path::PathBuf::from(args.get(2).cloned().unwrap_or_else(|| ".".into()));
            let samples: usize = opt(&args, "--samples", 20000);
            let kinds: String = opt(&args, "--kinds", String::from("key,cmat,attk"));
            let data = cavegen3::GameData::from_dir(engine::cavegen_data()).expect("cavegen3 data");
            for kind in kinds.split(',') {
                let t0 = Instant::now();
                let t = times::build(&data, kind, samples, &|s| println!("{s}")).expect("build");
                let path = out.join(format!("times_{kind}.json"));
                std::fs::write(&path, serde_json::to_string(&t).unwrap()).unwrap();
                println!("wrote {} in {:.0} s", path.display(), t0.elapsed().as_secs_f64());
            }
        }
        Some("--headless") => {
            attach_console();
            headless(&args[2..]);
        }
        _ => {
            attach_console();
            eprintln!("usage: p2live-app [--cameras | --grab NAME|VIDEO SECONDS [out.png] | --layout SUBLEVEL SEED out.png]");
        }
    }
}

fn opt<T: std::str::FromStr>(args: &[String], name: &str, default: T) -> T {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).and_then(|v| v.parse().ok()).unwrap_or(default)
}

fn headless(args: &[String]) {
    use engine::{Cmd, DetectCfg, Engine};
    use settings::{Category, Language, LayoutView};
    let name = args.first().cloned().unwrap_or_default();
    let spec = if std::path::Path::new(&name).is_file() { SourceSpec::Video { path: name } } else { SourceSpec::Camera { name } };
    let find: f64 = opt(args, "--find", 20.0);
    let run: f64 = opt(args, "--run", 60.0);
    let port: u16 = opt(args, "--port", 8787);
    let category = match opt(args, "--category", String::from("pod")).as_str() {
        "at" => Category::At,
        "attk" => Category::Attk,
        "key" => Category::Key,
        "cmat" => Category::Cmat,
        "700k" => Category::K700,
        _ => Category::Pod,
    };
    let console = match opt(args, "--console", String::from("gc")).as_str() {
        "switch" => rng::Gen::Switch,
        _ => rng::Gen::Gc,
    };
    let engine = Engine::start(Box::new(|| {}));
    let overlay = server::start(engine.shared.clone(), port);
    println!("Browser Source: {} {}", overlay.url(), overlay.error.clone().unwrap_or_default());
    engine.send(Cmd::Source(Some(spec)));
    engine.send(Cmd::FindFeed(true));
    let t0 = Instant::now();
    let mut printed = 0usize;
    let mut flush = |engine: &Engine| {
        let log = engine.shared.log.lock().unwrap();
        for l in log.iter().skip(printed.min(log.len())) {
            println!("  {l}");
        }
        printed = log.len();
    };
    while t0.elapsed().as_secs_f64() < find {
        std::thread::sleep(Duration::from_millis(500));
        flush(&engine);
    }
    let (samples, crop) = *engine.shared.feed.lock().unwrap();
    let st = engine.shared.status.lock().unwrap().clone();
    println!("game picture after {samples} samples: {crop:?} (capture {}x{}, {:.1} fps received)", st.w, st.h, st.received_fps);
    let crop = crop.unwrap_or(capture::Crop::full(st.w, st.h));
    engine.send(Cmd::FindFeed(false));
    engine.send(Cmd::Crop(Some(crop)));
    engine.send(Cmd::Detect(Some(DetectCfg { category, language: Language::Auto, hint: None, view: LayoutView::default(), manip: Default::default(), console })));
    let t1 = Instant::now();
    while t1.elapsed().as_secs_f64() < run {
        std::thread::sleep(Duration::from_millis(500));
        flush(&engine);
    }
    for e in engine.shared.entries.lock().unwrap().iter() {
        println!(
            "{:<28} {}  {}{}  ready {:.2}s  picture {}  judge {:?}",
            e.title(),
            e.seed_text(),
            e.confidence,
            if e.chained { " chained" } else { "" },
            e.ready_s,
            e.png.as_ref().map(|p| format!("{} bytes", p.len())).unwrap_or_else(|| "none".into()),
            e.score
        );
    }
    println!("hint {:?}", engine.shared.hint.lock().unwrap());
    let ch = engine.shared.ch.lock().unwrap().clone();
    if category.challenge().is_some() {
        println!("results screens {}, frame0 {:?}, played {:?}, busy {:?}, error {:?}", ch.screens, ch.frame0, ch.run.played, ch.busy, ch.error);
        println!("fades {}, level enters {}, title loops {}, run start {:?}, delta {:?}", ch.fades, ch.level_enters, ch.title_loops, ch.run_start, ch.delta(engine.shared.status.lock().unwrap().idx));
        if let Some(r) = &ch.roll {
            println!("last roll: {} end {:?} at {:?} ({})", r.final_display, r.end_state.map(|e| ch.rng.hex(e)), r.end_frame, r.note);
        }
        if let Some(p) = &ch.plan {
            println!("table {:?}, special {:?}", p.table, p.special);
            for o in p.options.iter().take(8) {
                println!(
                    "  CH{:<2} {:<22} {:>6} A at {:>5.1} s ±{:.1}  seed {} +{}  rank {:>4.1}%  delta {:>8.1}{}",
                    o.level,
                    chengine::level_name(o.level),
                    o.scroll,
                    o.target_frame as f64 / 30.0,
                    o.window as f64 / 60.0,
                    p.rng.hex(o.seed),
                    o.advances,
                    o.rank,
                    o.delta,
                    if o.no_key { " no key" } else { "" }
                );
            }
        }
    }
}
