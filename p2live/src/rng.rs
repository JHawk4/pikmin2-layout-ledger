//! Pikmin 2's random number generator (rng.py; CaveGen's Seed.java).
//!
//! State update s' = s * 0x41C64E6D + 0x3039 (mod 2^32); output (s' >> 16) & 0x7FFF.

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

#[cfg(test)]
mod tests {
    use super::*;
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
