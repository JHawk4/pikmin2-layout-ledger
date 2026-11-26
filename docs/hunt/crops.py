"""Enlarged crops of a full-resolution video frame around points given in 1280x720 coordinates.

    python docs/hunt/crops.py VIDEO FRAME "u,v;u,v;..." OUT.jpg [HALF=40] [SCALE=4]
"""
import sys

import cv2
import numpy as np


def main():
    video, n, pts, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    half = int(sys.argv[5]) if len(sys.argv) > 5 else 40
    sc = int(sys.argv[6]) if len(sys.argv) > 6 else 4
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    f = cap.read()[1]
    k = f.shape[1] / 1280
    f = cv2.copyMakeBorder(f, 200, 200, 200, 200, cv2.BORDER_CONSTANT)
    tiles = []
    for i, p in enumerate(pts.split(";")):
        u, v = (float(c) for c in p.split(",")[:2])
        x, y, h = int(u * k) + 200, int(v * k) + 200, int(half * k)
        t = cv2.resize(f[y - h:y + h, x - h:x + h], (2 * half * sc, 2 * half * sc), interpolation=cv2.INTER_CUBIC)
        cv2.putText(t, f"{i}: {p}", (4, 18), 0, 0.55, (0, 255, 255), 1)
        tiles.append(t)
    cols = 4
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))


if __name__ == "__main__":
    main()
