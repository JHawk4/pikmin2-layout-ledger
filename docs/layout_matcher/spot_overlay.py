"""Draw a sublevel's possible object spots (spots.py output) through the comedown camera on a
comedown frame, numbered, for reading which treasure sits at which spot.

    python docs/layout_matcher/spot_overlay.py CH FRAME ZOOM TURN OUT.jpg [SCALE [DX,DY]]
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
from wr_comedown import INV, crop_for  # noqa: E402


def main():
    ch, n, zoom, turn, out = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    sc = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0
    dx, dy = (float(v) for v in (sys.argv[7] if len(sys.argv) > 7 else "0,0").split(","))
    e = next(x for x in json.load(open(INV)) if x["ch"] == ch)
    video = os.path.join(WR, e["video"])
    x, y, w, h = crop_for(video)
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    img = cv2.resize(cap.read()[1][y:y + h, x:x + w], (1280, 720))
    spots = json.load(open(os.path.join(lm.ROOT, "data", "lm", f"spots_CH{ch}-1.json")))
    H = cd.homography(1280, 720, 16 / 9, zoom, turn)
    pts = np.array([[[s["side"], s["ahead"]] for s in spots]], np.float32)
    px = cv2.perspectiveTransform(pts, H)[0] + [dx, dy]
    for i, (u, v) in enumerate(px):
        cv2.circle(img, (int(u), int(v)), 10, (0, 255, 255), 1)
        cv2.putText(img, str(i), (int(u) + 10, int(v) - 6), 0, 0.5, (0, 255, 255), 1)
    o = cv2.perspectiveTransform(np.array([[[0, 0], [0, 300]]], np.float32), H)[0] + [dx, dy]
    cv2.arrowedLine(img, tuple(int(v) for v in o[0]), tuple(int(v) for v in o[1]), (0, 0, 255), 2)
    cv2.imwrite(out, cv2.resize(img, None, fx=sc, fy=sc))


if __name__ == "__main__":
    main()
