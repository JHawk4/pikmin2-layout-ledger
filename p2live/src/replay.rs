//! `p2live replay`: play a video through the live detector as a capture would deliver it.
//!
//! With a seeds.json (instead of a video) the run's video and feed are used, and the seeds found
//! are compared with the offline ones. `--speed 1` paces frames to the wall clock with worker
//! threads (the honest latency test); `--speed 0` analyzes on the capture thread as fast as it
//! can and reports simulated latency (frames waited / fps + analysis time). `--double` repeats
//! every frame, like a 60 fps capture of the 30 fps game.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use p2live::analyze::Conf;
use p2live::live::{Live, LiveConfig, LiveResult};
use p2live::templates::{caves, POD_CAVES};
use p2live::video::{probe, Feed, Stream};
use serde_json::{json, Value};

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

pub fn replay(args: &[String]) {
    let src = &args[0];
    let mut known: Vec<Value> = Vec::new();
    let (video, mut feed_v) = if src.ends_with(".json") {
        let p = PathBuf::from(src);
        let d: Value = serde_json::from_str(&std::fs::read_to_string(&p).expect("read seeds.json")).expect("parse seeds.json");
        let root = arg(args, "--root").map(PathBuf::from).unwrap_or_else(|| p.canonicalize().unwrap().ancestors().nth(4).unwrap().to_path_buf());
        let v = d["meta"]["video"].as_str().unwrap().replace('\\', "/");
        let v = if Path::new(&v).is_absolute() { v } else { root.join(&v).to_string_lossy().to_string() };
        known = d["entries"].as_array().unwrap().iter().filter(|e| e["frame"].as_u64().is_some()).cloned().collect();
        let f = &d["meta"]["feed"];
        let g = |i: usize| f[i].as_u64().unwrap() as usize;
        (v, Some([g(0), g(1), g(2), g(3)]))
    } else {
        (src.clone(), None)
    };
    if let Some(f) = arg(args, "--feed") {
        let v: Vec<usize> = f.split(',').map(|x| x.parse().unwrap()).collect();
        feed_v = Some([v[0], v[1], v[2], v[3]]);
    }
    let info = probe(&video).expect("ffprobe");
    let feed = match feed_v {
        Some(f) => Feed { x0: f[0], y0: f[1], x1: f[2], y1: f[3] },
        None => Feed { x0: 0, y0: 0, x1: info.w, y1: info.h },
    };
    let speed: f64 = arg(args, "--speed").and_then(|x| x.parse().ok()).unwrap_or(1.0);
    let mult = if args.iter().any(|a| a == "--double") { 2 } else { 1 };
    let start_f = (arg(args, "--start").and_then(|x| x.parse::<f64>().ok()).unwrap_or(0.0) * info.fps) as usize;
    let stop_n = arg(args, "--duration").and_then(|x| x.parse::<f64>().ok()).map(|d| (d * info.fps) as usize);
    let cave_set = arg(args, "--caves").unwrap_or_else(|| "all".into());
    let cave_list: Vec<_> = caves()
        .into_iter()
        .filter(|c| match cave_set.as_str() {
            "en" => c.lang == "en",
            "ja" => c.lang == "ja",
            "pod" => c.lang == "en" && POD_CAVES.contains(&c.cavegen),
            "pod-ja" => c.lang == "ja" && POD_CAVES.contains(&c.cavegen),
            _ => true,
        })
        .collect();
    let mut cfg = LiveConfig::new(info.fps * mult as f64, cave_list);
    if let Some(t) = arg(args, "--tails") {
        cfg.tails = t.split(',').map(|x| x.parse().unwrap()).collect();
    }
    cfg.workers = if speed > 0.0 { arg(args, "--workers").and_then(|x| x.parse().ok()).unwrap_or(2) } else { 0 };
    cfg.chain = !args.iter().any(|a| a == "--no-chain");
    let fps = info.fps;
    let game_frame = move |run_start: usize| start_f + run_start / mult;
    let (mut live, rx) = Live::new(cfg.clone(), Box::new(|s| eprintln!("  {s}")));
    let printer = std::thread::spawn(move || {
        let mut rows: Vec<LiveResult> = Vec::new();
        let mut refined = 0usize;
        let mut firsts: Vec<f64> = Vec::new();
        for r in rx {
            let s = game_frame(r.run_start) as f64 / fps;
            let sub = format!("{}{}", r.sublevel.map(|x| x.to_string()).unwrap_or("?".into()), if r.sublevel_source == "digit" { "" } else { "~" });
            if r.update {
                if r.refined {
                    refined += 1;
                    eprintln!(
                        "[{}:{:05.2}] {}-{}  {}  {:?}{}  (full analysis, ready {:.2}s after settling)",
                        (s / 60.0) as u64,
                        s % 60.0,
                        r.cave,
                        sub,
                        r.letter_seed.as_deref().unwrap_or("none"),
                        r.confidence,
                        r.chained.map(|d| format!(" +chained {d}")).unwrap_or_default(),
                        r.ready_after_s
                    );
                } else {
                    eprintln!("[{}:{:05.2}] {}-{}  (sublevel read on screen)", (s / 60.0) as u64, s % 60.0, r.cave, sub);
                }
                if let Some(old) = rows.iter_mut().find(|x| x.run_start == r.run_start) {
                    *old = r;
                }
                continue;
            }
            eprintln!(
                "[{}:{:05.2}] {}-{}  {}  {:?}{}  ready {:.2}s after settling (name {:.2}{}, prefill {:.2}, analysis {:.2}, chain {:.2}) tail {}",
                (s / 60.0) as u64,
                s % 60.0,
                r.cave,
                sub,
                r.letter_seed.as_deref().unwrap_or("none"),
                r.confidence,
                r.chained.map(|d| format!(" +chained {d}")).unwrap_or_default(),
                r.ready_after_s,
                r.name_s,
                if r.hinted { " hinted" } else { "" },
                r.prefill_s,
                r.analyze_s,
                r.chain_s,
                r.tail
            );
            if r.letter_seed.is_some() {
                firsts.push(r.ready_after_s);
            }
            rows.push(r);
        }
        (rows, refined, firsts)
    });
    let mut stream = Stream::open(&video, &info, feed, start_f).expect("ffmpeg");
    let t_start = Instant::now();
    let (mut idx, mut n_in, mut max_lag) = (0usize, 0usize, 0.0f64);
    while stop_n.is_none_or(|n| n_in < n) {
        let Some(g) = stream.next() else { break };
        n_in += 1;
        for _ in 0..mult {
            if speed > 0.0 {
                let due = t_start + Duration::from_secs_f64(idx as f64 / cfg.fps / speed);
                let now = Instant::now();
                if now < due {
                    std::thread::sleep(due - now);
                } else {
                    max_lag = max_lag.max((now - due).as_secs_f64());
                }
                live.push(idx, g.clone());
            } else {
                live.push_at(idx, g.clone(), t_start);
            }
            idx += 1;
        }
    }
    let check_ms = 1000.0 * live.check_s / live.frames_seen.max(1) as f64;
    let hint = live.hint();
    live.close();
    let (rows, refined, first) = printer.join().unwrap();
    println!(
        "{n_in} frames ({:.0} s of video) in {:.0} s; entry-screen check {check_ms:.2} ms/frame; capture fell behind by at most {max_lag:.2} s; scale {hint:?}",
        n_in as f64 / info.fps,
        t_start.elapsed().as_secs_f64()
    );
    println!("analysis stage time (all threads): {}", crate::stage_report());
    if let Some(p) = arg(args, "--out") {
        let mut f = std::fs::File::create(p).unwrap();
        for r in &rows {
            let mut v = serde_json::to_value(r).unwrap();
            v["frame"] = json!(game_frame(r.run_start));
            let _ = writeln!(f, "{v}");
        }
    }
    // the first answer per entry and the final one (after refinements)
    let stats = |mut v: Vec<f64>| -> String {
        v.sort_by(|a, b| a.partial_cmp(b).unwrap());
        if v.is_empty() {
            return "none".into();
        }
        let q = |p: f64| v[((v.len() - 1) as f64 * p).round() as usize];
        format!("median {:.2} s, p90 {:.2} s, max {:.2} s ({} seeds)", q(0.5), q(0.9), q(1.0), v.len())
    };
    let fin: Vec<f64> = rows.iter().filter(|r| r.letter_seed.is_some()).map(|r| r.ready_after_s).collect();
    println!("first answer after the screen settled: {}", stats(first));
    println!("final answer ({refined} improved by a later analysis): {}", stats(fin));
    if known.is_empty() {
        return;
    }
    // compare with the offline seeds of the entries inside the played stretch
    let hi = stop_n.map(|n| start_f + n).unwrap_or(usize::MAX);
    let inside: Vec<&Value> = known
        .iter()
        .filter(|e| {
            let f = e["frame"].as_u64().unwrap() as usize;
            f >= start_f + 150 && f < hi
        })
        .collect();
    let (mut same, mut wrong, mut wrong_sure, mut sub_ok, mut sub_n) = (0, 0, 0, 0, 0);
    let mut matched = std::collections::HashSet::new();
    for r in &rows {
        let f = game_frame(r.run_start) as i64;
        let e = inside
            .iter()
            .filter(|e| {
                let ef = e["frame"].as_u64().unwrap() as i64;
                ef >= f - 30 && ef <= f + 600
            })
            .min_by_key(|e| (e["frame"].as_u64().unwrap() as i64 - f).abs());
        let Some(e) = e else { continue };
        matched.insert(e["frame"].as_u64().unwrap());
        if let Some(es) = e["sublevel"].as_u64() {
            sub_n += 1;
            if r.sublevel == Some(es as u32) {
                sub_ok += 1;
            } else {
                println!("  sublevel: frame {} {} live {:?} ({}) offline {}", e["frame"], r.cave, r.sublevel, r.sublevel_source, es);
            }
        }
        let exp = e["letter_seed"].as_str().map(|s| s.to_string());
        if r.letter_seed.is_some() && exp == r.letter_seed {
            same += 1;
        } else if r.letter_seed.is_some() && exp.is_some() {
            wrong += 1;
            if r.confidence == Conf::High || r.chained.is_some() {
                wrong_sure += 1;
            }
            println!(
                "  differs: frame {} {}-{:?} live {} {:?}{} offline {} {}",
                e["frame"],
                r.cave,
                r.sublevel,
                r.letter_seed.as_deref().unwrap_or("-"),
                r.confidence,
                if r.chained.is_some() { " chained" } else { "" },
                exp.as_deref().unwrap_or("-"),
                e["confidence"]
            );
        }
    }
    let with_seed: Vec<&&Value> = inside.iter().filter(|e| e["letter_seed"].as_str().is_some()).collect();
    let missed: Vec<String> = with_seed
        .iter()
        .filter(|e| !matched.contains(&e["frame"].as_u64().unwrap()))
        .map(|e| format!("{}-{} @{}", e["cave"].as_str().unwrap_or("?"), e["sublevel"], e["frame"]))
        .collect();
    println!(
        "offline entries with a seed: {}; live seeds equal {same}, differ {wrong} ({wrong_sure} of them high or chained); no live result for {}; sublevel equal {sub_ok}/{sub_n}",
        with_seed.len(),
        missed.len()
    );
    if !missed.is_empty() {
        println!("  no live result: {}", missed.join(", "));
    }
}
