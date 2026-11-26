"""Draw a sublevel's possible spots (spots.py output) on a frame through a comedown camera,
numbered and coloured by kind, to read which spots are occupied.

    python docs/ch_hunt/spots_on_frame.py SUB FRAME.png ZOOM TURN DX,DY OUT.png [--kinds a,b] [--min-n 20]
Prints the numbered spots that fall in the frame with what can be there.
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

ap = argparse.ArgumentParser()
ap.add_argument("sub"), ap.add_argument("frame"), ap.add_argument("zoom", type=float), ap.add_argument("turn", type=float)
ap.add_argument("shift"), ap.add_argument("out"), ap.add_argument("--kinds", default=""), ap.add_argument("--min-n", type=int, default=20)
a = ap.parse_args()
dx, dy = (float(v) for v in a.shift.split(","))
spots = [s for s in json.load(open(os.path.join(lm.ROOT, "data", "lm", f"spots_{a.sub}.json"))) if s["n"] >= a.min_n]
if a.kinds:
    ks = set(a.kinds.split(","))
    spots = [s for s in spots if ks & set(s["what"])]
H = cd.homography(1280, 720, 16 / 9, a.zoom, a.turn)
q = cv2.perspectiveTransform(np.float32([[[s["side"], s["ahead"]] for s in spots]]), H)[0] + [dx, dy]
img = cv2.imread(a.frame)
cols = [(0, 255, 255), (255, 0, 255), (0, 128, 255), (255, 255, 0), (0, 255, 0)]
names = sorted({max(s["what"], key=s["what"].get) for s in spots})
for i, (s, p) in enumerate(zip(spots, q)):
    if 0 <= p[0] < 1280 and 0 <= p[1] < 720:
        k = max(s["what"], key=s["what"].get)
        c = cols[names.index(k) % len(cols)]
        cv2.circle(img, (int(p[0]), int(p[1])), 7, c, 1)
        cv2.putText(img, str(i), (int(p[0]) + 6, int(p[1]) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, c, 1)
        print(f"{i:3d} ({p[0]:.0f},{p[1]:.0f}) ahead {s['ahead']} side {s['side']} n {s['n']} {dict(list(s['what'].items())[:4])}")
cv2.imwrite(a.out, img)
