"""Pikmin 2's random number generators.

GameCube, Wii and Wii U ("gc", the default; same as CaveGen's Seed.java), MSL's rand():
    State update:  s' = (s * 0x41C64E6D + 0x3039) mod 2^32
    Output:        rand = (s' >> 16) & 0x7FFF     (the state is advanced first)
    randFloat = rand / 32768
Because the multiplier and increment are odd/affine mod 2^32, bit k of the
state only depends on bits <= k, and outputs only read bits 16..30. So bit 31
never matters and every seed can be reduced mod 2^31 (CaveGen's `clamp`).

Switch (Pikmin 2 HD, "switch"), musl libc's rand() (docs/switch-rng.md section 7):
    State update:  s' = (s * 6364136223846793005 + 1) mod 2^64
    Output:        rand = s' >> 33  (31 bits), randFloat = rand / (2^31 - 1)
Seeds are full 64-bit states.

The generator in use is module state: `use("switch")`, or `with using("switch"):`. Everything
here (jump, next_seed, distance, forward_states, speed_of_state, letter_velocities) follows it;
rand_after / rands / rand_of_state / index are the GC generator's 15-bit outputs only.
"""

from __future__ import annotations

from contextlib import contextmanager

import numpy as np

A = 0x41C64E6D
C = 0x3039
M32 = 1 << 32
MASK32 = M32 - 1
MASK31 = (1 << 31) - 1
A_INV = pow(A, -1, M32)

# Switch (musl)
A64 = 6364136223846793005
C64 = 1
M64 = 1 << 64
MASK64 = M64 - 1
A64_INV = pow(A64, -1, M64)

GENERATORS = ("gc", "switch")
_active = "gc"


def use(name: str) -> None:
    """Select the generator for everything in this module ("gc" or "switch")."""
    global _active
    if name not in GENERATORS:
        raise ValueError(f"unknown generator {name!r}; expected one of {GENERATORS}")
    _active = name


def active() -> str:
    return _active


@contextmanager
def using(name: str):
    prev = _active
    use(name)
    try:
        yield
    finally:
        use(prev)


def for_platform(platform: str | None) -> str:
    """Generator for a speedrun.com platform name ("Switch" -> switch, anything else -> gc)."""
    return "switch" if platform and "switch" in platform.lower() else "gc"


def state_mask() -> int:
    """Mask of the state arithmetic (2^32 - 1 on GC, 2^64 - 1 on Switch)."""
    return MASK64 if _active == "switch" else MASK32


def seed_mask() -> int:
    """Mask of a reported seed (the bits that matter): 2^31 - 1 on GC, 2^64 - 1 on Switch."""
    return MASK64 if _active == "switch" else MASK31


def seed_hex(s: int | None) -> str | None:
    """A seed as written in seeds.json and the reports (8 hex digits on GC, 16 on Switch)."""
    if s is None:
        return None
    return f"0x{s:016X}" if _active == "switch" else f"0x{s:08X}"


def next_seed(s: int, n: int = 1) -> int:
    a, c = jump(n)
    return (a * s + c) & state_mask()


def prev_seed(s: int, n: int = 1) -> int:
    return next_seed(s, -n)


def jump(n: int) -> tuple[int, int]:
    """(a, c) such that advancing the state n times is s -> a*s + c (mod 2^32, or 2^64 on Switch).
    n may be negative."""
    if _active == "switch":
        return _jump64(n)
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


def _jump64(n: int) -> tuple[int, int]:
    if n < 0:
        ba, bc, n = A64_INV, (-C64 * A64_INV) & MASK64, -n
    else:
        ba, bc = A64, C64
    a, c = 1, 0
    while n:
        if n & 1:
            a, c = (ba * a) & MASK64, (ba * c + bc) & MASK64
        ba, bc = (ba * ba) & MASK64, (ba * bc + bc) & MASK64
        n >>= 1
    return a, c


def speed_of_state(states: np.ndarray) -> np.ndarray:
    """Letter speed (5 * randFloat) of the draw that left each (already advanced) state, float64."""
    if _active == "switch":
        return (states >> np.uint64(33)).astype(np.float64) * (5.0 / ((1 << 31) - 1))
    return rand_of_state(states).astype(np.float64) * (5.0 / 32768.0)


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
    if _active == "switch":
        return speed_of_state(forward_states(seed, n)).astype(np.float32)
    return np.array(rands(seed, n), dtype=np.float32) * np.float32(5.0) / np.float32(32768.0)


def rand_of_state(states: np.ndarray) -> np.ndarray:
    """Output read from already-advanced states (vectorized)."""
    return (states >> np.uint64(16)) & np.uint64(0x7FFF)


def advance(states: np.ndarray, n: int) -> np.ndarray:
    """Advance a uint64 array of states by n (may be negative)."""
    a, c = jump(n)
    with np.errstate(over="ignore"):
        return (states * np.uint64(a) + np.uint64(c)) & np.uint64(state_mask())


def forward_states(s0: int, n: int) -> np.ndarray:
    """States s0 advanced 1, 2, ..., n times (mod 2^32, or 2^64 on Switch), as uint64.
    Built by doubling (uint64 arithmetic wraps mod 2^64)."""
    mask = np.uint64(state_mask())
    a = np.empty(n, np.uint64)
    c = np.empty(n, np.uint64)
    a[0], c[0] = jump(1)
    done = 1
    with np.errstate(over="ignore"):
        while done < n:
            m = min(done, n - done)
            ja, jc = jump(done)
            a[done:done + m] = (a[:m] * np.uint64(ja)) & mask
            c[done:done + m] = (c[:m] * np.uint64(ja) + np.uint64(jc)) & mask
            done += m
        return (a * np.uint64(s0 & int(mask)) + c) & mask


_M4 = 4 * M32
_C_INV = pow(C, -1, M32)
M31 = 1 << 31


def _v2(x: int) -> int:
    """2-adic valuation of x mod 4*2^32 (how many times 2 divides it); 0 counts as infinite."""
    x %= _M4
    return 1 << 40 if x == 0 else (x & -x).bit_length() - 1


def index(s: int) -> int:
    """n such that advancing state 0 n times gives s (mod 2^31): the seed's position in the
    RNG sequence, in O(log) time. Port of CaveGen's Seed.nth_inv (lifting the exponent):
    the n-th state from 0 is C*(A^n - 1)/(A - 1), so A^n = s*(A-1)/C + 1 (mod 4*2^32), and
    n is recovered one bit at a time by checking which choice makes A^n agree with that in
    more low bits."""
    x = s & MASK31
    target = (x * (A - 1) * _C_INV + 1) % _M4
    n, p = 0, 1
    for _ in range(32):
        if _v2(pow(A, n + p, _M4) - target) > _v2(pow(A, n, _M4) - target):
            n += p
        p *= 2
    return n % M31


def distance(s0: int, target: int, limit: int = 1 << 24, block: int | None = None) -> int | None:
    """Smallest n >= 1 with next_seed(s0, n) == target (both mod 2^31; 2^64 on Switch), if
    n <= limit. Exact and instant: via `index` on GC (the sequence mod 2^31 is one cycle of
    length 2^31), via the bitwise advance-distance algorithm (as in PCG) on Switch."""
    if _active == "switch":
        d = _distance64(s0 & MASK64, target & MASK64)
        if d == 0:
            d = M64
        return d if d <= limit else None
    d = (index(target) - index(s0)) % M31
    if d == 0:
        d = M31
    return d if d <= limit else None


def _distance64(s: int, target: int) -> int:
    """n in [0, 2^64) with the Switch state s advanced n times == target (full period, so it
    always exists). Bit k of the state has period 2^(k+1): fix the bits from the bottom up."""
    cur_a, cur_c, d, bit = A64, C64, 0, 1
    while s != target:
        if (s ^ target) & bit:
            s = (s * cur_a + cur_c) & MASK64
            d |= bit
        cur_c = ((cur_a + 1) * cur_c) & MASK64
        cur_a = (cur_a * cur_a) & MASK64
        bit <<= 1
    return d


def distance_brute(s0: int, target: int, limit: int = 1 << 24, block: int = 1 << 22) -> int | None:
    """Reference implementation of `distance` by stepping through the states."""
    t = np.uint64(target & seed_mask())
    done, s = 0, s0
    while done < limit:
        b = min(block, limit - done)
        st = forward_states(s, b) & np.uint64(seed_mask())
        hit = np.nonzero(st == t)[0]
        if len(hit):
            return done + int(hit[0]) + 1
        s = int(st[-1])
        done += b
    return None
