"""Read a dive's RNG state by Pikmin detection (dive_detect), blind (no truth used).

    python docs/challenge_dive/read_det.py VIDEO RESULT.json [--truth HEX] [--scan SCAN.bin COL DIST]

RESULT.json is an earlier read_dive result for the same visit (region, geometry, window). Steps:
1. colour frames and per-colour detection maps; geometry = the earlier fit, converted to sprite
   anchors and corrected by where the waiting stacks are detected;
2. every state of the window scored against the maps (compiled);
3. the best `--top` refit (geometry per state, maximising its score), then the best few refit again;
4. ranking by the refit score. The margin is (best - second) / (best - median of the window).
--scan marks which candidates pass an itemscan layout filter (seed k of the scan = window state k).
"""

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "p2seeds", "src"))
from p2seeds.challenge import dive as cd, dive_detect as dd, dive_rgb as dr  # noqa: E402


def read(video, r, parts=("flower",), top_n=150, truth=None, passes=None, log=print, shortlist=None, inject_truth=True):
    """Detection read of one dive. r: a read_dive result (or setup_only result) for the visit."""
    t0 = time.time()
    counts, region = r["counts"], tuple(r["region"])
    sp = dr.load_sprites()
    g = dr.shifted_geometry(cd.geometry_from_vector(r["candidates"][0]["geometry"]), sp)
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    rd = dr.RGBDive(video, int(g.f0) - 4, int(g.f0) + span, region, drop=r.get("dropped", []), sp=sp)
    ds = dd.DetScorer(rd, counts, sp, g.sx, g.sy, parts=tuple(parts))
    du, dv = ds.origin_correction(g)
    g = g.copy(origins={c: (u + du, v + dv) for c, (u, v) in g.origins.items()},
               goal=(g.goal[0] + du, g.goal[1] + dv), v100=g.v100 + dv)
    log(f"maps {time.time() - t0:.0f}s, {len(rd.frames)} frames, origin correction ({du:.1f}, {dv:.1f})")
    end, n = r["window"]
    if shortlist is None:
        st = cd.window_states(end, n)
        sc = ds.score(g, st)
        med = float(np.median(sc))
        top = np.argsort(-sc)[:top_n]
    else:       # only refit and rank the given states (e.g. the grey reader's shortlist); scale from a sample
        smp = cd.window_states(end, n)[:: max(1, n // 200_000)]
        med = float(np.median(ds.score(g, smp)))
        st = np.unique(np.asarray(shortlist, np.uint64))
        sc = ds.score(g, st)
        top = np.argsort(-sc)
    log(f"window {n} scored ({time.time() - t0:.0f}s); best {sc[top[0]]:.1f}, median {med:.1f}")
    truth_k = None
    if truth is not None:
        tv = truth & 0x7FFFFFFF
        hit = np.nonzero((st & np.uint64(0x7FFFFFFF)) == np.uint64(tv))[0]
        truth_k = int(hit[0]) if len(hit) else None
        if truth_k is not None:
            log(f"truth at window k={truth_k}: first-pass score {sc[truth_k]:.1f}, rank {(sc > sc[truth_k]).sum()}")
            if inject_truth and truth_k not in top:
                top = np.concatenate([top, [truth_k]])
    fits = []
    for k in top:
        gk, v = ds.fit(g, int(st[k]))
        fits.append((v, int(k), gk))
    fits.sort(key=lambda x: -x[0])
    # second round: refit the best 20 from the best geometry too, keep the better of the two. Only
    # these are ranked against each other (a second start adds ~5% to a score, so states without it
    # are not comparable); the rest follow below.
    gb = fits[0][2]
    again = []
    for v, k, gk in fits[:20]:
        g2, v2 = ds.fit(gb, int(st[k]))
        again.append((v2, k, g2) if v2 > v else (v, k, gk))
    fits = sorted(again, key=lambda x: -x[0]) + fits[20:]
    rows = []
    for v, k, gk in fits[:15]:
        s = int(st[k])
        tag = (" TRUTH" if k == truth_k else "") + ("" if passes is None else (" coin" if passes[k] else " -"))
        rows.append(dict(state=s, layout=cd.layout_seed(s) & 0x7FFFFFFF, k=k, score=v,
                         coin=None if passes is None else bool(passes[k])))
        log(f"  {s:08X} layout {cd.layout_seed(s) & 0x7FFFFFFF:08X} k {k} score {v:.1f}{tag}")
    margin = (fits[0][0] - fits[1][0]) / max(1e-6, fits[0][0] - med)
    truth_rank = next((j for j, f in enumerate(fits) if f[1] == truth_k), None)
    log(f"margin {margin:.3f}  ({time.time() - t0:.0f}s)")
    return dict(rows=rows, margin=margin, median=med, geometry=cd.geometry_vector(fits[0][2]),
                truth_k=truth_k, truth_rank=truth_rank, first_pass_rank=None if truth_k is None else int((sc > sc[truth_k]).sum()),
                seconds=time.time() - t0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("result")
    ap.add_argument("--truth")
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--scan", nargs=3)
    ap.add_argument("--out")
    ap.add_argument("--parts", default="flower", help="sprite parts to detect: body,flower | body | flower")
    a = ap.parse_args()
    r = json.load(open(a.result))
    passes = None
    if a.scan:
        col, dist = int(a.scan[1]), float(a.scan[2])
        arr = np.fromfile(a.scan[0], np.float32).reshape(-1, 2)[:r["window"][1], col]
        passes = np.abs(arr - dist) < 0.5
    out = read(a.video, r, a.parts.split(","), a.top, int(a.truth, 16) if a.truth else None, passes,
               log=lambda s: print(s, flush=True))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
