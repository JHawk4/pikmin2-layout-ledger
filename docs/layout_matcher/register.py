"""Find the frame of a video's fly-over that matches a calibrated reference frame, and the
homography between them (SIFT on the fixed room: stones, logs, ground texture).

    python docs/layout_matcher/register.py REF.png VIDEO FIRST LAST CROP(x,y,w,h|full) OUT.json
"""
import json
import sys

import cv2
import numpy as np

W, H = 1280, 720


def game_frames(video, first, last, crop):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    for n in range(first, last + 1):
        ok, f = cap.read()
        if not ok:
            break
        if crop:
            x, y, w, h = crop
            f = f[y:y + h, x:x + w]
        yield n, cv2.resize(f, (W, H), interpolation=cv2.INTER_CUBIC)


def match(ref, img, sift=cv2.SIFT_create(4000)):
    k1, d1 = sift.detectAndCompute(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), None)
    k2, d2 = sift.detectAndCompute(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None)
    if d2 is None or len(k2) < 10:
        return None, 0
    m = cv2.BFMatcher().knnMatch(d2, d1, k=2)
    good = [a for a, b in (x for x in m if len(x) == 2) if a.distance < 0.75 * b.distance]
    if len(good) < 10:
        return None, len(good)
    src = np.float32([k2[g.queryIdx].pt for g in good])
    dst = np.float32([k1[g.trainIdx].pt for g in good])
    Hm, inl = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
    return Hm, int(inl.sum()) if inl is not None else 0


if __name__ == "__main__":
    ref = cv2.resize(cv2.imread(sys.argv[1]), (W, H))
    video, first, last = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    crop = None if sys.argv[5] == "full" else tuple(int(v) for v in sys.argv[5].split(","))
    best = []
    step = int(sys.argv[7]) if len(sys.argv) > 7 else 1
    for n, img in game_frames(video, first, last, crop):
        if (n - first) % step:
            continue
        Hm, inl = match(ref, img)
        print(n, inl, flush=True)
        if Hm is not None:
            best.append((inl, n, Hm.tolist()))
    best.sort(reverse=True)
    json.dump([dict(inliers=i, frame=n, H=h) for i, n, h in best[:10]], open(sys.argv[6], "w"), indent=1)
    print("best", [(b[1], b[0]) for b in best[:5]])
