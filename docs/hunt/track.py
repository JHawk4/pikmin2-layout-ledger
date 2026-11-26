"""Crops of the same 1280x720 region over a run of frames (watch one spot through a fight).

    python docs/hunt/track.py VIDEO X,Y FIRST LAST STEP OUT.jpg [HALF=70] [SCALE=2] [COLS=8]
"""
import sys

import cv2
import numpy as np


def main():
    video, xy, a, b, st, out = sys.argv[1:7]
    half = int(sys.argv[7]) if len(sys.argv) > 7 else 70
    sc = int(sys.argv[8]) if len(sys.argv) > 8 else 2
    cols = int(sys.argv[9]) if len(sys.argv) > 9 else 8
    x, y = (int(v) for v in xy.split(","))
    cap = cv2.VideoCapture(video)
    tiles = []
    for n in range(int(a), int(b) + 1, int(st)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        f = cv2.resize(cap.read()[1], (1280, 720), interpolation=cv2.INTER_AREA)
        f = cv2.copyMakeBorder(f, half, half, half, half, cv2.BORDER_CONSTANT)
        t = cv2.resize(f[y:y + 2 * half, x:x + 2 * half], None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
        cv2.putText(t, str(n), (4, 16), 0, 0.5, (0, 255, 255), 1)
        tiles.append(t)
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))


if __name__ == "__main__":
    main()
