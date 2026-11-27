//! Prints fixed RNG sequences from CaveGen3's `Rng` (GC and Switch) as JSON, for
//! p2seeds/tests/test_rng_parity.py:
//!
//!     cargo run --release --manifest-path p2seeds/tests/cavegen3_rng/Cargo.toml > p2seeds/tests/data/cavegen3_rng.json

use cavegen3::rng::{Generator, Rng};

const STEPS: usize = 64;
const JUMPS: [u64; 6] = [1, 1000, 123_456_789, 1 << 31, (1 << 32) - 1, 0x0123_4567_89AB];

fn case(g: Generator, seed: u64) -> String {
    let mut r = Rng::with(g, seed);
    let (mut raws, mut states, mut floats) = (vec![], vec![], vec![]);
    for _ in 0..STEPS {
        let mut f = r.clone();
        floats.push(format!("{:?}", f.rand_f32()));
        raws.push(r.rand_raw().to_string());
        states.push(format!("\"{:#x}\"", r.state()));
    }
    let jumps: Vec<String> = JUMPS
        .iter()
        .map(|&n| {
            let mut j = Rng::with(g, seed);
            let v = j.advance(n);
            format!("{{\"n\": {n}, \"state\": \"{:#x}\", \"value\": {v}}}", j.state())
        })
        .collect();
    format!(
        "    {{\"generator\": \"{}\", \"seed\": \"{seed:#x}\",\n     \"rand\": [{}],\n     \"states\": [{}],\n     \"rand_f32\": [{}],\n     \"advance\": [{}]}}",
        g.name(),
        raws.join(", "),
        states.join(", "),
        floats.join(", "),
        jumps.join(", ")
    )
}

fn main() {
    let gc = [0u64, 1, 0x1234_5678, 0x7FFF_FFFF, 0xFFFF_FFFF, 0xDEAD_BEEF];
    let sw = [0u64, 1, 0x0123_4567_89AB_CDEF, 0xFFFF_FFFF_FFFF_FFFF, 0x9E37_79B9_7F4A_7C15];
    let mut cases: Vec<String> = gc.iter().map(|&s| case(Generator::Gc, s)).collect();
    cases.extend(sw.iter().map(|&s| case(Generator::Switch, s)));
    println!("{{\"cavegen3_rev\": \"{}\",\n \"cases\": [\n{}\n]}}", env!("CAVEGEN3_REV"), cases.join(",\n"));
}
