"""Fit the comedown camera (zoom, turn, pod shift) to objects marked on a comedown frame, by
snapping each mark to a possible spot of the kinds it could be (spots.py output), then print
which spot each mark is and the observations it implies.

    python docs/ch_hunt/fit_cd.py SUB MARKS.json [--min-n 200] [--zooms 0.8,2.2,0.025]
        [--turns -180,180,1] [--shift 160] [--obs OUT.json] [--tol 60]

MARKS.json: [{"u": 750, "v": 525, "kinds": ["kareooinu_l"], "what": "big red bush"},
             {"u": 660, "v": 370, "kinds": ["pod"]}, ...] in 1280x720 pixels. "pod" is (0, 0).
A mark matches a spot when any of its kinds has been seen there (data/lm/spots_SUB.json, spots
used by at least --min-n of the sampled seeds). With --obs, writes layoutmatch scan observations:
for each mark, "an object named one of KINDS within TOL of the spot".
"""
import argparse
import json
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sub"), ap.add_argument("marks")
    ap.add_argument("--min-n", type=int, default=200), ap.add_argument("--zooms", default="0.8,2.2,0.025")
    ap.add_argument("--turns", default="-180,180,1"), ap.add_argument("--shift", type=int, default=160)
    ap.add_argument("--obs"), ap.add_argument("--tol", type=float, default=60)
    ap.add_argument("--cap", type=float, default=60, help="per-mark cost cap in px (outlier robustness)")
    a = ap.parse_args()
    marks = json.load(open(a.marks))
    spots = [s for s in json.load(open(os.path.join(lm.ROOT, "data", "lm", f"spots_{a.sub}.json"))) if s["n"] >= a.min_n]
    spots.append(dict(ahead=0, side=0, n=10 ** 6, what={"pod": 1}))
    sp = np.array([[s["side"], s["ahead"]] for s in spots], np.float32)
    allowed = np.array([[bool(set(m["kinds"]) & set(s["what"])) for s in spots] for m in marks])   # mark x spot
    px = np.array([[m["u"], m["v"]] for m in marks], np.float32)
    step = 10
    SH = np.array([(dx, dy) for dx in range(-a.shift, a.shift + 1, step) for dy in range(-a.shift, a.shift + 1, step)], np.float32)
    best = (1e18, None)
    for zoom in rng(a.zooms):
        for turn in rng(a.turns):
            H = cd.homography(1280, 720, 16 / 9, float(zoom), float(turn))
            q = cv2.perspectiveTransform(sp[None], H)[0]
            d = np.linalg.norm(px[None, :, None, :] - (q[None, None] + SH[:, None, None, :]), axis=3)   # shift, mark, spot
            d = np.where(allowed[None], d, 1e6).min(2)
            c = np.minimum(d, a.cap).sum(1)
            j = int(c.argmin())
            if c[j] < best[0]:
                best = (float(c[j]), (float(zoom), float(turn), int(SH[j, 0]), int(SH[j, 1])))
    zoom, turn, dx, dy = best[1]
    H = cd.homography(1280, 720, 16 / 9, zoom, turn)
    q = cv2.perspectiveTransform(sp[None], H)[0] + [dx, dy]
    print(f"zoom {zoom:.3f} turn {turn:.0f} shift {dx},{dy}  cost {best[0]:.0f}")
    obs = []
    for m, p, al in zip(marks, px, allowed):
        d = np.where(al, np.linalg.norm(q - p, axis=1), 1e6)
        i = int(d.argmin())
        s = spots[i]
        print(f"  {m.get('what', '')[:28]:28s} {p[0]:.0f},{p[1]:.0f} -> spot (ahead {s['ahead']}, side {s['side']}) at {d[i]:.0f}px; seen there: {dict(list(s['what'].items())[:5])}")
        if "pod" not in m["kinds"]:
            obs.append(dict(names=m["kinds"], ahead=float(s["ahead"]), side=float(s["side"]), tol=a.tol, what=m.get("what", "")))
    if a.obs:
        json.dump(dict(camera=dict(zoom=zoom, turn=turn, dx=dx, dy=dy), obs=obs), open(a.obs, "w"), indent=1)


if __name__ == "__main__":
    main()
