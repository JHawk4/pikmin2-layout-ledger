"""Overlay a seed's objects on a frame through a homography fitted from a few hand pairs.

    python docs/ch_hunt/overlay_pairs.py FRAME.png SUB SEED PAIRS.json OUT.jpg [--ransac]

PAIRS.json: [{"u", "v", "ahead", "side", "what"}, ...] (>= 4). Objects within view are drawn
(magenta circle + name); the pairs as green crosses. Prints each pair's residual.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))
import lm  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("frame"), ap.add_argument("sub"), ap.add_argument("seed"), ap.add_argument("pairs"), ap.add_argument("out")
a = ap.parse_args()
pairs = json.load(open(a.pairs))
src = np.float32([[p["side"], p["ahead"]] for p in pairs])
dst = np.float32([[p["u"], p["v"]] for p in pairs])
H, _ = cv2.findHomography(src, dst, 0)
for p, q in zip(pairs, cv2.perspectiveTransform(src[None], H)[0]):
    print(f"  {p.get('what', '')[:30]:30s} residual {np.linalg.norm(q - [p['u'], p['v']]):.1f}px")
img = cv2.imread(a.frame)
d = lm.dump(a.sub, int(a.seed, 16))[0]
objs = [("pod", 0.0, 0.0)] + [(o["names"][0], o["side"], o["ahead"]) for o in d["objects"]]
for name, s, ah in objs:
    q = cv2.perspectiveTransform(np.float32([[[s, ah]]]), H)[0, 0]
    x, y = int(q[0]), int(q[1])
    if -20 < x < img.shape[1] + 20 and -20 < y < img.shape[0] + 20:
        cv2.circle(img, (x, y), 10, (255, 0, 255), 2)
        cv2.putText(img, name[:12], (x + 10, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1)
for p in pairs:
    cv2.drawMarker(img, (int(p["u"]), int(p["v"])), (0, 255, 0), cv2.MARKER_CROSS, 18, 2)
cv2.putText(img, f"{a.sub} {a.seed}", (10, 710), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
cv2.imwrite(a.out, img)
