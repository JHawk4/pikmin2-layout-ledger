"""Contact sheet of video frames, labelled with frame numbers.

    python docs/hunt/sheet.py VIDEO OUT.jpg FIRST LAST STEP [COLS] [WIDTH]
    python docs/hunt/sheet.py VIDEO OUT.png FRAME          (one full-size frame, 1280x720)
"""
import sys

import cv2
import numpy as np


def read(cap, n):
    cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    return cap.read()[1]


def main():
    video, out = sys.argv[1:3]
    cap = cv2.VideoCapture(video)
    if len(sys.argv) == 4:
        f = read(cap, int(sys.argv[3]))
        cv2.imwrite(out, cv2.resize(f, (1280, 720), interpolation=cv2.INTER_AREA))
        return
    a, b, st = (int(v) for v in sys.argv[3:6])
    cols = int(sys.argv[6]) if len(sys.argv) > 6 else 6
    w = int(sys.argv[7]) if len(sys.argv) > 7 else 320
    h = w * 9 // 16
    tiles = []
    for n in range(a, b + 1, st):
        f = read(cap, n)
        if f is None:
            break
        t = cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA)
        cv2.putText(t, str(n), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(t, str(n), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
        tiles.append(t)
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(out, np.vstack(rows))


if __name__ == "__main__":
    main()
