"""Check candidate seeds of any challenge floor against one comedown frame: CaveGen3's map of each
seed is warped into the comedown camera (zoom, turn and pod shift fitted per seed by the IoU of
CaveGen3's floor with the frame's lit floor) and blended over the frame. Generalises
docs/layout_matcher/cmal_check.py to any floor and a given frame.

    python docs/hunt/cdcheck.py FRAME.png SUB SEED[,SEED...] OUTDIR [--fast]

FRAME.png: a 1280x720 comedown frame (docs/hunt/sheet.py VIDEO OUT.png N). Prints IoU and camera
per seed, best first; writes OUTDIR/SUB_SEED.jpg (frame | blend | map).
"""
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "layout_matcher"))
import comedown as cd  # noqa: E402
import lm  # noqa: E402
from cmal_check import CG, map_to_pod  # noqa: E402


def fit(img, mp, A, fast=False):
    floor = (mp.max(2) > 60).astype(np.uint8)
    g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(img, (320, 180)), cv2.COLOR_BGR2GRAY), (0, 0), 1.5)
    _, bright = cv2.threshold(g, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    Q = np.diag([0.25, 0.25, 1])
    best = (-1, None)
    zlo, zhi = (float(v) for v in os.environ.get("CD_ZOOMS", "1.0,1.8").split(","))
    tlo, thi = (int(v) for v in os.environ.get("CD_TURNS", "-14,8").split(","))
    zs = np.arange(zlo, zhi + 0.01, 0.1 if fast else 0.05)
    sh = range(-120, 121, 40 if fast else 20)
    for zoom in zs:
        for turn in range(tlo, thi + 1, 6 if fast else 2):
            H = cd.homography(1280, 720, 16 / 9, float(zoom), float(turn)) @ A
            for dx in sh:
                for dy in sh:
                    T = Q @ np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]]) @ H
                    m = cv2.warpPerspective(floor, T, (320, 180), flags=cv2.INTER_NEAREST)
                    iou = (m & bright).sum() / max(1, (m | bright).sum())
                    if iou > best[0]:
                        best = (float(iou), (round(float(zoom), 2), turn, dx, dy))
    return best


def render(sub, seed):
    tmp = tempfile.mkdtemp()
    subprocess.run([CG, sub, seed, "--scale", "2", "-o", tmp], check=True, capture_output=True)
    return cv2.imread(os.path.join(tmp, f"{sub}_{seed}.png"))


def main():
    frame, sub, seeds, outdir = sys.argv[1:5]
    fast = "--fast" in sys.argv
    os.makedirs(outdir, exist_ok=True)
    img = cv2.resize(cv2.imread(frame), (1280, 720))
    res = []
    for seed in seeds.upper().split(","):
        mp = render(sub, seed)
        A = map_to_pod(lm.dump(sub, int(seed, 16))[0]["pod"])
        iou, (zoom, turn, dx, dy) = fit(img, mp, A, fast)
        res.append((iou, seed, zoom, turn, dx, dy))
        H = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]]) @ cd.homography(1280, 720, 16 / 9, zoom, turn) @ A
        warped = cv2.warpPerspective(mp, H, (1280, 720))
        floor = (mp.max(2) > 60).astype(np.uint8)
        wm = cv2.warpPerspective(floor, H, (1280, 720), flags=cv2.INTER_NEAREST)[..., None].astype(bool)
        blend = np.where(wm, (0.45 * img + 0.55 * warped).astype(np.uint8), img)
        edge = cv2.morphologyEx(wm[..., 0].astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        blend[edge] = (0, 255, 255)
        s = min(1280 / mp.shape[1], 720 / mp.shape[0])
        m2 = cv2.resize(mp, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        pad = np.zeros((720, 1280, 3), np.uint8)
        oy, ox = (720 - m2.shape[0]) // 2, (1280 - m2.shape[1]) // 2
        pad[oy:oy + m2.shape[0], ox:ox + m2.shape[1]] = m2
        row = []
        for im, t in ((img, os.path.basename(frame)), (blend, f"{sub} {seed} IoU {iou:.2f}"), (pad, f"map {sub} {seed}")):
            im = im.copy()
            cv2.rectangle(im, (0, 0), (1280, 44), (0, 0, 0), -1)
            cv2.putText(im, t, (10, 32), 0, 1.0, (255, 255, 255), 2)
            row.append(im)
        cv2.imwrite(os.path.join(outdir, f"{sub}_{seed}.jpg"), cv2.resize(np.hstack(row), (2880, 540), interpolation=cv2.INTER_AREA))
    for r in sorted(res, reverse=True):
        print(f"{r[1]} IoU {r[0]:.3f} zoom {r[2]} turn {r[3]} shift {r[4]},{r[5]}")


if __name__ == "__main__":
    main()
