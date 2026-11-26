"""Fit the comedown camera (zoom, turn, shift) to marks on objects that sit at the same place in
every seed (e.g. CH26-1's dandelions), then unproject other marks to the pod frame.

    python docs/ch_hunt/fit_fixed.py SUB SEED NAME "u,v;u,v;..." [--other "u,v,label;..."]
        [--zooms 1.3,1.9,0.01] [--turns=-15,5,0.5] [--shift 60]

SEED is any seed (the fixed objects are the same in all); NAME the fixed objects' name.
"""
import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def rng(s):
    lo, hi, st = (float(v) for v in s.split(","))
    return np.arange(lo, hi + st / 2, st)


ap = argparse.ArgumentParser()
ap.add_argument("sub"), ap.add_argument("seed"), ap.add_argument("name"), ap.add_argument("marks")
ap.add_argument("--other", default=""), ap.add_argument("--zooms", default="1.3,1.9,0.01")
ap.add_argument("--turns", default="-15,5,0.5"), ap.add_argument("--shift", type=int, default=60)
a = ap.parse_args()
d = lm.dump(a.sub, int(a.seed, 16))[0]
F = np.float32([[o["side"], o["ahead"]] for o in d["objects"] if a.name in o["names"]])
px = np.float32([[float(v) for v in p.split(",")[:2]] for p in a.marks.split(";")])
SH = np.array([(dx, dy) for dx in range(-a.shift, a.shift + 1, 4) for dy in range(-a.shift, a.shift + 1, 4)], np.float32)
best = (1e18, None)
for z in rng(a.zooms):
    for t in rng(a.turns):
        q = cv2.perspectiveTransform(F[None], cd.homography(1280, 720, 16 / 9, float(z), float(t)))[0]
        dd = np.linalg.norm(px[None, :, None] - (q[None, None] + SH[:, None, None]), axis=3).min(2)
        c = np.minimum(dd, 40).sum(1)
        j = int(c.argmin())
        if c[j] < best[0]:
            best = (float(c[j]), (float(z), float(t), float(SH[j, 0]), float(SH[j, 1])))
z, t, dx, dy = best[1]
H = cd.homography(1280, 720, 16 / 9, z, t)
q = cv2.perspectiveTransform(F[None], H)[0] + [dx, dy]
res = np.linalg.norm(px[:, None] - q[None], axis=2).min(1)
print(f"zoom {z:.3f} turn {t:.1f} shift {dx:.0f},{dy:.0f}; residuals px: {np.round(res).astype(int).tolist()}")
if a.other:
    Hi = np.linalg.inv(H)
    for p in a.other.split(";"):
        u, v, lab = p.split(",")
        s, ah = cv2.perspectiveTransform(np.float32([[[float(u) - dx, float(v) - dy]]]), Hi)[0, 0]
        print(f"  {lab:20s} pixel {u},{v} -> ahead {ah:.0f} side {s:.0f}")
