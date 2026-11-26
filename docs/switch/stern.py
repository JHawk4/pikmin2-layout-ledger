"""Recover an LCG's unknown multiplier from letter speeds (Stern / Frieze-Hastad-Kannan-Lagarias-
Shamir attack), testing "the Switch rand() is an LCG mod 2^k with other constants".

Model: s' = a s + c (mod 2^32), x = (s' >> lo) & 0x7FFF, letter speed v = 5 x / 32768, one draw
per letter. Only the state mod m = 2^(lo+15) matters. a and c are unknown.

The state differences y_i = s_{i+1} - s_i satisfy y_{i+1} = a y_i (mod m), with no c. So for any
integer vector lambda with sum_i lambda_i a^i = 0 (mod m), sum_i lambda_i y_{i+j} = 0 (mod m) for
every j. Letter speeds give each y_i to about 2^-8 of m (a speed offset shared by the entry
cancels in the difference), which is enough for LLL to find such short lambdas from the
approximate y's alone. Each lambda is a polynomial with a as a root mod m; roots are lifted bit by
bit (a is odd) and voted on across entries. The winner is then checked: with a known, every entry
must fit y_i = a^i y_0 (a one-unknown lattice), which chance values of a do not.

This needs more known bits per draw than Challenge Mode digits give (about 1.6), which is why it
uses letters.

    python docs/switch/stern.py FITS.json [--lo 16] [--k 8]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "p2seeds" / "src"))
from p2seeds.lattice import box_points, lll  # noqa: E402


def entry_runs(path, min_len):
    """Runs of consecutive measured letters: (label, x estimates, x error bounds)."""
    rows = json.load(open(path, encoding="utf-8"))
    out = []
    for r in rows:
        f = r.get("fit")
        if not f or f["rms_px"] > 0.35:
            continue
        v, sg = f["v"], f["sigma"]
        run = []
        for i in range(len(v) + 1):
            if i < len(v) and v[i] is not None and sg[i] is not None and -0.2 < v[i] < 5.2:
                run.append(i)
            else:
                if len(run) >= min_len:
                    xs = [v[j] / 5 * 32768 for j in run]
                    es = [4 * sg[j] / 5 * 32768 for j in run]
                    out.append((f"{r['frame']} {r.get('cave', '')}", xs, es))
                run = []
    return out


def relations(windows, E, m, k):
    """Short integer vectors lambda (length k) with sum_i lambda_i W_i ~ 0 (mod m) for every
    window W (k consecutive differences, from any entry: a is shared, so one lattice holds all)."""
    J = len(windows)
    Wt = max(1, int(E))
    rows = []
    for i in range(k):
        rows.append([Wt if t == i else 0 for t in range(k)] + [w[i] for w in windows])
    for j in range(J):
        rows.append([0] * k + [m if t == j else 0 for t in range(J)])
    red = lll(rows)
    out = []
    for r in red:
        lam = [x // Wt for x in r[:k]]
        if not any(lam):
            continue
        resid = max(abs(x) for x in r[k:])
        out.append((resid / (sum(abs(l) for l in lam) * E), lam))
    out.sort()
    return [lam for q, lam in out if q < 1.0]


def roots_odd(lam, bits, cap=4096):
    """Odd a mod 2^bits with sum lam_i a^i = 0 (mod 2^bits), by lifting one bit at a time."""
    cand = [1]
    for b in range(2, bits + 1):
        mod = 1 << b
        nxt = []
        for r in cand:
            for t in (r, r + (1 << (b - 1))):
                val = 0
                for l in reversed(lam):
                    val = (val * t + l) % mod
                if val == 0:
                    nxt.append(t)
        cand = nxt
        if not cand or len(cand) > cap:
            return [] if not cand else None
    return cand


def fits_entry(a, xs, es, lo, m):
    """Does some y_0 give y_i = a^i y_0 (mod m) inside every measured difference's bounds?"""
    n = len(xs) - 1
    gens = [[pow(a, i, m) for i in range(n)]] + [[m if t == i else 0 for t in range(n)] for i in range(1, n)]
    lo_b, hi_b = [], []
    for i in range(n):
        y = (xs[i + 1] - xs[i]) * (1 << lo)
        e = (es[i] + es[i + 1]) * (1 << lo) + (1 << lo)
        lo_b.append(math.floor(y - e))
        hi_b.append(math.ceil(y + e))
    pts = box_points(gens, lo_b, hi_b, 20_000)
    return pts is None or len(pts) > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fits")
    ap.add_argument("--lo", type=int, default=16)
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--entries", type=int, default=40)
    ap.add_argument("--windows", type=int, default=40)
    a = ap.parse_args()
    lo, k = a.lo, a.k
    bits = lo + 15
    m = 1 << bits
    runs = entry_runs(a.fits, k + 1)[: a.entries]
    print(f"{a.fits}: {len(runs)} letter runs of >= {k + 1}; model x = bits {lo}-{lo + 14}, m = 2^{bits}, k = {k}")
    windows = []
    E = 0.0
    for label, xs, es in runs:
        Y = [round((xs[i + 1] - xs[i]) * (1 << lo)) for i in range(len(xs) - 1)]
        for j in range(len(Y) - k + 1):
            windows.append(Y[j:j + k])
        E = max(E, (2 * float(np.median(es)) / 4 + 1) * (1 << lo))   # 1 sigma of a difference
    windows = windows[: a.windows]
    lams = relations(windows, E, m, k)
    n_rel = len(lams)
    votes = Counter()
    for lam in lams[:8]:
        rs = roots_odd(lam, bits)
        print(f"    lambda {lam}: {'too many roots' if rs is None else len(rs)} roots")
        for r in rs or []:
            votes[r] += 1
    print(f"  {n_rel} relations from {len(windows)} windows; multipliers that are roots of most of them:")
    top = votes.most_common(8)
    for r, nv in top:
        nfit = sum(fits_entry(r, xs, es, lo, m) for _, xs, es in runs)
        print(f"    a = {r:#010x}  votes {nv:>3}   entries consistent with it: {nfit}/{len(runs)}")
    if not top:
        print("    none")


if __name__ == "__main__":
    main()
