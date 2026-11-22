//! Layout matcher: find the seeds whose layout agrees with what a video shows near the pod.
//!
//!   p2seeds-layoutmatch dump SUB SEED
//!       One layout as JSON: the pod (position, facing, its unit and spawn point), every spawned
//!       object (teki, plants, items, hole, geyser, gates) with its position in the pod's frame
//!       (`ahead` along the pod's facing, `side` to its right as seen on screen), and the units.
//!
//!   p2seeds-layoutmatch scan SUB END_STATE COUNT OBS.json OUT.bin
//!       Seeds k = 0..COUNT-1 are END_STATE stepped back k draws of the game's LCG (as itemscan).
//!       OBS.json is a list of observations, each {"names": [...], "ahead": a, "side": s, "tol": t}
//!       (an object whose name is one of `names`, within `tol` units of that point in the pod's
//!       frame) or {"names": [...], "absent_within": r} (no such object within r of the pod), or
//!       {"unit_spawn": [i, ...]} (the pod is at one of these spawn points of its unit).
//!       OUT.bin gets one little-endian u32 per seed: bit j set when observation j holds.
//!
//! Names are CaveGen3 internal names, compared without case: teki ("Tanpopo", "Damagumo"),
//! treasures ("gold_medal"; a carried treasure matches at its carrier), "hole", "geyser", "gate".

use std::io::Write;

use cavegen3::{GameData, Layout, SpawnObject};
use serde_json::{Value, json};

const A: u32 = 0x41C64E6D;
const C: u32 = 0x3039;

/// (a, c) of the LCG stepped n times: s -> a*s + c.
fn jump(mut n: u64) -> (u32, u32) {
    let (mut ra, mut rc) = (1u32, 0u32);
    let (mut a, mut c) = (A, C);
    while n > 0 {
        if n & 1 == 1 {
            ra = ra.wrapping_mul(a);
            rc = rc.wrapping_mul(a).wrapping_add(c);
        }
        c = c.wrapping_mul(a).wrapping_add(c);
        a = a.wrapping_mul(a);
        n >>= 1;
    }
    (ra, rc)
}

/// One spawned object: lower-case names it answers to, and its game position.
struct Obj {
    names: Vec<String>,
    kind: &'static str,
    x: f32,
    y: f32,
    z: f32,
}

fn objects(layout: &Layout) -> Vec<Obj> {
    let mut out = Vec::new();
    for (so, p) in layout.spawn_objects() {
        let (kind, names): (&str, Vec<String>) = match so {
            SpawnObject::Teki(t, _) => {
                let mut v = vec![t.internal_name.to_ascii_lowercase()];
                if let Some(c) = &t.carrying {
                    v.push(c.to_ascii_lowercase());
                }
                (if t.group == 6 { "plant" } else { "teki" }, v)
            }
            SpawnObject::CapTeki(c, _) => ("capteki", vec![c.internal_name.to_ascii_lowercase()]),
            SpawnObject::Item(it) => ("item", vec![it.internal_name.to_ascii_lowercase()]),
            SpawnObject::Gate(..) => ("gate", vec!["gate".into()]),
            SpawnObject::Hole(_) => ("hole", vec!["hole".into()]),
            SpawnObject::Geyser(_) => ("geyser", vec!["geyser".into()]),
            SpawnObject::Ship => continue,
            SpawnObject::Onion(_) => ("onion", vec!["onion".into()]),
        };
        out.push(Obj { names, kind, x: p.x(), y: p.y(), z: p.z() });
    }
    out
}

/// The pod's position and its frame: forward (sin a, cos a), right (-cos a, sin a), as the
/// landing-view code in views.py.
fn pod(layout: &Layout) -> Option<(f32, f32, f32, f32, usize, usize)> {
    let i = layout.ship? as usize;
    let sp = &layout.spawnpoints[i];
    let a = sp.angle.to_radians();
    let unit = sp.unit as usize;
    let first = layout.units[unit].first_spawnpoint as usize;
    Some((sp.pos.x(), sp.pos.z(), a.sin(), a.cos(), unit, i - first))
}

fn frame(px: f32, pz: f32, fx: f32, fz: f32, x: f32, z: f32) -> (f32, f32) {
    let (dx, dz) = (x - px, z - pz);
    let ahead = dx * fx + dz * fz;
    let side = dx * -fz + dz * fx;
    (ahead, side)
}

fn parse_seed(s: &str) -> u32 {
    u32::from_str_radix(s.trim_start_matches("0x").trim_start_matches("0X"), 16).expect("seed in hex")
}

fn dump(data: &GameData, sub: &str, seed: u32) {
    let sl = data.sublevel(sub).expect("sublevel");
    let ci = data.caveinfo(&sl).expect("caveinfo");
    let layout = Layout::generate(seed, ci);
    let Some((px, pz, fx, fz, unit, spi)) = pod(&layout) else {
        println!("{}", json!({"error": "no pod"}));
        return;
    };
    let objs: Vec<Value> = objects(&layout)
        .iter()
        .map(|o| {
            let (a, s) = frame(px, pz, fx, fz, o.x, o.z);
            json!({"kind": o.kind, "names": o.names, "x": o.x, "y": o.y, "z": o.z, "ahead": a, "side": s})
        })
        .collect();
    let units: Vec<Value> = layout
        .units
        .iter()
        .map(|u| {
            json!({"name": u.unit.unit_folder_name, "x": u.x, "z": u.z, "w": u.unit.width, "h": u.unit.height,
                   "rotation": u.unit.rotation})
        })
        .collect();
    let sp = &layout.spawnpoints[layout.ship.unwrap() as usize];
    println!(
        "{}",
        json!({"seed": format!("{seed:08X}"), "pod": {"x": px, "z": pz, "angle": sp.angle, "unit": unit,
               "unit_name": layout.units[unit].unit.unit_folder_name, "unit_spawn": spi},
               "objects": objs, "units": units})
    );
}

enum Obs {
    Near { names: Vec<String>, ahead: f32, side: f32, tol: f32 },
    Absent { names: Vec<String>, r: f32 },
    UnitSpawn(Vec<usize>),
}

fn parse_obs(v: &Value) -> Vec<Obs> {
    let names = |o: &Value| -> Vec<String> {
        o["names"].as_array().map(|a| a.iter().filter_map(|n| n.as_str().map(|s| s.to_ascii_lowercase())).collect()).unwrap_or_default()
    };
    v.as_array()
        .expect("OBS.json is a list")
        .iter()
        .map(|o| {
            if let Some(a) = o["unit_spawn"].as_array() {
                Obs::UnitSpawn(a.iter().map(|x| x.as_u64().unwrap() as usize).collect())
            } else if let Some(r) = o["absent_within"].as_f64() {
                Obs::Absent { names: names(o), r: r as f32 }
            } else {
                Obs::Near {
                    names: names(o),
                    ahead: o["ahead"].as_f64().expect("ahead") as f32,
                    side: o["side"].as_f64().expect("side") as f32,
                    tol: o["tol"].as_f64().unwrap_or(100.0) as f32,
                }
            }
        })
        .collect()
}

fn check(layout: &Layout, obs: &[Obs]) -> u32 {
    let Some((px, pz, fx, fz, _unit, spi)) = pod(layout) else { return 0 };
    let objs = objects(layout);
    let local: Vec<(f32, f32)> = objs.iter().map(|o| frame(px, pz, fx, fz, o.x, o.z)).collect();
    let mut bits = 0u32;
    for (j, ob) in obs.iter().enumerate() {
        let ok = match ob {
            Obs::Near { names, ahead, side, tol } => objs.iter().zip(&local).any(|(o, (a, s))| {
                o.names.iter().any(|n| names.contains(n)) && ((a - ahead).powi(2) + (s - side).powi(2)).sqrt() <= *tol
            }),
            Obs::Absent { names, r } => !objs
                .iter()
                .zip(&local)
                .any(|(o, (a, s))| o.names.iter().any(|n| names.contains(n)) && (a * a + s * s).sqrt() <= *r),
            Obs::UnitSpawn(v) => v.contains(&spi),
        };
        if ok {
            bits |= 1 << j;
        }
    }
    bits
}

fn scan(data: &GameData, sub: &str, end: u32, count: usize, obs_path: &str, out_path: &str) {
    let sl = data.sublevel(sub).expect("sublevel");
    let ci = data.caveinfo(&sl).expect("caveinfo");
    let obs = parse_obs(&serde_json::from_str(&std::fs::read_to_string(obs_path).expect("OBS.json")).expect("OBS json"));
    assert!(obs.len() <= 32, "at most 32 observations");
    let (ia, ic) = jump((1u64 << 32) - 1);
    let threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    let chunk = count.div_ceil(threads).max(1);
    let mut out = vec![0u32; count];
    std::thread::scope(|s| {
        for (t, part) in out.chunks_mut(chunk).enumerate() {
            let obs = &obs;
            s.spawn(move || {
                let k0 = t * chunk;
                let (ja, jc) = jump((1u64 << 32) - k0 as u64 % (1u64 << 32));
                let mut seed = if k0 == 0 { end } else { ja.wrapping_mul(end).wrapping_add(jc) };
                for v in part.iter_mut() {
                    *v = check(&Layout::generate(seed, ci), obs);
                    seed = ia.wrapping_mul(seed).wrapping_add(ic);
                }
            });
        }
    });
    let mut f = std::io::BufWriter::new(std::fs::File::create(out_path).expect("output"));
    for v in out {
        f.write_all(&v.to_le_bytes()).unwrap();
    }
}

/// Per seed: f32 pod spawn index in its unit, f32 pod unit index among units of the same name
/// (always 0 or 1 here), then per NAME the (ahead, side) of the nearest such object (NaN, NaN if
/// none). Rows of 2 + 2·len(NAMES) little-endian f32.
fn feat(data: &GameData, sub: &str, end: u32, count: usize, out_path: &str, names: &[String]) {
    let sl = data.sublevel(sub).expect("sublevel");
    let ci = data.caveinfo(&sl).expect("caveinfo");
    let names: Vec<String> = names.iter().map(|n| n.to_ascii_lowercase()).collect();
    let row = 2 + 2 * names.len();
    let (ia, ic) = jump((1u64 << 32) - 1);
    let threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    let chunk = count.div_ceil(threads).max(1);
    let mut out = vec![f32::NAN; count * row];
    std::thread::scope(|s| {
        for (t, part) in out.chunks_mut(chunk * row).enumerate() {
            let names = &names;
            s.spawn(move || {
                let k0 = t * chunk;
                let (ja, jc) = jump((1u64 << 32) - k0 as u64 % (1u64 << 32));
                let mut seed = if k0 == 0 { end } else { ja.wrapping_mul(end).wrapping_add(jc) };
                for r in part.chunks_mut(row) {
                    let layout = Layout::generate(seed, ci);
                    seed = ia.wrapping_mul(seed).wrapping_add(ic);
                    let Some((px, pz, fx, fz, unit, spi)) = pod(&layout) else { continue };
                    r[0] = spi as f32;
                    r[1] = unit as f32;
                    let objs = objects(&layout);
                    for (j, n) in names.iter().enumerate() {
                        let mut best = f32::INFINITY;
                        for o in objs.iter().filter(|o| o.names.contains(n)) {
                            let (a, sd) = frame(px, pz, fx, fz, o.x, o.z);
                            if a * a + sd * sd < best {
                                best = a * a + sd * sd;
                                r[2 + 2 * j] = a;
                                r[3 + 2 * j] = sd;
                            }
                        }
                    }
                }
            });
        }
    });
    let mut f = std::io::BufWriter::new(std::fs::File::create(out_path).expect("output"));
    for v in out {
        f.write_all(&v.to_le_bytes()).unwrap();
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let data = GameData::bundled().expect("CaveGen3 data");
    match args.get(1).map(String::as_str) {
        Some("feat") if args.len() >= 7 => feat(
            &data,
            &args[2],
            parse_seed(&args[3]),
            args[4].parse().expect("COUNT"),
            &args[5],
            &args[6..],
        ),
        Some("dump") if args.len() >= 4 => {
            for s in &args[3..] {
                dump(&data, &args[2], parse_seed(s));
            }
        }
        Some("scan") if args.len() == 7 => {
            scan(&data, &args[2], parse_seed(&args[3]), args[4].parse().expect("COUNT"), &args[5], &args[6])
        }
        _ => {
            eprintln!("usage: p2seeds-layoutmatch dump SUB SEED [SEED ...]\n       p2seeds-layoutmatch scan SUB END_STATE COUNT OBS.json OUT.bin");
            std::process::exit(1);
        }
    }
}
