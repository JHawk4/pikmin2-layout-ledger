//! Pikmin 2's random number generators (rng.py; CaveGen's Seed.java).
//!
//! GameCube, Wii and Wii U: s' = s * 0x41C64E6D + 0x3039 (mod 2^32); output (s' >> 16) & 0x7FFF.
//! The free functions here are this generator.
//!
//! Switch (Pikmin 2 HD): musl libc's rand(), s' = s * 6364136223846793005 + 1 (mod 2^64), output
//! s' >> 33 (31 bits); see docs/switch-rng.md on the switch-rng branch. [`Gen`] covers both.

pub const A: u64 = 0x41C6_4E6D;
pub const C: u64 = 0x3039;
pub const MASK32: u64 = 0xFFFF_FFFF;
pub const MASK31: u64 = 0x7FFF_FFFF;

/// Inverse of A mod 2^32 (Newton iteration).
pub fn a_inv() -> u64 {
    let mut x: u64 = 1;
    for _ in 0..6 {
        x = x.wrapping_mul(2u64.wrapping_sub(A.wrapping_mul(x))) & MASK32;
    }
    x & MASK32
}

/// (a, c) such that advancing the state n times is s -> a*s + c (mod 2^32). n may be negative.
pub fn jump(n: i64) -> (u64, u64) {
    let (base_a, base_c, mut n) = if n < 0 {
        let ai = a_inv();
        (ai, (C.wrapping_neg().wrapping_mul(ai)) & MASK32, (-n) as u64)
    } else {
        (A, C, n as u64)
    };
    let (mut a, mut c) = (1u64, 0u64);
    let (mut pa, mut pc) = (base_a, base_c);
    while n > 0 {
        if n & 1 == 1 {
            a = pa.wrapping_mul(a) & MASK32;
            c = (pa.wrapping_mul(c).wrapping_add(pc)) & MASK32;
        }
        pc = (pa.wrapping_mul(pc).wrapping_add(pc)) & MASK32;
        pa = pa.wrapping_mul(pa) & MASK32;
        n >>= 1;
    }
    (a, c)
}

pub fn next_seed(s: u64, n: i64) -> u64 {
    let (a, c) = jump(n);
    (a.wrapping_mul(s).wrapping_add(c)) & MASK32
}

#[inline]
pub fn step(s: u64) -> u64 {
    (s.wrapping_mul(A).wrapping_add(C)) & MASK32
}

#[inline]
pub fn rand_of_state(s: u64) -> u64 {
    (s >> 16) & 0x7FFF
}

#[inline]
pub fn apply(ac: (u64, u64), s: u64) -> u64 {
    (s.wrapping_mul(ac.0).wrapping_add(ac.1)) & MASK32
}

pub const A64: u64 = 6_364_136_223_846_793_005;
pub const C64: u64 = 1;

/// (a, c) such that advancing the 64-bit Switch state n times is s -> a*s + c (mod 2^64).
pub fn jump64(n: i64) -> (u64, u64) {
    let (mut pa, mut pc, mut n) = if n < 0 {
        let mut ai: u64 = 1;
        for _ in 0..7 {
            ai = ai.wrapping_mul(2u64.wrapping_sub(A64.wrapping_mul(ai)));
        }
        (ai, C64.wrapping_neg().wrapping_mul(ai), n.unsigned_abs())
    } else {
        (A64, C64, n as u64)
    };
    let (mut a, mut c) = (1u64, 0u64);
    while n > 0 {
        if n & 1 == 1 {
            a = pa.wrapping_mul(a);
            c = pa.wrapping_mul(c).wrapping_add(pc);
        }
        pc = pa.wrapping_mul(pc).wrapping_add(pc);
        pa = pa.wrapping_mul(pa);
        n >>= 1;
    }
    (a, c)
}

/// Which `rand()` the game was built with.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Gen {
    /// GameCube, Wii, Wii U: Metrowerks MSL's 32-bit LCG, 15-bit outputs.
    #[default]
    Gc,
    /// Switch (Pikmin 2 HD): musl's 64-bit LCG, 31-bit outputs.
    Switch,
}

impl Gen {
    pub fn name(self) -> &'static str {
        match self {
            Gen::Gc => "gc",
            Gen::Switch => "switch",
        }
    }

    /// Hex digits of a seed: 8 on GC, 16 on Switch.
    pub fn digits(self) -> usize {
        match self {
            Gen::Gc => 8,
            Gen::Switch => 16,
        }
    }

    pub fn hex(self, s: u64) -> String {
        format!("{:0w$X}", s, w = self.digits())
    }

    /// Mask of a reported seed (the bits that matter): 2^31 - 1 on GC, all 64 on Switch.
    pub fn seed_mask(self) -> u64 {
        match self {
            Gen::Gc => MASK31,
            Gen::Switch => u64::MAX,
        }
    }

    /// (a, c) of n steps (n may be negative).
    pub fn jump(self, n: i64) -> (u64, u64) {
        match self {
            Gen::Gc => jump(n),
            Gen::Switch => jump64(n),
        }
    }

    /// s -> a*s + c in this generator's modulus.
    #[inline]
    pub fn apply(self, ac: (u64, u64), s: u64) -> u64 {
        match self {
            Gen::Gc => apply(ac, s),
            Gen::Switch => s.wrapping_mul(ac.0).wrapping_add(ac.1),
        }
    }

    #[inline]
    pub fn step(self, s: u64) -> u64 {
        match self {
            Gen::Gc => step(s),
            Gen::Switch => s.wrapping_mul(A64).wrapping_add(C64),
        }
    }

    /// The state n steps on (n may be negative). GC states are 32 bits.
    pub fn next(self, s: u64, n: i64) -> u64 {
        self.apply(self.jump(n), s)
    }

    /// What randFloat sees for the draw that left state `s`: GC rand/32768, Switch rand/2^31.
    #[inline]
    pub fn frac(self, s: u64) -> f64 {
        match self {
            Gen::Gc => rand_of_state(s) as f64 / 32768.0,
            Gen::Switch => (s >> 33) as f64 / 2147483648.0,
        }
    }

    /// Forward steps from `a` to `b` (both reduced to the seed mask on GC: a distance mod 2^31;
    /// Switch: exact over the full 2^64 period). 0 when equal.
    pub fn distance(self, a: u64, b: u64) -> u64 {
        match self {
            Gen::Gc => (index31(b) + (1u64 << 31) - index31(a)) % (1u64 << 31),
            Gen::Switch => distance64(a, b),
        }
    }
}

/// n in [0, 2^64) with the Switch state `s` advanced n times == `target` (PCG's advance distance).
pub fn distance64(mut s: u64, target: u64) -> u64 {
    let (mut cur_a, mut cur_c, mut d, mut bit) = (A64, C64, 0u64, 1u64);
    while s != target {
        if (s ^ target) & bit != 0 {
            s = s.wrapping_mul(cur_a).wrapping_add(cur_c);
            d |= bit;
        }
        cur_c = cur_a.wrapping_add(1).wrapping_mul(cur_c);
        cur_a = cur_a.wrapping_mul(cur_a);
        bit <<= 1;
    }
    d
}

/// The index n in [0, 2^31) of a GC state mod 2^31 in the sequence from 0 (the same lifting as
/// distance64, mod 2^31: bit k of the state has period 2^(k+1)).
pub fn index31(target: u64) -> u64 {
    let m = MASK31;
    let (mut s, target) = (0u64, target & m);
    let (mut cur_a, mut cur_c, mut d, mut bit) = (A, C, 0u64, 1u64);
    while s != target && bit < (1u64 << 31) {
        if (s ^ target) & bit != 0 {
            s = (s.wrapping_mul(cur_a).wrapping_add(cur_c)) & m;
            d |= bit;
        }
        cur_c = (cur_a.wrapping_add(1).wrapping_mul(cur_c)) & m;
        cur_a = cur_a.wrapping_mul(cur_a) & m;
        bit <<= 1;
    }
    d
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn switch_steps_and_distance() {
        let g = Gen::Switch;
        let s = 0x0123_4567_89AB_CDEF;
        assert_eq!(g.step(s), s.wrapping_mul(A64).wrapping_add(1));
        assert_eq!(g.next(g.next(s, 1000), -1000), s);
        let mut t = s;
        for _ in 0..777 {
            t = g.step(t);
        }
        assert_eq!(g.next(s, 777), t);
        for n in [1u64, 54_321, 1 << 40, 987_654_321_012] {
            assert_eq!(g.distance(s, g.next(s, n as i64)), n);
        }
        assert_eq!(g.hex(0x1234), "0000000000001234");
    }

    #[test]
    fn gc_distance() {
        let g = Gen::Gc;
        let s = 0x1234_5678;
        for n in [1u64, 999, 123_456_789] {
            assert_eq!(g.distance(s, g.next(s, n as i64)), n);
        }
        // bit 31 does not matter
        assert_eq!(g.distance(s ^ 0x8000_0000, g.next(s, 5)), 5);
        assert_eq!(g.hex(0xAB), "000000AB");
    }
    #[test]
    fn jumps_compose() {
        let s = 0x1234_5678;
        let mut t = s;
        for _ in 0..1000 {
            t = step(t);
        }
        assert_eq!(next_seed(s, 1000), t);
        assert_eq!(next_seed(t, -1000), s);
    }
}
