//! p2live command line.
//!
//!   p2live entries data/output/RUN/seeds.json [--jobs N] [--limit N] [--frames F1,F2] [--out FILE.jsonl]
//!   p2live replay data/output/RUN/seeds.json [--speed 1|0] [--double] ...
//!
//! `entries` re-analyzes every entry screen of a run the way profile_realtime.py does (detect
//! around the recorded frame, then analyze_event) and compares the seed with the one in
//! seeds.json. `replay` plays a video through the live detector (src/replay.rs).

mod replay;

use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Instant;

use p2live::analyze::{analyze_event, detect, Conf, EntryResult, Event, Options, RESCUE_MARGIN, RESCUE_SCORE};
use p2live::video::{probe, Feed, Window};
use rayon::prelude::*;
use serde_json::{json, Value};

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

fn hex(s: Option<u64>) -> Value {
    s.map(|x| json!(format!("0x{:08X}", x))).unwrap_or(Value::Null)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(|s| s.as_str()) {
        Some("entries") => entries(&args[2..]),
        Some("replay") => replay::replay(&args[2..]),
        Some("challenge") => challenge_cmd(&args[2..]),
        _ => {
            eprintln!("usage: p2live entries SEEDS.json [--jobs N] [--limit N] [--frames F1,F2] [--out FILE.jsonl]");
            eprintln!("       p2live replay VIDEO|SEEDS.json [--feed x0,y0,x1,y1] [--start S] [--duration S] [--speed 1|0] [--double]");
            eprintln!("              [--caves all|en|ja|pod|pod-ja] [--tails 20,40] [--workers N] [--no-chain] [--out FILE.jsonl]");
            eprintln!("              [--rng gc|switch] [--anchor LAYOUT_SEED]   (entries takes --rng too)");
            std::process::exit(2);
        }
    }
}

fn entries(args: &[String]) {
    let seeds_path = PathBuf::from(&args[0]);
    let d: Value = serde_json::from_str(&std::fs::read_to_string(&seeds_path).expect("read seeds.json")).expect("parse seeds.json");
    let meta = &d["meta"];
    // seeds.json sits at <root>/data/output/<run>/seeds.json; its video path is relative to <root>
    let root: PathBuf = arg(args, "--root").map(PathBuf::from).unwrap_or_else(|| {
        seeds_path.canonicalize().unwrap().ancestors().nth(4).unwrap().to_path_buf()
    });
    let video = arg(args, "--video").unwrap_or_else(|| {
        let v = meta["video"].as_str().unwrap().replace('\\', "/");
        let p = Path::new(&v);
        if p.is_absolute() { v } else { root.join(p).to_string_lossy().to_string() }
    });
    let f = &meta["feed"];
    let feed = Feed { x0: f[0].as_u64().unwrap() as usize, y0: f[1].as_u64().unwrap() as usize, x1: f[2].as_u64().unwrap() as usize, y1: f[3].as_u64().unwrap() as usize };
    let info = probe(&video).expect("ffprobe");
    let fps = meta["fps"].as_f64().unwrap_or(info.fps);
    let jobs: usize = arg(args, "--jobs").and_then(|x| x.parse().ok()).unwrap_or(4);
    let limit: usize = arg(args, "--limit").and_then(|x| x.parse().ok()).unwrap_or(usize::MAX);
    let only_frames: Option<Vec<usize>> = arg(args, "--frames").map(|s| s.split(',').filter_map(|x| x.parse().ok()).collect());
    let mut list: Vec<Value> = d["entries"].as_array().unwrap().iter().filter(|e| e["frame"].as_u64().is_some()).cloned().collect();
    if let Some(fr) = &only_frames {
        list.retain(|e| fr.contains(&(e["frame"].as_u64().unwrap() as usize)));
    }
    list.truncate(limit);
    let out: Mutex<Box<dyn Write + Send>> = Mutex::new(match arg(args, "--out") {
        Some(p) => Box::new(std::fs::OpenOptions::new().create(true).append(true).open(p).unwrap()),
        None => Box::new(std::io::sink()),
    });
    let run = seeds_path.parent().and_then(|p| p.file_name()).map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let mut opts = Options::default();
    if arg(args, "--rng").as_deref() == Some("switch") {
        opts.rng = p2live::rng::Gen::Switch;
    }
    let pool = rayon::ThreadPoolBuilder::new().num_threads(jobs).build().unwrap();
    let t_all = Instant::now();
    let rows: Vec<Value> = pool.install(|| {
        list.par_iter()
            .map(|e| {
                let f = e["frame"].as_u64().unwrap() as usize;
                let t0 = Instant::now();
                let w = Window::new(&video, info.clone(), fps, feed, f.saturating_sub(720), f + 190).expect("decode");
                let t_decode = t0.elapsed().as_secs_f64();
                let t1 = Instant::now();
                let evs = detect(&w, f.saturating_sub(450), f + 150, 10, 300);
                let ev = evs.iter().min_by_key(|x| (x.last as i64 - f as i64).abs()).cloned().unwrap_or(Event { first: f, last: f });
                let res = analyze_event(&w, &ev, &opts, None);
                let mut r: EntryResult = res.into_iter().min_by_key(|r| (r.settled_frame.unwrap_or(0) as i64 - f as i64).abs()).unwrap();
                // the rescue pass (analyze.rescue_caves): an unrecognized screen whose near matches
                // include a Pay Off Debt cave is tried again with only that cave
                let mut rescued = false;
                if r.cave.is_none() {
                    let want = e["cave"].as_str().unwrap_or("");
                    if p2live::analyze::is_pod(want) && r.near.iter().any(|(c, sc, m)| c == want && *sc >= RESCUE_SCORE && *m >= RESCUE_MARGIN) {
                        let res = analyze_event(&w, &ev, &opts, Some(want));
                        if let Some(r2) = res.into_iter().min_by_key(|r| (r.settled_frame.unwrap_or(0) as i64 - f as i64).abs()) {
                            if r2.cave.is_some() {
                                r = r2;
                                rescued = true;
                            }
                        }
                    }
                }
                let t_analyze = t1.elapsed().as_secs_f64();
                let expected = e["letter_seed"].as_str().map(|s| s.to_string());
                let got = hex(r.letter_seed);
                let same = expected.as_deref() == got.as_str();
                let row = json!({
                    "run": run, "frame": f, "cave": r.cave.as_ref().map(|c| c.cavegen), "sublevel": r.digit_value,
                    "expected_cave": e["cave"], "expected_sublevel": e["sublevel"],
                    "letter_seed": got, "expected": expected, "same": same,
                    "confidence": r.confidence, "expected_confidence": e["confidence"],
                    "note": r.note, "expected_note": e["note"], "rescued": rescued,
                    "letters": r.fit.as_ref().map(|f| f.n_measured()), "rms_px": r.fit.as_ref().map(|f| f.rms_px),
                    "cave_score": r.cave_score, "settled": r.settled_frame, "digit_votes": r.digit_votes, "t_decode": t_decode, "t_analyze": t_analyze,
                    "extra_decodes": *w.extra_decodes.lock().unwrap(),
                });
                let mut o = out.lock().unwrap();
                let _ = writeln!(o, "{}", row);
                let _ = o.flush();
                eprintln!(
                    "{} {:>6} {:>4}-{:<2} {} {:<6} {}  {:.1}s",
                    run, f, row["cave"].as_str().unwrap_or("?"), r.digit_value.map(|x| x.to_string()).unwrap_or("?".into()),
                    if same { "ok  " } else { "DIFF" }, format!("{:?}", r.confidence).to_lowercase(), r.note, t_analyze
                );
                row
            })
            .collect()
    });
    let n = rows.len();
    let same = rows.iter().filter(|r| r["same"].as_bool().unwrap()).count();
    let high_wrong = rows.iter().filter(|r| r["confidence"] == json!(Conf::High) && !r["same"].as_bool().unwrap() && r["letter_seed"] != Value::Null).count();
    let t: Vec<f64> = rows.iter().map(|r| r["t_analyze"].as_f64().unwrap()).collect();
    let mut ts = t.clone();
    ts.sort_by(|a, b| a.partial_cmp(b).unwrap());
    println!(
        "{run}: {same}/{n} seeds equal, {high_wrong} high-confidence seeds that differ; analysis median {:.2}s max {:.2}s; wall {:.0}s",
        ts.get(n / 2).cloned().unwrap_or(0.0), ts.last().cloned().unwrap_or(0.0), t_all.elapsed().as_secs_f64()
    );
    println!("stage time (all threads): {}", stage_report());
}

pub fn stage_report() -> String {
    use std::sync::atomic::Ordering;
    p2live::analyze::STAGES
        .iter()
        .zip(p2live::analyze::STAGE_NS.iter())
        .map(|(n, t)| format!("{n} {:.1}s", t.load(Ordering::Relaxed) as f64 / 1e9))
        .collect::<Vec<_>>()
        .join(", ")
}

/// p2live challenge VIDEO [--out FILE.json] [--rng gc|switch] [--chain] [--anchor HEX]: every
/// results screen's score roll. `--chain` uses each decoded roll's end as the next screen's
/// anchor; `--anchor` gives the first one.
fn challenge_cmd(args: &[String]) {
    use p2live::challenge::{blue_fraction, decode_screen_with, Screens};
    use p2live::rng::Gen;
    let g = if arg(args, "--rng").as_deref() == Some("switch") { Gen::Switch } else { Gen::Gc };
    let chain = args.iter().any(|a| a == "--chain");
    let mut anchor: Option<u64> = arg(args, "--anchor").and_then(|a| u64::from_str_radix(a.trim_start_matches("0x"), 16).ok());
    use std::io::Read;
    let path = &args[0];
    let info = probe(path).expect("ffprobe");
    let (w, h) = (info.w, info.h);
    let mut child = std::process::Command::new(std::env::var("P2LIVE_FFMPEG").unwrap_or_else(|_| "ffmpeg".into()))
        .args(["-v", "error", "-nostdin", "-i", path, "-an", "-vf", "scale=in_color_matrix=bt601", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
        .expect("ffmpeg");
    let mut out = child.stdout.take().unwrap();
    let mut buf = vec![0u8; w * h * 3];
    let mut screens = Screens::new();
    let mut hint = None;
    let mut results = Vec::new();
    let t0 = Instant::now();
    let mut idx = 0usize;
    let mut handle = |frames: Vec<(usize, p2live::img::Gray)>, hint: &mut Option<p2live::challenge::Placement>, results: &mut Vec<Value>| {
        let t = Instant::now();
        if let Some(r) = decode_screen_with(&frames, hint.as_ref(), g, anchor) {
            *hint = Some(r.placement);
            if chain && (r.end_state.is_some() || r.first_state.is_some()) {
                anchor = r.end_state.or(r.first_state);
            }
            eprintln!(
                "  screen {}-{}: {} end {} at {:?} ({}{}, {:.2} s)",
                r.first_frame,
                r.last_frame,
                r.final_display,
                r.end_state.map(|s| format!("0x{}", g.hex(s))).unwrap_or("-".into()),
                r.end_frame,
                r.note,
                r.from_anchor.map(|d| format!(", {d} draws after the anchor")).unwrap_or_default(),
                t.elapsed().as_secs_f64()
            );
            results.push(serde_json::to_value(&r).unwrap());
        }
    };
    while out.read_exact(&mut buf).is_ok() {
        // blue share on a 160x90 grid of block means (cv2.resize INTER_AREA to 160x90)
        let idle = !screens.active();
        let blue = if idle && idx % 3 != 0 {
            0.0
        } else {
            let (sw, sh) = (160usize, 90usize);
            let mut small = vec![0u8; sw * sh * 3];
            for sy in 0..sh {
                let (y0, y1) = (sy * h / sh, ((sy + 1) * h / sh).max(sy * h / sh + 1));
                for sx in 0..sw {
                    let (x0, x1) = (sx * w / sw, ((sx + 1) * w / sw).max(sx * w / sw + 1));
                    let mut acc = [0u32; 3];
                    for y in y0..y1 {
                        for x in x0..x1 {
                            let i = (y * w + x) * 3;
                            acc[0] += buf[i] as u32;
                            acc[1] += buf[i + 1] as u32;
                            acc[2] += buf[i + 2] as u32;
                        }
                    }
                    let n = ((y1 - y0) * (x1 - x0)) as u32;
                    for c in 0..3 {
                        small[(sy * sw + sx) * 3 + c] = (acc[c] / n) as u8;
                    }
                }
            }
            blue_fraction(&small, sw, sh)
        };
        let gray = || {
            let mut g = vec![0u8; w * h];
            for i in 0..w * h {
                let (r, gg, b) = (buf[i * 3] as u32, buf[i * 3 + 1] as u32, buf[i * 3 + 2] as u32);
                g[i] = ((b * 1868 + gg * 9617 + r * 4899 + 8192) >> 14) as u8;
            }
            p2live::img::Gray::new(w, h, g)
        };
        if let Some(frames) = screens.push(idx, blue, gray) {
            handle(frames, &mut hint, &mut results);
        }
        idx += 1;
    }
    if let Some(frames) = screens.finish() {
        handle(frames, &mut hint, &mut results);
    }
    let _ = child.wait();
    eprintln!("{} frames, {} screens in {:.0} s", idx, results.len(), t0.elapsed().as_secs_f64());
    if let Some(p) = arg(args, "--out") {
        std::fs::write(p, serde_json::to_string_pretty(&results).unwrap()).unwrap();
    }
}
