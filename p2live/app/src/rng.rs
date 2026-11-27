//! The game's `rand()` per console, for the menu timing and the manip.
//!
//! GameCube, Wii and Wii U: a 32-bit LCG; CaveGen works with 31-bit seeds, since bit 31 never
//! reaches an observed bit. Switch (Pikmin 2 HD): musl's 64-bit LCG, `rand() = s >> 33`.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Gen {
    /// GameCube, Wii, Wii U
    #[default]
    Gc,
    /// Pikmin 2 HD (Switch, 2023)
    Switch,
}

const A64: u64 = 6_364_136_223_846_793_005;
const C64: u64 = 1;
const A32: u64 = 0x41C6_4E6D;
const C32: u64 = 0x3039;

/// x -> a x + c composed n times, mod 2^64 (reduced by the caller for GC).
fn jump(a: u64, c: u64, mut n: u64) -> (u64, u64) {
    let (mut mul, mut add) = (1u64, 0u64);
    let (mut sm, mut sa) = (a, c);
    while n > 0 {
        if n & 1 == 1 {
            mul = mul.wrapping_mul(sm);
            add = add.wrapping_mul(sm).wrapping_add(sa);
        }
        sa = sa.wrapping_mul(sm).wrapping_add(sa);
        sm = sm.wrapping_mul(sm);
        n >>= 1;
    }
    (mul, add)
}

/// Steps from `from` to `to` of x -> a x + c mod 2^bits (full-period LCG), as in PCG.
fn lcg_distance(a: u64, c: u64, mut from: u64, to: u64, bits: u32) -> u64 {
    let mask = if bits == 64 { u64::MAX } else { (1u64 << bits) - 1 };
    let (mut cm, mut cp) = (a & mask, c & mask);
    let mut bit = 1u64;
    let mut d = 0u64;
    from &= mask;
    while from != to & mask {
        if (from & bit) != (to & bit) {
            from = (from.wrapping_mul(cm).wrapping_add(cp)) & mask;
            d |= bit;
        }
        bit <<= 1;
        cp = (cm.wrapping_add(1)).wrapping_mul(cp) & mask;
        cm = cm.wrapping_mul(cm) & mask;
        if bit == 0 {
            break;
        }
    }
    d
}

impl Gen {
    pub fn name(self) -> &'static str {
        match self {
            Gen::Gc => "gc",
            Gen::Switch => "switch",
        }
    }
    pub fn label(self) -> &'static str {
        match self {
            Gen::Gc => "GameCube / Wii / Wii U",
            Gen::Switch => "Switch (Pikmin 2 HD)",
        }
    }
    /// The seeds the manip works with: 31 bits on GC (CaveGen's), all 64 on Switch.
    pub fn mask(self) -> u64 {
        match self {
            Gen::Gc => 0x7FFF_FFFF,
            Gen::Switch => u64::MAX,
        }
    }
    /// `n` draws after `s` (n may be negative).
    pub fn next(self, s: u64, n: i64) -> u64 {
        match self {
            Gen::Gc => {
                let (m, a) = jump(A32, C32, n as u64 & 0xFFFF_FFFF);
                (s.wrapping_mul(m).wrapping_add(a)) & self.mask()
            }
            Gen::Switch => {
                let (m, a) = jump(A64, C64, n as u64);
                s.wrapping_mul(m).wrapping_add(a)
            }
        }
    }
    /// Draws from `a` forward to `b` (mod 2^31 on GC, where s and s ^ 2^31 are the same seed).
    pub fn distance(self, a: u64, b: u64) -> u64 {
        match self {
            Gen::Gc => lcg_distance(A32, C32, a, b, 32) & 0x7FFF_FFFF,
            Gen::Switch => lcg_distance(A64, C64, a, b, 64),
        }
    }
    /// What `rand() / RAND_MAX` gave for the draw that left the state at `s`.
    pub fn frac(self, s: u64) -> f64 {
        match self {
            Gen::Gc => ((s >> 16) & 0x7FFF) as f64 / 32768.0,
            Gen::Switch => (s >> 33) as f64 / 2147483648.0,
        }
    }
    pub fn hex(self, s: u64) -> String {
        match self {
            Gen::Gc => format!("{:08X}", s & 0xFFFF_FFFF),
            Gen::Switch => format!("{s:016X}"),
        }
    }
    pub fn parse(self, t: &str) -> Option<u64> {
        let t = t.trim().trim_start_matches("0x").trim_start_matches("0X");
        if t.is_empty() || t.len() > 16 {
            return None;
        }
        u64::from_str_radix(t, 16).ok().map(|v| v & self.mask())
    }
    /// The same console in the core detector.
    pub fn core(self) -> p2live::rng::Gen {
        match self {
            Gen::Gc => p2live::rng::Gen::Gc,
            Gen::Switch => p2live::rng::Gen::Switch,
        }
    }
    pub fn cavegen(self) -> cavegen3::Generator {
        match self {
            Gen::Gc => cavegen3::Generator::Gc,
            Gen::Switch => cavegen3::Generator::Switch,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gc_matches_p2live() {
        for &(s, n) in &[(0x1234_5678u64, 1000i64), (0x0404_7550, -1004), (5, 4505)] {
            assert_eq!(Gen::Gc.next(s, n), p2live::rng::next_seed(s, n) & 0x7FFF_FFFF);
        }
    }

    #[test]
    fn distances_invert_next() {
        for g in [Gen::Gc, Gen::Switch] {
            let a = g.next(0xDEAD_BEEF_1234, 0);
            for n in [0i64, 1, 4505, 123_456_789] {
                assert_eq!(g.distance(a, g.next(a, n)), n as u64, "{g:?} {n}");
            }
        }
    }

    #[test]
    fn switch_steps_like_cavegen3() {
        let mut r = cavegen3::rng::Rng::with(cavegen3::Generator::Switch, 77);
        r.advance(1000);
        assert_eq!(r.state(), Gen::Switch.next(77, 1000));
    }
}
