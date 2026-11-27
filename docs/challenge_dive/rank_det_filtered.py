"""Rank only the window states that pass an itemscan layout filter, by detection score.

    python docs/challenge_dive/rank_det_filtered.py VIDEO RESULT.json DET.json SCAN.bin COL DIST [--top 120]

RESULT.json: the read_dive result (region, window); DET.json: a read_det output whose best geometry
is the starting point. Every passing state is scored at that geometry, the best `--top` are refit
(each from the same starting geometry, so their scores are comparable).
"""
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "p2seeds", "src"))
from p2seeds.challenge import dive as cd, dive_detect as dd, dive_rgb as dr  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("result"); ap.add_argument("det")
ap.add_argument("scan"); ap.add_argument("col", type=int); ap.add_argument("dist", type=float)
ap.add_argument("--top", type=int, default=120)
ap.add_argument("--parts", default="flower")
a = ap.parse_args()
t0 = time.time()
r = json.load(open(a.result)); d = json.load(open(a.det))
counts, region = r["counts"], tuple(r["region"])
end, n = r["window"]
arr = np.fromfile(a.scan, np.float32).reshape(-1, 2)[:n, a.col]
ks = np.nonzero(np.abs(arr - a.dist) < 0.5)[0]
st = cd.window_states(end, n)[ks]
sp = dr.load_sprites()
g = cd.geometry_from_vector(d["geometry"])
span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
rd = dr.RGBDive(a.video, int(g.f0) - 6, int(g.f0) + span, region, drop=r.get("dropped", []), sp=sp)
ds = dd.DetScorer(rd, counts, sp, g.sx, g.sy, parts=tuple(a.parts.split(",")))
sc = ds.score(g, st)
print(f"{len(st)} passing states of {n}; scored at the best geometry: best {sc.max():.1f} median {np.median(sc):.1f} ({time.time() - t0:.0f}s)", flush=True)
top = np.argsort(-sc)[:a.top]
fits = sorted(((ds.fit(g, int(st[j]))[1], j) for j in top), reverse=True)
for v, j in fits[:15]:
    s = int(st[j])
    print(f"  {s:08X} layout {cd.layout_seed(s) & 0x7FFFFFFF:08X} k {ks[j]} first {sc[j]:.1f} fitted {v:.1f}", flush=True)
print(f"margin over median {(fits[0][0] - fits[1][0]) / max(1e-6, fits[0][0] - np.median(sc)):.3f} ({time.time() - t0:.0f}s)")
