"""Test measured letter speeds against RNG / draw-order variants.

Reads fits.json files (written by the pipeline before linking) and, for every entry whose fit
is clean, runs the lattice seed search under each hypothesis about how the letters draw from
the RNG. A hypothesis "explains" an entry when the best seed fits with a per-letter score like a
real GameCube match (score / letters < 4 over >= 8 letters, as analyze._confidence's "high").

Run on GameCube fits as the positive control and on Switch fits as the test:

    python docs/switch/variants.py data/output/12_tcbtrio_y64e4x0m/fits.json ...
"""

from __future__ import annotations

import json
import sys
from collections import Counter

import numpy as np

from p2seeds import lattice, rng

LCGS = {
    "gc": (0x41C64E6D, 0x3039),       # GameCube/Wii (ANSI C rand)
    "msvc": (0x343FD, 0x269EC3),      # Microsoft C runtime rand
    "borland": (0x015A4E35, 0x1),     # Borland C/C++ rand
}


def set_lcg(a: int, c: int) -> None:
    rng.A, rng.C = a, c
    rng.A_INV = pow(a, -1, rng.M32)


def remap(v, sigma, kind: str, name: str):
    """Measured letters placed at the RNG positions the hypothesis gives them."""
    n = len(v)
    pos = list(range(n))
    if kind == "reverse":
        pos = [n - 1 - i for i in range(n)]
    elif kind.startswith("stride"):
        k = int(kind[6:])
        pos = [k * i for i in range(n)]
    elif kind == "no_space_draw":
        # spaces draw nothing: letter i sits at the count of non-space characters before it
        pos, j = [], 0
        for ch in name:
            pos.append(j)
            j += ch != " "
    elif kind == "two_per_letter_second":
        pos = [2 * i + 1 for i in range(n)]
    m = max(pos) + 1
    v2, s2 = np.full(m, np.nan), np.full(m, np.nan)
    for i in range(n):
        if np.isfinite(v[i]):
            v2[pos[i]], s2[pos[i]] = v[i], sigma[i]
    return v2, s2


KINDS = ["consecutive", "reverse", "stride2", "two_per_letter_second", "stride3", "stride4", "no_space_draw"]


def best(v, sigma):
    try:
        c = lattice.search(v, sigma, max_nodes=200_000, top=2)
    except ValueError:
        return None
    if not c:
        return None
    n = int(np.sum(np.isfinite(c[0].residuals)))
    return c[0], n, c[0].score / max(1, n)


def main(paths: list[str]) -> None:
    from p2seeds.caves import CAVES
    names = {c.cavegen: c.name for c in CAVES if c.lang == "en"}
    for path in paths:
        rows = json.load(open(path, encoding="utf-8"))
        good = [r for r in rows if r["fit"] and r["fit"]["rms_px"] < 0.35
                and sum(x is not None for x in r["fit"]["v"]) >= 8]
        hits = Counter()
        print(f"== {path}: {len(rows)} entries, {len(good)} with a clean fit (rms < 0.35 px, >= 8 letters)")
        for r in good:
            v = np.array([np.nan if x is None else x for x in r["fit"]["v"]])
            s = np.array([np.nan if x is None else x for x in r["fit"]["sigma"]])
            name = names.get(r["cave"], " " * len(v))
            line = []
            for lcg, (a, c) in LCGS.items():
                set_lcg(a, c)
                for kind in KINDS:
                    if lcg != "gc" and kind not in ("consecutive", "reverse"):
                        continue
                    b = best(*remap(v, s, kind, name))
                    ok = b is not None and b[1] >= 8 and b[2] < 4
                    if ok:
                        hits[(lcg, kind)] += 1
                        line.append(f"{lcg}/{kind}")
            set_lcg(*LCGS["gc"])
            print(f"  {r['frame']:>7} {r['cave'] or '-':<4} rms {r['fit']['rms_px']:.2f} "
                  f"letters {int(np.sum(np.isfinite(v))):>2}  explained by: {', '.join(line) or 'nothing'}")
        print("  totals:", dict(hits) or "none")


if __name__ == "__main__":
    main(sys.argv[1:])
