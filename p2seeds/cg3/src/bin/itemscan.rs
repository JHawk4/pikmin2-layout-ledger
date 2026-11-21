//! Scan a run of layout seeds for where given items land relative to the pod.
//!
//!   p2seeds-itemscan SUB END_STATE COUNT OUT.bin ITEM [ITEM ...]
//!
//! Seed k (k = 0..COUNT-1) is END_STATE stepped back k draws of the game's LCG. For each seed and
//! each ITEM (internal name), OUT.bin gets one little-endian f32: the distance from the pod's spawn
//! point to the nearest copy of that item, or -1 when the item is not on the layout. Rows are
//! seeds, columns items. Used to filter challenge-mode dive candidates by a visible layout feature.

use std::io::Write;

use cavegen3::{GameData, Layout, SpawnObject};

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

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 6 {
        eprintln!("usage: p2seeds-itemscan SUB END_STATE COUNT OUT.bin ITEM [ITEM ...]");
        std::process::exit(1);
    }
    let sub = &args[1];
    let end = u32::from_str_radix(args[2].trim_start_matches("0x"), 16).expect("END_STATE in hex");
    let count: usize = args[3].parse().expect("COUNT");
    let out_path = &args[4];
    let items: Vec<String> = args[5..].to_vec();
    let data = GameData::bundled().expect("CaveGen3 data");
    let sl = data.sublevel(sub).expect("sublevel");
    let ci = data.caveinfo(&sl).expect("caveinfo");

    // the inverse step: 2^32 - 1 forward steps
    let (ia, ic) = jump((1u64 << 32) - 1);
    let threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    let chunk = count.div_ceil(threads);
    let ni = items.len();
    let mut out = vec![-1f32; count * ni];
    std::thread::scope(|s| {
        for (t, part) in out.chunks_mut(chunk * ni).enumerate() {
            let items = &items;
            s.spawn(move || {
                let k0 = t * chunk;
                let (ja, jc) = jump((1u64 << 32) - k0 as u64 % (1u64 << 32));
                let mut seed = if k0 == 0 { end } else { ja.wrapping_mul(end).wrapping_add(jc) };
                for row in part.chunks_mut(ni) {
                    let layout = Layout::generate(seed, ci);
                    if let Some(i) = layout.ship {
                        let p = layout.spawnpoints[i as usize].pos;
                        for (obj, q) in layout.spawn_objects() {
                            let name = match obj {
                                SpawnObject::Item(it) => it.internal_name.as_str(),
                                _ => continue,
                            };
                            if let Some(j) = items.iter().position(|n| n.eq_ignore_ascii_case(name)) {
                                let d = ((q.x() - p.x()).powi(2) + (q.z() - p.z()).powi(2)).sqrt();
                                if row[j] < 0.0 || d < row[j] {
                                    row[j] = d;
                                }
                            }
                        }
                    }
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
