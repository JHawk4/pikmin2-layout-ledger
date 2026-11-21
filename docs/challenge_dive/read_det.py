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
from p2seeds import challenge_dive as cd, dive_detect as dd, dive_rgb as dr  # noqa: E402


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
    t0 = time.time()
    r = json.load(open(a.result))
    counts, region = r["counts"], tuple(r["region"])
    sp = dr.load_sprites()
    g = dr.shifted_geometry(cd.geometry_from_vector(r["candidates"][0]["geometry"]), sp)
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    rd = dr.RGBDive(a.video, int(g.f0) - 4, int(g.f0) + span, region, drop=r.get("dropped", []), sp=sp)
    ds = dd.DetScorer(rd, counts, sp, g.sx, g.sy, parts=tuple(a.parts.split(",")))
    du, dv = ds.origin_correction(g)
    g = g.copy(origins={c: (u + du, v + dv) for c, (u, v) in g.origins.items()},
               goal=(g.goal[0] + du, g.goal[1] + dv), v100=g.v100 + dv)
    print(f"maps {time.time() - t0:.0f}s, {len(rd.frames)} frames, origin correction ({du:.1f}, {dv:.1f})", flush=True)
    end, n = r["window"]
    st = cd.window_states(end, n)
    sc = ds.score(g, st)
    med = float(np.median(sc))
    top = np.argsort(-sc)[:a.top]
    print(f"window {n} scored ({time.time() - t0:.0f}s); best {sc[top[0]]:.1f}, median {med:.1f}", flush=True)
    passes = None
    if a.scan:
        col, dist = int(a.scan[1]), float(a.scan[2])
        arr = np.fromfile(a.scan[0], np.float32).reshape(-1, 2)[:n, col]
        passes = np.abs(arr - dist) < 0.5
    truth_k = None
    if a.truth:
        tv = int(a.truth, 16) & 0x7FFFFFFF
        hit = np.nonzero((st & np.uint64(0x7FFFFFFF)) == np.uint64(tv))[0]
        truth_k = int(hit[0]) if len(hit) else None
        if truth_k is not None:
            print(f"truth at window k={truth_k}: first-pass score {sc[truth_k]:.1f}, rank {(sc > sc[truth_k]).sum()}", flush=True)
            if truth_k not in top:
                top = np.concatenate([top, [truth_k]])
    fits = []
    for k in top:
        gk, v = ds.fit(g, int(st[k]))
        fits.append((v, int(k), gk))
    fits.sort(key=lambda x: -x[0])
    # second round: refit the best 10 from the best geometry too, keep the better of the two
    gb = fits[0][2]
    again = []
    for v, k, gk in fits[:10]:
        g2, v2 = ds.fit(gb, int(st[k]))
        again.append((v2, k, g2) if v2 > v else (v, k, gk))
    fits = sorted(again + fits[10:], key=lambda x: -x[0])
    best = fits[0][0]
    rows = []
    for v, k, gk in fits[:15]:
        s = int(st[k])
        tag = (" TRUTH" if k == truth_k else "") + ("" if passes is None else (" coin" if passes[k] else " -"))
        rows.append(dict(state=s, layout=cd.layout_seed(s) & 0x7FFFFFFF, k=k, score=v, coin=None if passes is None else bool(passes[k])))
        print(f"  {s:08X} layout {cd.layout_seed(s) & 0x7FFFFFFF:08X} k {k} score {v:.1f}{tag}", flush=True)
    margin = (fits[0][0] - fits[1][0]) / max(1e-6, fits[0][0] - med)
    print(f"margin {margin:.3f}  ({time.time() - t0:.0f}s)", flush=True)
    if a.out:
        json.dump(dict(rows=rows, margin=margin, median=med, geometry=cd.geometry_vector(fits[0][2])),
                  open(a.out, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
