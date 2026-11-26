"""Story-mode letter seeds under the Switch generator (a musl-style 64-bit LCG), with chaining.

Switch rand(): s = 6364136223846793005 s + 1 (mod 2^64), rand() = s >> 33 (31 bits), and the
game's randFloat() = rand() / RAND_MAX with the native RAND_MAX = 2^31 - 1. So a letter's speed is
v = 5 s / 2^64 (to 2^-31), one draw per character (spaces included), as on GC.

Per entry: the best-measured letter is the pivot; its state is bounded by its speed (plus a shared
speed offset of up to 0.3), and every other letter's state difference to the pivot (the offset
cancels) by the speed difference. lattice.box_points enumerates the 64-bit states in the box,
which are ranked by chi-square after fitting the offset.

Check: consecutive entries of a run are a modest number of draws apart (GC: < 500k). The LCG
distance between two states is computed exactly (PCG's advance-distance algorithm), so wrong
seeds show up as distances of ~10^18.

    python docs/switch/musl_letters.py FITS.json [--out seeds.json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "p2seeds" / "src"))
from p2seeds.lattice import box_points  # noqa: E402

A = 6364136223846793005
C = 1
M = 1 << 64
MASK = M - 1
A_INV = pow(A, -1, M)
K_TOL = 4.0
MAX_BIAS = 0.3


def jump(n: int) -> tuple[int, int]:
    if n < 0:
        ba, bc, n = A_INV, (-C * A_INV) & MASK, -n
    else:
        ba, bc = A, C
    a, c = 1, 0
    while n:
        if n & 1:
            a, c = (ba * a) & MASK, (ba * c + bc) & MASK
        ba, bc = (ba * ba) & MASK, (ba * bc + bc) & MASK
        n >>= 1
    return a, c


def advance(s: int, n: int) -> int:
    a, c = jump(n)
    return (a * s + c) & MASK


def distance(s_from: int, s_to: int) -> int:
    """n >= 0 with advance(s_from, n) == s_to (the LCG has full period 2^64)."""
    cur_a, cur_c, d, bit, s = A, C, 0, 1, s_from
    while s != s_to:
        if (s & bit) != (s_to & bit):
            s = (s * cur_a + cur_c) & MASK
            d |= bit
        cur_c = ((cur_a + 1) * cur_c) & MASK
        cur_a = (cur_a * cur_a) & MASK
        bit <<= 1
        if bit > M:
            raise ValueError("not on the same cycle")
    return d


def speeds(s_first: int, n: int) -> np.ndarray:
    """Speeds of draws 0..n-1, s_first being the state after draw 0."""
    out, s = [], s_first
    for _ in range(n):
        out.append(5 * (s >> 33) / ((1 << 31) - 1))
        s = (s * A + C) & MASK
    return np.array(out)


def search(v, sigma, max_nodes=2_000_000):
    meas = [i for i in range(len(v)) if v[i] is not None and sigma[i] is not None]
    if len(meas) < 6:
        return []
    p = min(meas, key=lambda i: sigma[i])
    others = [i for i in meas if i != p]
    span = K_TOL * sigma[p] + MAX_BIAS
    lo = [max(0, math.floor((v[p] - span) / 5 * M))]
    hi = [min(M - 1, math.ceil((v[p] + span) / 5 * M))]
    row = [1]
    for i in others:
        a, c = jump(i - p)
        row.append((a - 1) % M)
        d = v[i] - v[p]
        tol = K_TOL * math.hypot(sigma[i], sigma[p]) + 1e-6
        lo.append(math.floor((d - tol) / 5 * M) - c)
        hi.append(math.ceil((d + tol) / 5 * M) - c)
    n = len(row)
    gens = [row] + [[M if j == t else 0 for j in range(n)] for t in range(1, n)]
    pts = box_points(gens, lo, hi, max_nodes)
    if pts is None:
        return None
    out = []
    vv = np.array([np.nan if x is None else x for x in v])
    sg = np.array([np.nan if x is None else x for x in sigma])
    ok = np.isfinite(vv)
    for pt in pts:
        sp = pt[0] % M
        s0 = advance(sp, -p)                      # state after draw 0
        pred = speeds(s0, len(v))
        r = vv[ok] - pred[ok]
        w = 1 / sg[ok] ** 2
        bias = float(np.sum(r * w) / np.sum(w))
        if abs(bias) > MAX_BIAS:
            continue
        chi2 = float(np.sum(((r - bias) / sg[ok]) ** 2))
        out.append((chi2, s0, bias))
    out.sort()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fits")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = json.load(open(a.fits, encoding="utf-8"))
    res = []
    for r in rows:
        f = r.get("fit")
        if not f or f["rms_px"] > 0.35:
            continue
        c = search(f["v"], f["sigma"])
        if c is None:
            print(f"{r['frame']:>7} {r.get('cave', ''):<5} enumeration too large", flush=True)
            continue
        if not c:
            print(f"{r['frame']:>7} {r.get('cave', ''):<5} no state", flush=True)
            continue
        nm = sum(x is not None for x in f["v"])
        second = c[1][0] if len(c) > 1 else float("inf")
        res.append(dict(frame=r["frame"], cave=r.get("cave"), sublevel=r.get("sublevel"), letters=nm,
                        state=c[0][1], chi2=c[0][0], second=second, bias=c[0][2], n=len(c)))
        print(f"{r['frame']:>7} {r.get('cave', ''):<5} {nm:>2} letters  state {c[0][1]:#018x}  chi2 {c[0][0]:7.1f}"
              f"  next {second:9.1f}  offset {c[0][2]:+.3f}  ({len(c)} in box)", flush=True)
    print("\nchaining (draws from one entry's first letter to the next entry's):")
    prev = None
    for e in res:
        if prev is not None:
            d = distance(prev["state"], e["state"])
            e["from_prev"] = d
            tag = "CHAINS" if d < 5_000_000 else ""
            print(f"  {prev['frame']:>7} {prev['cave']:<5} -> {e['frame']:>7} {e['cave']:<5} {d:>22,} {tag}", flush=True)
        prev = e
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
