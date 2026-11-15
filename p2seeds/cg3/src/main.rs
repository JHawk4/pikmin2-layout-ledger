//! p2seeds' bridge to CaveGen3. Reads one JSON request per line on stdin and writes one JSON
//! answer per line on stdout:
//!
//!   {"sub": "SCx-6", "seed": "0x1234ABCD", "judge": "pod"}
//!     -> {"score": 123.4, "items": [{"name": "...", "value": 50, "carried_by": null}, ...]}
//!   {"sub": "SCx-6", "reference": 2000, "judge": "pod"}
//!     -> {"scores": [...]}       (judge scores of seeds 0, 1, ... spread over the RNG)
//!
//! An error answers {"error": "..."} for that line only.

use std::collections::HashMap;
use std::io::{BufRead, Write};
use std::sync::OnceLock;

use cavegen3::{GameData, Layout, SpawnObject, jhawk_judge::{JhawkJudge, JudgeType}};
use serde_json::{Value, json};

/// Pokos each creature is worth when carried back (name,minCarry,maxCarry,seeds,seedsMin,pokos,...),
/// the table CaveGen's judges use.
fn teki_pokos(name: &str) -> i64 {
    static T: OnceLock<HashMap<String, i64>> = OnceLock::new();
    T.get_or_init(|| {
        include_str!("../../../../cavegen3/data/resources/jhawk_judge/treasure_teki_config.csv")
            .lines()
            .filter_map(|l| {
                let f: Vec<&str> = l.trim().split(',').collect();
                Some((f.first()?.to_ascii_lowercase(), f.get(5)?.parse().ok()?))
            })
            .collect()
    })
    .get(&name.to_ascii_lowercase())
    .copied()
    .unwrap_or(0)
}

fn answer(data: &GameData, req: &Value) -> Result<Value, String> {
    let sub = req["sub"].as_str().ok_or("missing \"sub\"")?;
    let sublevel = data.sublevel(sub).map_err(|e| e.to_string())?;
    let ci = data.caveinfo(&sublevel).map_err(|e| e.to_string())?;
    let kind: JudgeType = req["judge"].as_str().unwrap_or("pod").parse().map_err(|_| "unknown judge".to_string())?;
    let judge = JhawkJudge::new(kind, ci);

    if let Some(n) = req["reference"].as_u64() {
        // evenly spaced seeds, like random ones but reproducible
        let step = (u32::MAX as u64 / n.max(1)) as u32;
        let scores: Vec<f64> = (0..n as u32).map(|i| judge.judge(&Layout::generate(i.wrapping_mul(step), ci))).collect();
        return Ok(json!({ "scores": scores }));
    }

    let seed_text = req["seed"].as_str().ok_or("missing \"seed\"")?;
    let seed = u32::from_str_radix(seed_text.trim_start_matches("0x").trim_start_matches("0X"), 16)
        .map_err(|e| format!("bad seed: {e}"))?;
    let layout = Layout::generate(seed, ci);
    let game = &ci.cave_cfg.game;
    let value = |name: &str| data.treasure(game, name).map(|t| t.value);
    let mut items = Vec::new();
    let mut teki: HashMap<String, i64> = HashMap::new();
    for (obj, _) in layout.spawn_objects() {
        match obj {
            SpawnObject::CapTeki(c, n) => {
                *teki.entry(c.internal_name.clone()).or_default() += *n as i64;
            }
            SpawnObject::Item(it) => items.push(json!({ "name": it.internal_name, "value": value(&it.internal_name), "carried_by": null })),
            SpawnObject::Teki(t, _) => {
                *teki.entry(t.internal_name.clone()).or_default() += 1;
                if let Some(c) = &t.carrying {
                    items.push(json!({ "name": c, "value": value(c), "carried_by": t.internal_name }));
                }
            }
            _ => {}
        }
    }
    // every creature on the layout and what it is worth: the most pokos creatures can give here
    let creature_pokos: i64 = teki.iter().map(|(n, c)| teki_pokos(n) * c).sum();
    let teki: Vec<Value> = teki.iter().map(|(n, c)| json!({ "name": n, "count": c, "pokos": teki_pokos(n) })).collect();
    Ok(json!({ "score": judge.judge(&layout), "items": items, "teki": teki, "creature_pokos": creature_pokos }))
}

fn main() {
    let data = match GameData::bundled() {
        Ok(d) => d,
        Err(e) => {
            eprintln!("cannot load CaveGen3 data: {e}");
            std::process::exit(2);
        }
    };
    let stdin = std::io::stdin();
    let mut out = std::io::stdout().lock();
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
