"""Test candidate random-number generators against Challenge Mode score-roll digits.

Each digit on a rolling results screen is randInt(9) + 1 = floor(9 x / 32768) + 1, x the 15-bit
rand() value. The decomp divides rand() by 32768.0f, and Switch letter speeds still fill [0, 5),
so whatever replaced rand() on Switch still returns 15 bits. A digit therefore bounds x to a 1/9
interval. Early in a roll every digit rolls (14 per frame here), and consecutive game frames are
exactly 14 draws apart, so a few frames give 40-100 digits at known relative positions.

Two solvers, for two generator families:
- LCGs (mod 2^k or Lehmer mod p), x read from state bits [lo, lo+15): the state modulo 2^(lo+15)
  after each draw is affine in the first one, so a digit bounds it to one interval and
  lattice.box_points enumerates the states that fit every digit (as challenge_results does).
- GF(2)-linear generators (xorshift family, WELL): every output bit is an XOR of state bits.
  A digit fixes the top 1-3 bits of x (digits 1-4 mean the top bit is 0, 6-9 that it is 1, 1 and
  9 fix three bits), each a linear equation. Gaussian elimination gives the state.

A candidate is solved from a window of frames and must then predict the following frames' digits:
right about 1/9 of the time by chance, nearly always if it is the generator.

    python docs/switch/rng_candidates.py selftest
    python docs/switch/rng_candidates.py DIGITS.json [--frames 4] [--screens 0,1,2]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "p2seeds" / "src"))
from p2seeds.lattice import box_points  # noqa: E402

COUNTERS = ("pokos", "pikmin", "time", "total")
MIN_SCORE = 0.55


def x_range(d: int) -> tuple[int, int]:
    """Inclusive range of the 15-bit x that shows digit d (1..9)."""
    lo = -(-(d - 1) * 32768 // 9)
    hi = -(-d * 32768 // 9) - 1
    return lo, hi


def digit_of_x(x):
    return x * 9 // 32768 + 1


# --------------------------------------------------------------------------- LCG family

@dataclass
class LCG:
    name: str
    a: int
    c: int
    mod: int          # 2^k, or a prime for Lehmer (c = 0)
    lo: int           # x = (state >> lo) & 0x7FFF, read after the step

    @property
    def pow2(self) -> bool:
        return self.mod & (self.mod - 1) == 0

    @property
    def m(self) -> int:
        """Modulus that matters: bits above lo+15 never reach x for a power-of-two LCG."""
        return min(self.mod, 1 << (self.lo + 15)) if self.pow2 else self.mod

    def jump(self, n: int) -> tuple[int, int]:
        a, c, pa, pc = 1, 0, self.a, self.c
        m = self.mod
        while n:
            if n & 1:
                a, c = (pa * a) % m, (pa * c + pc) % m
            pa, pc = (pa * pa) % m, (pa * pc + pc) % m
            n >>= 1
        return a, c

    def x(self, s: int) -> int:
        return (s >> self.lo) & 0x7FFF

    def solve(self, obs: list[tuple[int, int]], max_nodes: int = 300_000) -> list[int] | None:
        """States s0 (after draw 0, mod self.m) fitting digits obs = [(pos, digit)]."""
        m = self.m
        p0 = obs[0][0]
        rows_a, lo, hi = [], [], []
        for p, d in obs:
            a, c = self.jump(p - p0)          # state at draw p from the state at draw p0
            xl, xh = x_range(d)
            L, H = xl << self.lo, (xh << self.lo) | ((1 << self.lo) - 1)
            rows_a.append(a % m)
            lo.append(L - c % m)
            hi.append(H - c % m)
        n = len(obs)
        # rows_a[0] == 1, so (rows_a, m e_1, ..., m e_{n-1}) is a basis of the lattice
        gens = [rows_a] + [[m if j == t else 0 for j in range(n)] for t in range(1, n)]
        pts = box_points(gens, lo, hi, max_nodes)
        if pts is None:
            return None
        A, C = self.jump(p0)
        inv = pow(A % m, -1, m)
        return sorted({((pt[0] - C) * inv) % m for pt in pts})

    def predict(self, s0: int, positions) -> list[int]:
        out = []
        for p in positions:
            a, c = self.jump(p)
            out.append(digit_of_x(self.x((a * s0 + c) % self.mod)))
        return out




# --------------------------------------------------------------------------- GF(2)-linear family

class Linear:
    """A GF(2)-linear generator on n32 32-bit words; step(words) -> (words, out32), vectorised
    over numpy uint32 arrays so all basis states run at once."""

    def __init__(self, name, n32, step, shift):
        self.name, self.n32, self._step, self.shift = name, n32, step, shift   # x = (out >> shift) & 0x7FFF
        self.n = 32 * n32

    def outputs(self, words, count):
        out = []
        st = [w.copy() for w in words]
        for _ in range(count):
            st, o = self._step(st)
            out.append(o)
        return out

    def basis_outputs(self, count):
        n = self.n
        words = [np.zeros(n, np.uint32) for _ in range(self.n32)]
        for b in range(n):
            words[b // 32][b] = np.uint32(1 << (b % 32))
        outs = self.outputs(words, count)
        # rows[t][k] = int bitmask over state bits of output bit k at draw t
        res = []
        for o in outs:
            per_bit = []
            for k in range(32):
                bits = ((o >> np.uint32(k)) & np.uint32(1)).astype(np.uint8)
                per_bit.append(int.from_bytes(np.packbits(bits[::-1]).tobytes(), "big") >> ((-n) % 8))
            res.append(per_bit)
        return res

    def solve(self, obs, rows):
        """State bitmask fitting the known x bits, or None (inconsistent / not enough rank)."""
        eqs = []
        for p, d in obs:
            xl, xh = x_range(d)
            for k in range(14, -1, -1):          # common leading bits of xl and xh
                if (xl >> k) & 1 != (xh >> k) & 1:
                    break
                eqs.append((rows[p][k + self.shift], (xl >> k) & 1))
        piv = {}
        for row, v in eqs:
            while row:
                top = row.bit_length() - 1
                if top in piv:
                    pr, pv = piv[top]
                    row ^= pr
                    v ^= pv
                else:
                    piv[top] = (row, v)
                    break
            else:
                if v:
                    return None
        if len(piv) < self.n:
            return "underdetermined"
        # back-substitute
        state = 0
        for top in sorted(piv):
            row, v = piv[top]
            rest = row & ~(1 << top)
            par = bin(rest & state).count("1") & 1
            if v ^ par:
                state |= 1 << top
        return state

    def predict(self, state, positions):
        words = [np.array([(state >> (32 * i)) & 0xFFFFFFFF], np.uint32) for i in range(self.n32)]
        outs = self.outputs(words, max(positions) + 1)
        return [digit_of_x(int((outs[p][0] >> np.uint32(self.shift)) & np.uint32(0x7FFF))) for p in positions]


def _shl(w, k):
    return (w << np.uint32(k)) & np.uint32(0xFFFFFFFF)


def xorshift128(st):
    """Marsaglia xorshift128, as in sead::Random."""
    x, y, z, w = st
    t = x ^ _shl(x, 11)
    nw = w ^ (w >> np.uint32(19)) ^ t ^ (t >> np.uint32(8))
    return [y, z, w, nw], nw


def xorshift32(st):
    (x,) = st
    x = x ^ _shl(x, 13)
    x = x ^ (x >> np.uint32(17))
    x = x ^ _shl(x, 5)
    return [x], x


def xorshift64(st):
    """Marsaglia xorshift64 (13, 7, 17) on (lo, hi) words; output the high word."""
    lo, hi = st
    # x ^= x << 13
    nlo = lo ^ _shl(lo, 13)
    nhi = hi ^ _shl(hi, 13) ^ (lo >> np.uint32(19))
    lo, hi = nlo, nhi
    # x ^= x >> 7
    nlo = lo ^ (lo >> np.uint32(7)) ^ _shl(hi, 25)
    nhi = hi ^ (hi >> np.uint32(7))
    lo, hi = nlo, nhi
    # x ^= x << 17
    nlo = lo ^ _shl(lo, 17)
    nhi = hi ^ _shl(hi, 17) ^ (lo >> np.uint32(15))
    return [nlo, nhi], nhi


def well512(st):
    """WELL512a (Lomont's version); state 16 words + index folded in by rotating the list."""
    s = st
    a = s[0]
    c = s[13]
    b = a ^ _shl(a, 16) ^ c ^ _shl(c, 15)
    c = s[9]
    c = c ^ (c >> np.uint32(11))
    a = b ^ c
    new0 = a
    d = new0 ^ (_shl(new0, 5) & np.uint32(0xDA442D24))
    s15 = s[15]
    new15 = s15 ^ _shl(s15, 2) ^ b ^ _shl(b, 18) ^ _shl(c, 28) ^ d
    # Lomont writes state[index] = a, index = (index + 15) & 15, state[index] = new value.
    # Rotating: the list is kept so that s[0] is state[index].
    s2 = list(s)
    s2[0] = new0
    s2 = [s2[15]] + s2[:15]       # index -> index + 15
    s2[0] = new15
    return s2, new15


# --------------------------------------------------------------------------- candidates

def lcg_candidates():
    out = []
    l32 = [("GC/MSL (control)", 0x41C64E6D, 0x3039), ("MSVC", 0x343FD, 0x269EC3),
           ("Borland", 22695477, 1), ("Numerical Recipes", 1664525, 1013904223),
           ("Unreal FRandomStream", 196314165, 907633515), ("Delphi", 134775813, 1),
           ("Turbo Pascal", 0x08088405, 1), ("glibc random TYPE_0 (=MSL consts)", 1103515245, 12345),
           ("cc65", 16843009, 826366247), ("Microsoft VB6 (mod 2^24)", 1140671485, 12820163)]
    for name, a, c in l32:
        mod = 1 << 24 if "2^24" in name else 1 << 32
        top = mod.bit_length() - 1
        for lo in sorted({0, 16, top - 15, top - 16}):
            if lo + 15 <= top:
                out.append(LCG(f"{name} bits {lo}-{lo + 14}", a, c, mod, lo))
    l64 = [("musl/newlib 64-bit", 6364136223846793005, 1), ("Knuth MMIX/PCG", 6364136223846793005, 1442695040888963407)]
    for name, a, c in l64:
        for lo in (32, 33, 48, 49):
            out.append(LCG(f"{name} bits {lo}-{lo + 14}", a, c, 1 << 64, lo))
    for lo in (17, 32, 33):
        out.append(LCG(f"Java Random bits {lo}-{lo + 14}", 0x5DEECE66D, 0xB, 1 << 48, lo))
    for a in (16807, 48271, 69621):
        for lo in (16,):
            out.append(LCG(f"Lehmer {a} mod 2^31-1 bits {lo}-{lo + 14}", a, 0, (1 << 31) - 1, lo))
    return out


def linear_candidates():
    out = []
    for shift in (17, 16, 0):
        out.append(Linear(f"xorshift128 / sead::Random >>{shift}", 4, xorshift128, shift))
        out.append(Linear(f"xorshift32 >>{shift}", 1, xorshift32, shift))
        out.append(Linear(f"xorshift64 (hi word) >>{shift}", 2, xorshift64, shift))
        out.append(Linear(f"WELL512a >>{shift}", 16, well512, shift))
    return out


# --------------------------------------------------------------------------- observations

def all_rolling_frames(screen: dict) -> list[dict]:
    """The frames before the first lock (every digit rolling), dups removed.
    A slot counts as locked from the frame it starts showing its final value for good."""
    frames = [f for f in screen["frames"] if not f["dup"]]
    first_lock = len(frames)
    for c in COUNTERS:
        for j in range(screen["n"][c]):
            vals = [f["d"][c][j][0] for f in frames]
            final = max(set(vals[-20:]), key=vals[-20:].count)
            t = len(vals)
            while t > 0 and vals[t - 1] == final:
                t -= 1
            # a rolling digit equals the final value 1/9 of the time; lock = start of the final run
            first_lock = min(first_lock, t)
    fr = frames[:first_lock]
    # drop the frames before the roll starts (blank or zero counters)
    start = 0
    while start < len(fr) and sum(1 <= d <= 9 and v >= MIN_SCORE for c in COUNTERS for d, v, _ in fr[start]["d"][c]) < 12:
        start += 1
    return fr[start:]


def frame_obs(frame: dict, n: dict, base: int) -> list[tuple[int, int]]:
    out, p = [], base
    for c in COUNTERS:
        for j in range(n[c]):
            d, v, _ = frame["d"][c][j]
            if v >= MIN_SCORE and 1 <= d <= 9:
                out.append((p, d))
            p += 1
    return out


GAP = 0   # extra draws assumed between frames (something else drawing once per frame)


def screen_windows(screen, k):
    """Yield (fit_obs, check_obs) for windows of k frames followed by up to 6 check frames,
    positions relative to the window's first draw, assuming 14 (+ GAP) draws per frame, no drops."""
    fr = all_rolling_frames(screen)
    per = sum(screen["n"].values()) + GAP
    for s in range(0, max(0, len(fr) - k - 1)):
        fit = [o for t in range(k) for o in frame_obs(fr[s + t], screen["n"], t * per)]
        chk = [o for t in range(k, min(len(fr) - s, k + 6)) for o in frame_obs(fr[s + t], screen["n"], t * per)]
        if chk:
            yield s, fit, chk


def score(pred, chk):
    return sum(p == d for p, (_, d) in zip(pred, chk))


# --------------------------------------------------------------------------- driver

def test_lcg(g: LCG, screens, k, max_windows=4):
    best = (0, 0, None)
    for sc in screens:
        tried = 0
        for s, fit, chk in screen_windows(sc, k):
            nfit = math.ceil((g.m.bit_length() + 10) / 3.17)
            fit, chk = fit[:nfit], fit[nfit:] + chk
            sols = g.solve(fit)
            tried += 1
            if sols is None:
                best = max(best, (0, len(chk), "enumeration too large"), key=lambda t: t[0])
            else:
                for s0 in sols[:2000]:
                    pred = g.predict(s0, [p for p, _ in chk])
                    sc_ = score(pred, chk)
                    if sc_ > best[0]:
                        best = (sc_, len(chk), f"state {s0:#x}, {len(sols)} fits")
            if tried >= max_windows:
                break
    return best


def test_linear(g: Linear, screens, k, max_windows=4):
    best = (0, 0, None)
    rows = None
    for sc in screens:
        tried = 0
        for s, fit, chk in screen_windows(sc, k):
            need = max(p for p, _ in fit + chk) + 1
            if rows is None or len(rows) < need:
                rows = g.basis_outputs(need)
            st = g.solve(fit, rows)
            tried += 1
            if isinstance(st, int):
                sc_ = score(g.predict(st, [p for p, _ in chk]), chk)
                if sc_ > best[0]:
                    best = (sc_, len(chk), "solved")
            elif best[2] is None:
                best = (0, len(chk), "inconsistent" if st is None else st)
            if tried >= max_windows:
                break
    return best


def synth_screen(digits_fn, frames=12, n=(4, 3, 3, 4)):
    nd = dict(zip(COUNTERS, n))
    per = sum(n)
    ds = digits_fn(frames * per)
    fr, p = [], 0
    for _ in range(frames):
        d = {}
        for c in COUNTERS:
            d[c] = [[int(ds[p + j]), 0.9, 0.3] for j in range(nd[c])]
            p += nd[c]
        fr.append(dict(i=len(fr), dup=False, d=d))
    # tail of locked frames so all_rolling_frames finds the lock
    fin = {c: [[1, 0.9, 0.3] for _ in range(nd[c])] for c in COUNTERS}
    fr += [dict(i=len(fr) + t, dup=False, d=fin) for t in range(25)]
    return dict(n=nd, frames=fr)


def selftest():
    rnd = random.Random(1)
    print("self-test: each generator on its own synthetic roll, then on a GC roll")
    gc = LCG("GC", 0x41C64E6D, 0x3039, 1 << 32, 16)

    def gc_digits(count, s=rnd.getrandbits(32)):
        out = []
        for _ in range(count):
            s = (s * gc.a + gc.c) & 0xFFFFFFFF
            out.append(digit_of_x(gc.x(s)))
        return out
    gc_screen = synth_screen(gc_digits)
    for g in lcg_candidates()[:3] + [c for c in lcg_candidates() if "64" in c.name or "Java" in c.name or "Lehmer" in c.name][::3]:
        s0 = rnd.randrange(g.mod)

        def dig(count, g=g, s0=s0):
            return g.predict(s0, list(range(count)))
        own = test_lcg(g, [synth_screen(dig)], 3, 1)
        other = test_lcg(g, [gc_screen], 3, 1)
        print(f"  {g.name:<44} own {own[0]}/{own[1]} ({own[2]})   GC roll {other[0]}/{other[1]}")
    for g in linear_candidates()[:8]:
        st = rnd.getrandbits(g.n)
        k = max(2, math.ceil(g.n / 14 / 1.5) + 1)

        def dig(count, g=g, st=st):
            return g.predict(st, list(range(count)))
        own = test_linear(g, [synth_screen(dig, frames=k + 8)], k, 1)
        other = test_linear(g, [synth_screen(gc_digits, frames=k + 8)], k, 1)
        print(f"  {g.name:<44} own {own[0]}/{own[1]} ({own[2]})   GC roll {other[0]}/{other[1]} ({other[2]})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("digits")
    ap.add_argument("--frames", type=int, default=0, help="fit window (default: per generator)")
    ap.add_argument("--screens", default="")
    ap.add_argument("--only", default="", help="substring filter on generator names")
    ap.add_argument("--skip", default="", help="comma-separated substrings of generator names to skip")
    ap.add_argument("--windows", type=int, default=4, help="fit windows tried per screen")
    ap.add_argument("--gaps", default="0", help="extra draws per frame to try, e.g. 0-40")
    a = ap.parse_args()
    if a.digits == "selftest":
        selftest()
        return
    screens = json.load(open(a.digits))
    if a.screens:
        screens = [screens[int(i)] for i in a.screens.split(",")]
    for sc in screens:
        fr = all_rolling_frames(sc)
        print(f"# screen frames {sc['first']}-{sc['last']}: {len(fr)} all-rolling frames")
    print(f"{'generator':<48} best agreement on check frames")
    for g in lcg_candidates():
        if (a.only and a.only not in g.name) or any(x and x in g.name for x in a.skip.split(",")):
            continue
        k = a.frames or 3
        b = test_lcg(g, screens, k, a.windows)
        print(f"{g.name:<48} {b[0]:>3}/{b[1]:<3} {b[2] or ''}", flush=True)
    gaps = range(int(a.gaps.split("-")[0]), int(a.gaps.split("-")[-1]) + 1)
    if len(gaps) > 1:
        global GAP
        for g in linear_candidates():
            if (a.only and a.only not in g.name) or any(x and x in g.name for x in a.skip.split(",")):
                continue
            k = a.frames or max(2, math.ceil(g.n / 14 / 1.4) + 1)
            res = []
            for GAP in gaps:
                res.append((test_linear(g, screens, k, a.windows)[0], GAP))
            b = max(res)
            print(f"{g.name:<48} best over gaps {a.gaps}: {b[0]} agreeing digits (gap {b[1]})", flush=True)
        return
    for g in linear_candidates():
        if (a.only and a.only not in g.name) or any(x and x in g.name for x in a.skip.split(",")):
            continue
        k = a.frames or max(2, math.ceil(g.n / 14 / 1.4) + 1)
        b = test_linear(g, screens, k, a.windows)
        print(f"{g.name:<48} {b[0]:>3}/{b[1]:<3} {b[2] or ''}", flush=True)


if __name__ == "__main__":
    main()
