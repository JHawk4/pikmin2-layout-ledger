"""Comedown frames of a score-WR video, for reading floor 1 in the pod's frame.

    python docs/layout_matcher/wr_comedown.py sheet CH OUT.jpg [FIRST LAST]
        Contact sheet (every 4th frame, labelled) from the dive's end to ~8 s later, to pick the
        clearest comedown frame (the still overhead shot under the floor title).
    python docs/layout_matcher/wr_comedown.py rect CH FRAME OUT.jpg [SEED]
        That frame rectified to the pod frame (grid every 100 units, labels every 400), 0.5 px per
        unit, +-1100 units; with SEED, that layout drawn on it.

Uses data/lm/inventory.json (inventory.py) for the video and dive frames; the game area is found
from the frame's non-black bounding box.
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comedown as cd  # noqa: E402
import lm  # noqa: E402
from inventory import WR  # noqa: E402

INV = os.path.join(lm.ROOT, "data", "lm", "inventory.json")


def entry(ch):
    return next(e for e in json.load(open(INV)) if e["ch"] == ch)


def read(video, n):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    return cap.read()[1]


def game_area(img):
    g = img.max(2).astype(int)
    h, w = g.shape
    cols = np.where(g[h // 6:5 * h // 6].mean(0) > 20)[0]
    rows = np.where(g[:, w // 6:5 * w // 6].mean(1) > 20)[0]
    x0, x1, y0, y1 = cols.min(), cols.max(), rows.min(), rows.max()
    # a 16:9 game area: keep the width, trust it over dark rows
    hh = int(round((x1 - x0 + 1) * 9 / 16))
    if abs(hh - (y1 - y0 + 1)) > 8:
        cy = (y0 + y1) // 2
        y0 = max(0, cy - hh // 2)
    return x0, y0, x1 - x0 + 1, hh


def crop_for(video):
    """Game area from a bright gameplay frame well after the start."""
    cap = cv2.VideoCapture(video)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    best = None
    for f in (n // 3, n // 2, 2 * n // 3):
        img = read(video, f)
        if img is None:
            continue
        a = game_area(img)
        if best is None or a[2] > best[2]:
            best = a
    return best


def main():
    mode, ch = sys.argv[1], int(sys.argv[2])
    e = entry(ch)
    video = os.path.join(WR, e["video"])
    if mode == "sheet":
        out = sys.argv[3]
        first = int(sys.argv[4]) if len(sys.argv) > 4 else (e["dive"][1] if e["dive"] else 0) + 40
        last = int(sys.argv[5]) if len(sys.argv) > 5 else first + 240
        cap = cv2.VideoCapture(video)
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)
        ims = []
        for n in range(first, last):
            ok, f = cap.read()
            if not ok:
                break
            if (n - first) % 4 == 0:
                im = cv2.resize(f, (256, 144))
                cv2.putText(im, str(n), (3, 13), 0, 0.42, (0, 255, 255), 1)
                ims.append(im)
        ims += [np.zeros_like(ims[0])] * ((-len(ims)) % 6)
        cv2.imwrite(out, np.vstack([np.hstack(ims[i:i + 6]) for i in range(0, len(ims), 6)]))
    else:
        frame, out = int(sys.argv[3]), sys.argv[4]
        x, y, w, h = crop_for(video)
        img = read(video, frame)[y:y + h, x:x + w]
        img = cv2.resize(img, (1280, 720), interpolation=cv2.INTER_CUBIC)
        r, to = cd.rectify(img, 16 / 9, scale=0.5, side=(-1100, 1100), ahead=(-1100, 1100))
        if len(sys.argv) > 5:
            r = cd.draw(r, to, f"CH{ch}-1", int(sys.argv[5], 16))
        cv2.imwrite(out, r)
        print("crop", (x, y, w, h))


if __name__ == "__main__":
    main()
