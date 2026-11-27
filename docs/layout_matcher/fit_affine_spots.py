"""Fit an affine map pod-frame (side, ahead) -> pixels for a gameplay frame, by assigning
treasures marked on it to a sublevel's possible spots (spots.py). Tries every triple of spots for
the first three points, keeps maps that are not mirrored and roughly a tilted top view (axis
ratio 1-2.5), and ranks them by how many marked points land on a spot.

    python docs/layout_matcher/fit_affine_spots.py SUB "u,v;u,v;..." [TOL_PX [SMIN,SMAX]]  (SMIN,SMAX: px per unit, larger axis)
"""
import itertools
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lm  # noqa: E402


def main():
    sub = sys.argv[1]
    px = np.array([[float(v) for v in p.split(",")] for p in sys.argv[2].split(";")], np.float32)
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else 25
    SMIN, SMAX = (float(v) for v in (sys.argv[4] if len(sys.argv) > 4 else "0.3,3").split(","))
    spots = json.load(open(os.path.join(lm.ROOT, "data", "lm", f"spots_{sub}.json")))
    sp = np.array([[s["side"], s["ahead"]] for s in spots], np.float32)
    res = []
    for tri in itertools.permutations(range(len(sp)), 3):
        A = cv2.getAffineTransform(sp[list(tri)], px[:3])
        M = A[:, :2]
        if np.linalg.det(M) >= 0:      # pixel y grows down, ahead grows up: a proper view flips
            continue
        sv = np.linalg.svd(M, compute_uv=False)
        if sv[1] <= 0 or not 1.0 <= sv[0] / sv[1] <= 2.5 or not SMIN <= sv[0] <= SMAX:
            continue
        q = sp @ M.T + A[:, 2]
        d = np.linalg.norm(px[:, None] - q[None], axis=2)
        j = d.argmin(1)
        ok = d[np.arange(len(px)), j] < tol
        if len(set(j[ok])) < ok.sum():
            continue
        res.append((int(ok.sum()), -float(d[np.arange(len(px)), j][ok].sum()), tri, j.tolist(), ok.tolist(), sv.tolist()))
    res.sort(reverse=True)
    for r in res[:8]:
        print(f"inliers {r[0]}  err {-r[1]:.0f}  scale {r[5][0]:.2f}/{r[5][1]:.2f}  spots {[s if o else None for s, o in zip(r[3], r[4])]}")
        print("   ", [(spots[s]['ahead'], spots[s]['side']) for s, o in zip(r[3], r[4]) if o])


if __name__ == "__main__":
    main()
