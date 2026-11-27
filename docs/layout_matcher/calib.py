"""Calibrate a video frame to the pod's frame with a homography, from a seed whose layout is known.

The pod always lands at the same place of the same room on some sublevels (CH10-1: spawn point 0
of room_5x5a_2_kusachi), and the "FINAL FLOOR!" fly-over is a fixed camera move relative to the
pod. So one known-seed video gives a pixel <-> pod-frame map for that shot, reusable on other
videos at the same moment of the fly-over (after scaling to the game area).

Coordinates: pixels are in a 1280x720 image of the game area. Pod frame: (ahead, side) units.
"""

import json
import sys

import cv2
import numpy as np


def fit(pairs):
    """pairs: [((ahead, side), (px, py)), ...] -> H mapping (side, ahead, 1) to pixels, and residuals."""
    src = np.array([[s, a] for (a, s), _ in pairs], np.float64)
    dst = np.array([p for _, p in pairs], np.float64)
    H, _ = cv2.findHomography(src, dst, 0)
    proj = cv2.perspectiveTransform(src[None], H)[0]
    return H, np.hypot(*(proj - dst).T)


def to_pod(H, px, py):
    """Pixels -> (ahead, side)."""
    q = cv2.perspectiveTransform(np.array([[[px, py]]], np.float64), np.linalg.inv(H))[0, 0]
    return float(q[1]), float(q[0])


def to_px(H, ahead, side):
    q = cv2.perspectiveTransform(np.array([[[side, ahead]]], np.float64), H)[0, 0]
    return float(q[0]), float(q[1])


if __name__ == "__main__":
    pairs = json.load(open(sys.argv[1]))
    H, r = fit([((p["ahead"], p["side"]), (p["px"], p["py"])) for p in pairs])
    print("residuals (px):", np.round(r, 1))
    json.dump(H.tolist(), open(sys.argv[2], "w"))
