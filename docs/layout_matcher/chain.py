"""Carry a frame's pod-frame homography forward through the video by registering each frame to
the previous one (SIFT), so frames from the start of play, after the fly-over, can be rectified
too. The ground is a plane, so frame-to-frame homographies compose exactly (up to drift).

    python docs/layout_matcher/chain.py VIDEO CROP|full START H_START.json LAST STEP OUT.json [mosaic.png]

H_START.json: pod frame (side, ahead) -> START frame pixels (1280x720 game area). OUT.json is a
list of {frame, inliers, H_pod}, usable by rectify.py (pass - for H_REF). With mosaic.png, every
chained frame is also warped into one top-down pod-frame mosaic (later frames on top).
"""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from refs import feats, match, crop_arg  # noqa: E402
from register import game_frames  # noqa: E402

MSCALE = 0.3
MSIDE, MAHEAD = (-1500, 1500), (-1200, 2200)


def mosaic_T():
    M = np.array([[1 / MSCALE, 0, MSIDE[0]], [0, -1 / MSCALE, MAHEAD[1]], [0, 0, 1]])
    return M, (int((MSIDE[1] - MSIDE[0]) * MSCALE), int((MAHEAD[1] - MAHEAD[0]) * MSCALE))


def main():
    video, crop, start, h0, last, step = sys.argv[1], crop_arg(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), int(sys.argv[6])
    mosaic_path = sys.argv[8] if len(sys.argv) > 8 else None
    H = np.array(json.load(open(h0)))
    out = []
    prev = None
    M, size = mosaic_T()
    mos = np.zeros((size[1], size[0], 3), np.uint8)
    for n, img in game_frames(video, start, last, crop):
        if (n - start) % step:
            continue
        f = feats(img, hud=True)
        if prev is not None:
            Hm, inl = match(prev, f)               # img -> prev frame
            if Hm is None or inl < 25:
                print(n, "lost", inl, flush=True)
                break
            H = np.linalg.inv(Hm) @ H              # pod -> img
        else:
            inl = -1
        out.append(dict(frame=n, inliers=inl, H_pod=H.tolist()))
        if mosaic_path:
            w = cv2.warpPerspective(img, H @ M, size, flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
            m = cv2.warpPerspective(np.full(img.shape[:2], 255, np.uint8), H @ M, size, flags=cv2.WARP_INVERSE_MAP)
            # skip the HUD band at the top and bottom of game frames
            mos[m > 0] = w[m > 0]
        print(n, inl, flush=True)
        prev = f
    json.dump(out, open(sys.argv[7], "w"), indent=1)
    if mosaic_path:
        for v in range(-1400, 1401, 200):
            x = int((v - MSIDE[0]) * MSCALE)
            cv2.line(mos, (x, 0), (x, size[1]), (255, 255, 255) if v % 400 == 0 else (120, 120, 120), 1)
            cv2.putText(mos, str(v), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        for a in range(-1200, 2201, 200):
            y = int((MAHEAD[1] - a) * MSCALE)
            cv2.line(mos, (0, y), (size[0], y), (255, 255, 255) if a % 400 == 0 else (120, 120, 120), 1)
            cv2.putText(mos, str(a), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        cv2.imwrite(mosaic_path, mos)


if __name__ == "__main__":
    main()
