"""Calibrated reference frames for a sublevel whose pod always lands at the same place.

    python docs/layout_matcher/refs.py build VIDEO CROP BASE_FRAME H_BASE.json FIRST LAST STEP OUT_DIR
        Register frames FIRST..LAST of a known video's fly-over to its calibrated BASE_FRAME and
        save each (PNG + its pod-frame homography) in OUT_DIR/refs.json.
    python docs/layout_matcher/refs.py match OUT_DIR VIDEO CROP FIRST LAST STEP OUT.json
        Register another video's frames against every reference; keep the best pairs, each with the
        composed homography pod-frame -> that video's frame (for rectify --hpod).
"""

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from register import game_frames  # noqa: E402

SIFT = cv2.SIFT_create(3000)


def feats(img, hud=False):
    """SIFT features; with hud, only the middle of the frame (the HUD is fixed on screen)."""
    mask = None
    if hud:
        mask = np.zeros(img.shape[:2], np.uint8)
        mask[110:590, 170:1110] = 255
    return SIFT.detectAndCompute(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), mask)


def match(fa, fb):
    """Homography taking image b's pixels to image a's, and its inlier count."""
    (k1, d1), (k2, d2) = fa, fb
    if d1 is None or d2 is None or len(k2) < 10:
        return None, 0
    m = cv2.BFMatcher().knnMatch(d2, d1, k=2)
    good = [a for a, b in (x for x in m if len(x) == 2) if a.distance < 0.75 * b.distance]
    if len(good) < 10:
        return None, len(good)
    src = np.float32([k2[g.queryIdx].pt for g in good])
    dst = np.float32([k1[g.trainIdx].pt for g in good])
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
    return H, int(inl.sum()) if inl is not None else 0


def crop_arg(s):
    return None if s == "full" else tuple(int(v) for v in s.split(","))


def build(video, crop, base, h_base, first, last, step, out):
    os.makedirs(out, exist_ok=True)
    H_base = np.array(json.load(open(h_base)))
    base_img = next(game_frames(video, base, base, crop))[1]
    fb = feats(base_img)
    refs = []
    for n, img in game_frames(video, first, last, crop):
        if (n - first) % step:
            continue
        H, inl = match(fb, feats(img))          # img -> base
        if H is None or inl < 40:
            print(n, "skip", inl, flush=True)
            continue
        pod_to_img = np.linalg.inv(H) @ H_base
        p = os.path.join(out, f"ref_{n}.png")
        cv2.imwrite(p, img)
        refs.append(dict(frame=n, png=os.path.basename(p), inliers=inl, H_pod=pod_to_img.tolist()))
        print(n, inl, flush=True)
    json.dump(refs, open(os.path.join(out, "refs.json"), "w"), indent=1)


def match_video(ref_dir, video, crop, first, last, step, out):
    refs = json.load(open(os.path.join(ref_dir, "refs.json")))
    rf = [(r, feats(cv2.imread(os.path.join(ref_dir, r["png"])))) for r in refs]
    res = []
    for n, img in game_frames(video, first, last, crop):
        if (n - first) % step:
            continue
        fi = feats(img, hud=True)
        best = max(((match(f, fi), r) for r, f in rf), key=lambda x: x[0][1])
        (H, inl), r = best
        print(n, "best ref", r["frame"], inl, flush=True)
        if H is not None:
            res.append(dict(frame=n, ref=r["frame"], inliers=inl,
                            H_pod=(np.linalg.inv(H) @ np.array(r["H_pod"])).tolist()))
    res.sort(key=lambda e: -e["inliers"])
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    a = sys.argv
    if a[1] == "build":
        build(a[2], crop_arg(a[3]), int(a[4]), a[5], int(a[6]), int(a[7]), int(a[8]), a[9])
    else:
        match_video(a[2], a[3], crop_arg(a[4]), int(a[5]), int(a[6]), int(a[7]), a[8])
