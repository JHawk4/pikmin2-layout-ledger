"""Frames from an HD (1080p60) copy of a record video, cropped to the game area and scaled to
1280x720, the frame size the layout-matcher tools (comedown camera, pointscan, seed_overlay) use.

    python docs/ch_hunt/hdframe.py VIDEO OUT_DIR FRAME [FRAME ...] [--sheet COLS] [--step N --to M]

FRAME numbers are in the HD video's own frames (60 fps: twice the 30 fps index of the 360p copy).
With --step/--to, FRAME is the first of a range. --sheet makes one contact sheet instead of PNGs.
"""
import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))


def game_area(img):
    """Bounding box of the non-black area (capture borders removed)."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    rows = np.where(g.mean(1) > 12)[0]
    cols = np.where(g.mean(0) > 12)[0]
    if len(rows) < 10 or len(cols) < 10:
        return 0, 0, img.shape[1], img.shape[0]
    return int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)


def crop_box(cap):
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    best = None
    for f in (n // 3, n // 2, 2 * n // 3):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, img = cap.read()
        if ok:
            a = game_area(img)
            if best is None or a[2] * a[3] > best[2] * best[3]:
                best = a
    return best


def frames(video, idx):
    cap = cv2.VideoCapture(video)
    x, y, w, h = crop_box(cap)
    want = sorted(set(idx))
    cap.set(cv2.CAP_PROP_POS_FRAMES, want[0])
    i, out = want[0], {}
    while i <= want[-1]:
        ok, img = cap.read()
        if not ok:
            break
        if i in want:
            out[i] = cv2.resize(img[y:y + h, x:x + w], (1280, 720), interpolation=cv2.INTER_AREA)
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"), ap.add_argument("out"), ap.add_argument("frames", type=int, nargs="+")
    ap.add_argument("--step", type=int), ap.add_argument("--to", type=int), ap.add_argument("--sheet", type=int)
    a = ap.parse_args()
    idx = list(range(a.frames[0], a.to + 1, a.step)) if a.step else a.frames
    fr = frames(a.video, idx)
    os.makedirs(a.out, exist_ok=True)
    if a.sheet:
        tiles = []
        for i in idx:
            t = cv2.resize(fr[i], (320, 180))
            cv2.putText(t, str(i), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            tiles.append(t)
        while len(tiles) % a.sheet:
            tiles.append(np.zeros_like(tiles[0]))
        rows = [np.hstack(tiles[r:r + a.sheet]) for r in range(0, len(tiles), a.sheet)]
        cv2.imwrite(os.path.join(a.out, f"sheet_{idx[0]}_{idx[-1]}.jpg"), np.vstack(rows))
    else:
        for i, im in fr.items():
            cv2.imwrite(os.path.join(a.out, f"f{i}.png"), im)


if __name__ == "__main__":
    main()
