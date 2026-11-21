//! p2live command line.
//!
//!   p2live entries data/output/RUN/seeds.json [--jobs N] [--limit N] [--frames F1,F2] [--out FILE.jsonl]
//!
//! Re-analyzes every entry screen of a run the way profile_realtime.py does (detect around the
//! recorded frame, then analyze_event) and compares the seed with the one in seeds.json.

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
        _ => {
            eprintln!("usage: p2live entries SEEDS.json [--jobs N] [--limit N] [--frames F1,F2] [--out FILE.jsonl]");
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
    let opts = Options::default();
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
                    "cave_score": r.cave_score, "t_decode": t_decode, "t_analyze": t_analyze,
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
