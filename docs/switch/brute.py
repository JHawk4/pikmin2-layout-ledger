"""Brute-force test of measured letter speeds against other random-number generators.

variants.py uses the lattice search, which needs the GameCube generator's shape (an LCG mod 2^32
read through bits 16..30). This tests any generator whose state maps to an output in [0, 1) by
a monotonic function of the state, by enumeration: the best-measured letter (pivot) fixes its
state to one or two intervals, every state in them is stepped to each other letter's draw, and
states whose speed differences to the pivot disagree with the measured ones (beyond 4 sigma)
are dropped. A generator explains an entry when a state agrees on all but at most two letters
(on a GameCube entry the GC generator agrees on 13/13; wrong ones reach 7-8 by chance).

    python docs/switch/brute.py FITS.json [FITS.json ...]
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np

M32 = 1 << 32
CHUNK = 1 << 24
MAX_BIAS = 0.3        # a shared offset of all measured speeds (GC fits: |bias| < 0.21 in 99%)
K = 4.0


class LCG32:
    """s' = a s + c mod 2^32; output from bits [lo, hi) of the new state, as a fraction."""

    def __init__(self, name, a, c, lo, hi):
        self.name, self.a, self.c, self.lo, self.hi = name, a, c, lo, hi
        self.mod = M32

    def jump(self, n):
        a, c = 1, 0
        pa, pc = self.a, self.c
        while n:
            if n & 1:
                a, c = (pa * a) % M32, (pa * c + pc) % M32
            pa, pc = (pa * pa) % M32, (pa * pc + pc) % M32
            n >>= 1
        return a, c

    def step(self, s, n):
        a, c = self.jump(n)
        return (s * np.uint64(a) + np.uint64(c)) & np.uint64(M32 - 1)

    def out(self, s):
        bits = self.hi - self.lo
        return ((s >> np.uint64(self.lo)) & np.uint64((1 << bits) - 1)).astype(np.float64) / (1 << bits)

    def intervals(self, f0, f1):
        """States (after the draw) whose output lies in [f0, f1)."""
        bits = self.hi - self.lo
        r0, r1 = max(0, math.floor(f0 * (1 << bits))), min(1 << bits, math.ceil(f1 * (1 << bits)))
        out = []
        for top in range(1 << (32 - self.hi)):
            base = top << self.hi
            out.append((base + (r0 << self.lo), base + (r1 << self.lo)))
        return out


class Lehmer:
    """s' = a s mod m (m = 2^31 - 1); output s / m."""

    def __init__(self, name, a, m=(1 << 31) - 1):
        self.name, self.a, self.mod = name, a, m

    def out(self, s):
        return s.astype(np.float64) / self.mod

    def intervals(self, f0, f1):
        return [(max(1, math.floor(f0 * self.mod)), min(self.mod, math.ceil(f1 * self.mod)))]

    def step(self, s, n):
        """a^n * s mod m; the multiply is split in 16-bit halves so nothing overflows uint64."""
        k = pow(self.a, n, self.mod)
        hi, lo = np.uint64(k >> 16), np.uint64(k & 0xFFFF)
        m = np.uint64(self.mod)
        return ((s * hi % m) * np.uint64(1 << 16) % m + s * lo) % m


GENS = [
    LCG32("GC rand (bits 16-30)", 0x41C64E6D, 0x3039, 16, 31),
    LCG32("GC LCG, bits 16-31", 0x41C64E6D, 0x3039, 16, 32),
    LCG32("GC LCG, top 23 bits", 0x41C64E6D, 0x3039, 9, 32),
    LCG32("MSVC rand (bits 16-30)", 0x343FD, 0x269EC3, 16, 31),
    LCG32("JSystem TRandom_fast (top 23 bits)", 1664525, 1013904223, 9, 32),
    LCG32("Numerical Recipes LCG, bits 16-30", 1664525, 1013904223, 16, 31),
    Lehmer("minstd_rand0", 16807),
    Lehmer("minstd_rand", 48271),
]


def test(gen, v, sigma, positions):
    meas = [i for i in range(len(v)) if np.isfinite(v[i])]
    p = min(meas, key=lambda i: sigma[i])
    others = sorted((i for i in meas if i != p), key=lambda i: sigma[i])
    best = (0, None)
    f0, f1 = (v[p] - MAX_BIAS - K * sigma[p]) / 5, (v[p] + MAX_BIAS + K * sigma[p]) / 5
    for a, b in gen.intervals(f0, f1):
        for c0 in range(a, b, CHUNK):
            s = np.arange(c0, min(b, c0 + CHUNK), dtype=np.uint64)
            base = gen.out(s) * 5
            alive = np.ones(len(s), bool)
            agree = np.zeros(len(s), int)
            for j, i in enumerate(others):
                si = gen.step(s, positions[i] - positions[p]) if positions[i] >= positions[p] else None
                if si is None:   # draws before the pivot: step forward from the earlier letter instead
                    k = (positions[i] - positions[p]) % (gen.mod - 1 if isinstance(gen, Lehmer) else M32)
                    si = gen.step(s, k)
                d = gen.out(si) * 5 - base
                ok = np.abs(d - (v[i] - v[p])) <= K * math.hypot(sigma[i], sigma[p])
                agree += ok
                if j < 5:            # prune on the five best letters; count agreement on all
                    alive &= ok
                    s, base, alive, agree = s[alive], base[alive], np.ones(alive.sum(), bool), agree[alive]
                    if len(s) == 0:
                        break
            if len(s):
                k = int(np.argmax(agree))
                if agree[k] + 1 > best[0]:
                    best = (int(agree[k]) + 1, int(s[k]))
    return best, len(meas)


def positions_for(kind, n):
    return {"consecutive": list(range(n)), "stride2": [2 * i for i in range(n)],
            "reverse": [n - 1 - i for i in range(n)]}[kind]


KINDS = ("consecutive", "stride2")   # reverse too is slow under load; variants.py covers it for the GC LCG


def main(paths):
    for path in paths:
        rows = json.load(open(path, encoding="utf-8"))
        for r in rows:
            if not r["fit"] or r["fit"]["rms_px"] > 0.35:
                continue
            v = np.array([np.nan if x is None else x for x in r["fit"]["v"]])
            sg = np.array([np.nan if x is None else x for x in r["fit"]["sigma"]])
            if np.sum(np.isfinite(v)) < 8:
                continue
            print(f"== {path} frame {r['frame']} {r['cave']} ({int(np.sum(np.isfinite(v)))} letters)")
            for gen in GENS:
                for kind in KINDS:
                    (n_ok, st), n = test(gen, v, sg, positions_for(kind, len(v)))
                    # the pivot and the 5 pruning letters agree by construction, and with millions
                    # of survivors 1-2 more agree by chance; the true generator agrees on all
                    flag = "EXPLAINS" if n_ok >= max(8, n - 2) else ""
                    print(f"   {gen.name:<36} {kind:<12} best state agrees on {n_ok:>2}/{n} letters {flag}")


if __name__ == "__main__":
    main(sys.argv[1:])
