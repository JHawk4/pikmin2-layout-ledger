"""Brightness timeline of a record video: black fades split it into shots, which locates each
floor's comedown (the still overhead shot right after a fade, under the floor title).

    python docs/hunt/timeline.py VIDEO [STEP]

Prints shots (first frame, last frame, mean brightness) separated by near-black frames.
"""
import sys

import cv2
import numpy as np


def main():
    video = sys.argv[1]
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    cap = cv2.VideoCapture(video)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    vals = []
    i = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            ok, f = cap.retrieve()
            small = cv2.resize(f, (160, 90))
            vals.append((i, float(small.mean())))
        i += 1
    print(f"# {video}: {n} frames, {fps:.2f} fps")
    shots, cur = [], None
    for i, v in vals:
        dark = v < float(__import__("os").environ.get("DARK", 3))
        if not dark and cur is None:
            cur = [i, i, [v]]
        elif not dark:
            cur[1] = i
            cur[2].append(v)
        elif cur is not None:
            shots.append(cur)
            cur = None
    if cur:
        shots.append(cur)
    for a, b, vs in shots:
        print(f"{a:6d}-{b:6d}  ({(b - a) / fps:6.1f}s)  mean {np.mean(vs):5.1f}")


if __name__ == "__main__":
    main()
