//! judge2 command line. One JSON request per line on stdin, one JSON answer per line on stdout:
//!
//!   {"sub": "SH-6", "seed": "0x1234ABCD"}
//!     -> {"old": 17.4, "pod2": 21.0, "parts": {...}, "pod2_parts": {...}}
//!   {"sub": "SH-6", "seed": "0x1234ABCD", "dump": true}
//!     -> the same plus "layout": every treasure, teki, gate and the hole with its geometry
//!   {"sub": "SH-6", "reference": 1000}
//!     -> {"old": [...], "pod2": [...]} for evenly spaced seeds (like p2seeds' cg3 bridge)
//!
//! Or with arguments: judge2 SH-6 0x1234ABCD [more seeds...]   (prints old and pod2 scores)

mod features;
mod graph;
mod old_judge;
mod pod2;

use std::io::{BufRead, Write};

use cavegen3::{GameData, Layout};
use old_judge::{JhawkJudge, JudgeType};
use serde_json::{Value, json};

fn parse_seed(s: &str) -> Result<u32, String> {
    u32::from_str_radix(s.trim_start_matches("0x").trim_start_matches("0X"), 16).map_err(|e| format!("bad seed: {e}"))
}

fn answer(data: &GameData, req: &Value) -> Result<Value, String> {
    let sub = req["sub"].as_str().ok_or("missing \"sub\"")?;
    let sublevel = data.sublevel(sub).map_err(|e| e.to_string())?;
    let ci = data.caveinfo(&sublevel).map_err(|e| e.to_string())?;
    let judge = JhawkJudge::new(JudgeType::Pod, ci);

    if let Some(n) = req["reference"].as_u64() {
        let step = (u32::MAX as u64 / n.max(1)) as u32;
        let mut old = Vec::new();
        let mut new = Vec::new();
        for i in 0..n as u32 {
            let layout = Layout::generate(i.wrapping_mul(step), ci);
            old.push(judge.judge(&layout));
            new.push(pod2::judge(&judge, &layout).total);
        }
        return Ok(json!({ "old": old, "pod2": new }));
    }

    let seed = parse_seed(req["seed"].as_str().ok_or("missing \"seed\"")?)?;
    let layout = Layout::generate(seed, ci);
    let parts = judge.judge_pod_parts(&layout);
    let p2 = pod2::judge(&judge, &layout);
    let mut out = json!({
        "old": parts.total(),
        "pod2": p2.total,
        "parts": {
            "walking": parts.walking_seconds, "carry": parts.carry_seconds, "hazard": parts.hazard_seconds,
            "gate": parts.gate_seconds, "optional": parts.optional_seconds, "poko": parts.poko_seconds,
            "adj": parts.adj_seconds, "treasures": parts.treasures, "bug_pokos": parts.bug_pokos,
        },
        "pod2_parts": p2.parts,
    });
    if req["dump"].as_bool().unwrap_or(false) {
        out["layout"] = pod2::dump(&judge, &layout);
    }
    Ok(out)
}

fn main() {
    let data = match GameData::bundled() {
        Ok(d) => d,
        Err(e) => {
            eprintln!("cannot load CaveGen3 data: {e}");
            std::process::exit(2);
        }
    };
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut out = std::io::stdout().lock();
    if !args.is_empty() {
        let sub = &args[0];
        for seed in &args[1..] {
            let reply = answer(&data, &json!({"sub": sub, "seed": seed})).unwrap_or_else(|e| json!({ "error": e }));
            let _ = writeln!(out, "{sub} {seed} old {} pod2 {}", reply["old"], reply["pod2"]);
        }
        return;
    }
    let stdin = std::io::stdin();
    for line in stdin.lock().lines() {
        let Ok(line) = line else { break };
        if line.trim().is_empty() {
            continue;
        }
        let reply = match serde_json::from_str::<Value>(&line) {
            Ok(req) => answer(&data, &req).unwrap_or_else(|e| json!({ "error": e })),
            Err(e) => json!({ "error": format!("bad request: {e}") }),
        };
        let _ = writeln!(out, "{reply}");
        let _ = out.flush();
    }
}
