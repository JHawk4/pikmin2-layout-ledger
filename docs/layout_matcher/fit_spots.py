"""Fit the comedown camera's zoom, turn and shift so that treasures marked on a comedown frame
(pixel positions, 1280x720) land on a sublevel's possible spots (spots.py), and print which spot
each one is.

    python docs/layout_matcher/fit_spots.py SUB "u,v;u,v;..."
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def main():
    sub = sys.argv[1]
    px = np.array([[float(v) for v in p.split(",")] for p in sys.argv[2].split(";")], np.float32)
    spots = json.load(open(os.path.join(lm.ROOT, "data", "lm", f"spots_{sub}.json")))
    sp = np.array([[s["side"], s["ahead"]] for s in spots], np.float32)
    best = (1e18, None)
    SH = np.array([(dx, dy) for dx in range(-100, 101, 10) for dy in range(-100, 101, 10)], np.float32)
    for zoom in np.arange(0.7, 2.01, 0.05):
        for turn in np.arange(-180, 180, 2):
            H = cd.homography(1280, 720, 16 / 9, float(zoom), float(turn))
            q = cv2.perspectiveTransform(sp[None], H)[0]
            # all shifts at once: (shift, pixel, spot)
            d = np.linalg.norm(px[None, :, None, :] - (q[None, None] + SH[:, None, None, :]), axis=3).min(2)
            c = np.minimum(d, 60).sum(1)
            j = int(c.argmin())
            if c[j] < best[0]:
                best = (float(c[j]), (zoom, turn, int(SH[j, 0]), int(SH[j, 1])))
    zoom, turn, dx, dy = best[1]
    H = cd.homography(1280, 720, 16 / 9, float(zoom), float(turn))
    q = cv2.perspectiveTransform(sp[None], H)[0] + [dx, dy]
    print(f"zoom {zoom:.2f} turn {turn:.0f} shift {dx},{dy}  cost {best[0]:.0f}")
    for p in px:
        d = np.linalg.norm(q - p, axis=1)
        i = int(d.argmin())
        print(f"  pixel {p[0]:.0f},{p[1]:.0f} -> spot {i} (ahead {spots[i]['ahead']}, side {spots[i]['side']}) at {d[i]:.0f} px")


if __name__ == "__main__":
    main()
