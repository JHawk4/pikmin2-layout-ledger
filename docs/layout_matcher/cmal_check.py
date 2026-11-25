"""Check a known (e.g. digit-read) seed by eye against a run's comedown: CaveGen3's map of the seed
is warped into the comedown camera and blended over the video frame.

    python docs/layout_matcher/cmal_check.py VIDEO X,Y,W,H CH SEED DIVE_END OUT.jpg

The frame is the brightest one 50-110 frames (env CMAL_WIN) after the stage-select dive ends (the comedown at
full brightness, before the flower/Pikmin burst that ends it). The camera (zoom, turn, pod shift) is fitted by the IoU of CaveGen3's floor
(map pixels) with the frame's lit floor. Panels: the frame, CaveGen3's map warped onto it, and
the map alone.
"""
import math
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comedown as cd  # noqa: E402
import lm  # noqa: E402

CG = os.environ.get("CAVEGEN3", r"C:\Users\Jordan\Desktop\Claude\cavegen3\target\release\cavegen3.exe")
PX, MARGIN = 80 / 170, 40          # CaveGen3 map at --scale 2: 80 px per 170-unit cell, 40 px margin


def map_to_pod(pod):
    """3x3: CaveGen3 map pixel -> pod frame (side, ahead)."""
    t = math.radians(pod["angle"])
    f, r = (math.sin(t), math.cos(t)), (-math.cos(t), math.sin(t))
    to_world = np.array([[1 / PX, 0, -MARGIN / PX - pod["x"]], [0, 1 / PX, -MARGIN / PX - pod["z"]], [0, 0, 1]])
    rot = np.array([[r[0], r[1], 0], [f[0], f[1], 0], [0, 0, 1]])
    return rot @ to_world


def best_frame(cap, x, y, w, h, end):
    """Brightest comedown frame: read sequentially after one seek (seeking these mp4s isn't
    frame-exact), skipping the flower/Pikmin burst that ends the shot (large pure-white areas)."""
    lo, hi = (int(v) for v in os.environ.get("CMAL_WIN", "50,110").split(","))
    cap.set(cv2.CAP_PROP_POS_FRAMES, end + lo)
    best = (-1, None, None)
    for n in range(end + lo, end + hi + 1):
        ok, f = cap.read()
        if not ok:
            break
        f = f[y:y + h, x:x + w]
        white = float((f.min(2) > 215).mean())
        v = float(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean())
        if white < 0.03 and v > best[0]:
            best = (v, n, f)
    return best[1], cv2.resize(best[2], (1280, 720), interpolation=cv2.INTER_CUBIC)


def main():
    video, crop, ch, seed, end, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4].upper(), int(sys.argv[5]), sys.argv[6]
    x, y, w, h = (int(v) for v in crop.split(","))
    n, img = best_frame(cv2.VideoCapture(video), x, y, w, h, end)
    tmp = tempfile.mkdtemp()
    subprocess.run([CG, f"CH{ch}-1", seed, "--scale", "2", "-o", tmp], check=True, capture_output=True)
    mp = cv2.imread(os.path.join(tmp, f"CH{ch}-1_{seed}.png"))
    floor = (mp.max(2) > 60).astype(np.uint8)                  # grey/white floor and icons vs the dark ground
    A = map_to_pod(lm.dump(f"CH{ch}-1", int(seed, 16))[0]["pod"])
    g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(img, (320, 180)), cv2.COLOR_BGR2GRAY), (0, 0), 1.5)
    _, bright = cv2.threshold(g, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    Q = np.diag([0.25, 0.25, 1])
    best = (-1, None)
    for zoom in np.arange(1.0, 1.81, 0.05):
        for turn in range(-14, 9, 2):
            H = cd.homography(1280, 720, 16 / 9, float(zoom), float(turn)) @ A
            for dx in range(-120, 121, 20):
                for dy in range(-120, 121, 20):
                    T = Q @ np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]]) @ H
                    m = cv2.warpPerspective(floor, T, (320, 180), flags=cv2.INTER_NEAREST)
                    iou = (m & bright).sum() / max(1, (m | bright).sum())
                    if iou > best[0]:
                        best = (float(iou), (round(float(zoom), 2), turn, dx, dy))
    iou, (zoom, turn, dx, dy) = best
    H = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]]) @ cd.homography(1280, 720, 16 / 9, zoom, turn) @ A
    warped = cv2.warpPerspective(mp, H, (1280, 720))
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
    for im, t in ((img, f"video frame {n}"), (blend, f"CaveGen3 CH{ch}-1 {seed} warped onto it (floor IoU {iou:.2f})"),
                  (pad, f"CaveGen3 map CH{ch}-1 {seed}")):
        im = im.copy()
        cv2.rectangle(im, (0, 0), (1280, 44), (0, 0, 0), -1)
        cv2.putText(im, t, (10, 32), 0, 1.0, (255, 255, 255), 2)
        row.append(im)
    cv2.imwrite(out, cv2.resize(np.hstack(row), (2880, 540), interpolation=cv2.INTER_AREA))
    print(f"CH{ch} {seed} frame {n}: IoU {iou:.3f} camera zoom {zoom} turn {turn} shift {dx},{dy}")


if __name__ == "__main__":
    main()
