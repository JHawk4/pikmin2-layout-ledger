"""Side by side: a record's comedown frame and CaveGen3's comedown render of a seed.

    python docs/layout_matcher/compare.py CH FRAME SEED OUT.jpg
"""
import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inventory import WR  # noqa: E402
from wr_comedown import INV, crop_for  # noqa: E402

CG = os.environ.get("CAVEGEN3", r"C:\Users\Jordan\Desktop\Claude\cavegen3\target\release\cavegen3.exe")


def fit(im, W, H):
    s = min(W / im.shape[1], H / im.shape[0])
    im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    out = np.zeros((H, W, 3), np.uint8)
    y, x = (H - im.shape[0]) // 2, (W - im.shape[1]) // 2
    out[y:y + im.shape[0], x:x + im.shape[1]] = im
    return out


def main():
    ch, n, seed, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3].upper(), sys.argv[4]
    e = next(x for x in json.load(open(INV)) if x["ch"] == ch)
    video = os.path.join(WR, e["video"])
    x, y, w, h = crop_for(video)
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    a = fit(cap.read()[1][y:y + h, x:x + w], 960, 540)
    d = tempfile.mkdtemp()
    for view, tag in (("comedown", "c"), (None, "f")):
        args = [CG, f"CH{ch}-1", seed, "--scale", "2", "-o", os.path.join(d, tag)]
        if view:
            args += ["--view", view]
        subprocess.run(args, check=True, capture_output=True)
    b = fit(cv2.imread(os.path.join(d, "c", f"CH{ch}-1_{seed}.png")), 960, 540)
    c = fit(cv2.imread(os.path.join(d, "f", f"CH{ch}-1_{seed}.png")), 960, 540)
    for im, t in ((a, f"WR CH{ch} frame {n}"), (b, f"CaveGen3 comedown {seed}"), (c, f"full layout {seed}")):
        cv2.rectangle(im, (0, 0), (960, 36), (0, 0, 0), -1)
        cv2.putText(im, t, (8, 26), 0, 0.8, (255, 255, 255), 2)
    cv2.imwrite(out, np.hstack([a, b, c]))


if __name__ == "__main__":
    main()
