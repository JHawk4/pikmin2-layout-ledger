"""Fit the comedown camera's zoom and turn on a frame whose layout is known, by maximising how well
the layout's unit footprints cover the bright (floor) pixels and avoid the dark ones.

    python docs/layout_matcher/fit_comedown.py VIDEO CROP SUB SEED FRAME [FRAME ...]

Prints per frame the best (zoom, turn, dx, dy) and the score's z against random seeds' scores at
that camera. Used to learn how the shot zooms in over time.
"""
import math
import sys

import cv2
import numpy as np

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def cells(d):
    """Pod-frame (side, ahead) centres of every unit cell."""
    P = d["pod"]
    t = math.radians(P["angle"])
    f, r = (math.sin(t), math.cos(t)), (-math.cos(t), math.sin(t))
    out = []
    for u in d["units"]:
        for cx in range(u["w"]):
            for cz in range(u["h"]):
                X, Z = (u["x"] + cx + 0.5) * 170 - P["x"], (u["z"] + cz + 0.5) * 170 - P["z"]
                out.append((X * r[0] + Z * r[1], X * f[0] + Z * f[1]))
    return np.array(out, np.float32)


def floor_map(img):
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 3)
    thr, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = np.zeros_like(b)
    m[:] = b
    m[140:450, 250:1030] = 128         # title and falling pod: unknown
    return m


def score(fm, cell_pts, zoom, turn, dx, dy):
    """IoU of the projected footprint (cells as squares) with the bright floor, outside the
    unknown centre box, at quarter resolution."""
    H = cd.homography(1280, 720, 16 / 9, zoom, turn)
    H = np.array([[0.25, 0, dx / 4], [0, 0.25, dy / 4], [0, 0, 1]]) @ H
    sq = np.array([[-85, -85], [85, -85], [85, 85], [-85, 85]], np.float32)
    polys = cv2.perspectiveTransform((cell_pts[:, None, :] + sq[None]).reshape(1, -1, 2), H)[0].reshape(-1, 4, 2)
    m = np.zeros((180, 320), np.uint8)
    cv2.fillPoly(m, [p.astype(np.int32) for p in polys], 1)
    f = fm[::4, ::4]
    known = f != 128
    br = (f > 128) & known
    fp = (m > 0) & known
    inter = (br & fp).sum()
    union = (br | fp).sum()
    return float(inter / union) if union else 0.0


def best_fit(fm, cp):
    best = (-9, None)
    for zoom in np.arange(0.8, 2.01, 0.1):
        for turn in range(-180, 180, 6):
            s = score(fm, cp, zoom, turn, 0, 0)
            if s > best[0]:
                best = (s, (zoom, turn, 0, 0))
    z0, t0, _, _ = best[1]
    for zoom in np.arange(z0 - 0.06, z0 + 0.061, 0.02):
        for turn in np.arange(t0 - 3, t0 + 3.1, 1):
            for dx in range(-40, 41, 10):
                for dy in range(-40, 41, 10):
                    s = score(fm, cp, zoom, turn, dx, dy)
                    if s > best[0]:
                        best = (s, (zoom, turn, dx, dy))
    return best


def main():
    video, crop, sub, seed = sys.argv[1:5]
    x, y, w, h = (int(v) for v in crop.split(","))
    cp = cells(lm.dump(sub, int(seed, 16))[0])
    rand = [cells(d) for d in lm.dump(sub, *[(i * 0x9E3779B1 + 7) & 0xFFFFFFFF for i in range(40)])]
    cap = cv2.VideoCapture(video)
    for n in (int(v) for v in sys.argv[5:]):
        cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        img = cv2.resize(cap.read()[1][y:y + h, x:x + w], (1280, 720))
        fm = floor_map(img)
        s, p = best_fit(fm, cp)
        rs = [score(fm, c, *p) for c in rand]
        print(f"frame {n}: zoom {p[0]:.2f} turn {p[1]:.0f} shift {p[2]},{p[3]}  score {s:.3f}  random {np.mean(rs):.3f}+-{np.std(rs):.3f}", flush=True)


if __name__ == "__main__":
    main()
