"""Pikmin 2's random number generator (same as CaveGen's Seed.java).

State update:  s' = (s * 0x41C64E6D + 0x3039) mod 2^32
Output:        rand = (s' >> 16) & 0x7FFF     (the state is advanced first)

Because the multiplier and increment are odd/affine mod 2^32, bit k of the
state only depends on bits <= k, and outputs only read bits 16..30. So bit 31
never matters and every seed can be reduced mod 2^31 (CaveGen's `clamp`).
"""

from __future__ import annotations

import numpy as np

A = 0x41C64E6D
C = 0x3039
M32 = 1 << 32
MASK32 = M32 - 1
MASK31 = (1 << 31) - 1
A_INV = pow(A, -1, M32)


def next_seed(s: int, n: int = 1) -> int:
    a, c = jump(n)
    return (a * s + c) & MASK32


def prev_seed(s: int, n: int = 1) -> int:
    return next_seed(s, -n)


def jump(n: int) -> tuple[int, int]:
    """(a, c) such that advancing the state n times is s -> a*s + c (mod 2^32). n may be negative."""
    if n < 0:
        base_a, base_c = A_INV, (-C * A_INV) & MASK32
        n = -n
    else:
        base_a, base_c = A, C
    a, c = 1, 0
    pa, pc = base_a, base_c
    while n:
        if n & 1:
            a, c = (pa * a) & MASK32, (pa * c + pc) & MASK32
        pa, pc = (pa * pa) & MASK32, (pa * pc + pc) & MASK32
        n >>= 1
    return a, c


def rand_after(s: int) -> tuple[int, int]:
    """Advance once; return (new state, 15-bit output)."""
    s = (s * A + C) & MASK32
    return s, (s >> 16) & 0x7FFF


def rands(s: int, n: int) -> list[int]:
    out = []
    for _ in range(n):
        s, r = rand_after(s)
        out.append(r)
    return out


def letter_velocities(seed: int, n: int) -> np.ndarray:
    """Starting velocities of the n falling characters drawn from `seed` (Seed.seed_to_vel_vector)."""
    return np.array(rands(seed, n), dtype=np.float32) * np.float32(5.0) / np.float32(32768.0)


def rand_of_state(states: np.ndarray) -> np.ndarray:
    """Output read from already-advanced states (vectorized)."""
    return (states >> np.uint64(16)) & np.uint64(0x7FFF)


def advance(states: np.ndarray, n: int) -> np.ndarray:
    """Advance a uint64 array of 32-bit states by n (may be negative)."""
    a, c = jump(n)
    return (states * np.uint64(a) + np.uint64(c)) & np.uint64(MASK32)


def forward_states(s0: int, n: int) -> np.ndarray:
    """States s0 advanced 1, 2, ..., n times (mod 2^32), as uint64. Built by doubling."""
    a = np.empty(n, np.uint64)
    c = np.empty(n, np.uint64)
    a[0], c[0] = A, C
    done = 1
    while done < n:
        m = min(done, n - done)
        ja, jc = jump(done)
        a[done:done + m] = (a[:m] * np.uint64(ja)) & np.uint64(MASK32)
        c[done:done + m] = (c[:m] * np.uint64(ja) + np.uint64(jc)) & np.uint64(MASK32)
        done += m
    return (a * np.uint64(s0 & MASK32) + c) & np.uint64(MASK32)


def distance(s0: int, target: int, limit: int = 1 << 24, block: int = 1 << 22) -> int | None:
    """Smallest n >= 1 with next_seed(s0, n) == target (both mod 2^31), if n <= limit."""
    t = np.uint64(target & MASK31)
    done, s = 0, s0
    while done < limit:
        b = min(block, limit - done)
        st = forward_states(s, b) & np.uint64(MASK31)
        hit = np.nonzero(st == t)[0]
        if len(hit):
            return done + int(hit[0]) + 1
        s = int(st[-1])
        done += b
    return None
