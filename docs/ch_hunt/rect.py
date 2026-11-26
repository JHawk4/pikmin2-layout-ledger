"""Rectify a 1280x720 frame into the pod's frame (top-down, pod at the grid origin, facing up),
given a homography pod-frame (side, ahead) -> frame pixel.

    python docs/ch_hunt/rect.py FRAME.png H.json OUT.png [--side -900,900] [--ahead -600,1400]
        [--scale 0.5] [--seed SUB SEED]

H.json: a 3x3 list, or {"H": [[...]]}. Grid every 100 units, labelled every 200. With --seed, that
layout's objects are drawn on top (magenta circles with names) for checking a candidate.
Also: --fit PAIRS.json fits H from [{"u","v","side","ahead"}, ...] first (>= 4 pairs) and writes it
to H.json.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))


def load_h(path):
    d = json.load(open(path))
    return np.array(d["H"] if isinstance(d, dict) else d, np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frame"), ap.add_argument("h"), ap.add_argument("out")
    ap.add_argument("--side", default="-900,900"), ap.add_argument("--ahead", default="-600,1400")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--seed", nargs=2, metavar=("SUB", "SEED"))
    ap.add_argument("--fit", help="pairs json to fit H from (written to the H path)")
    a = ap.parse_args()
    if a.fit:
        pairs = json.load(open(a.fit))
        src = np.array([[p["side"], p["ahead"]] for p in pairs], np.float32)
        dst = np.array([[p["u"], p["v"]] for p in pairs], np.float32)
        H, _ = cv2.findHomography(src, dst, 0)
        proj = cv2.perspectiveTransform(src[None], H)[0]
        for p, q in zip(pairs, proj):
            print(f"  {p.get('what', '')[:30]:30s} residual {np.linalg.norm(q - [p['u'], p['v']]):.1f}px")
        json.dump(dict(H=H.tolist()), open(a.h, "w"))
    H = load_h(a.h)
    s0, s1 = (float(v) for v in a.side.split(","))
    a0, a1 = (float(v) for v in a.ahead.split(","))
    sc = a.scale
    w, h = int((s1 - s0) * sc), int((a1 - a0) * sc)
    # output pixel -> pod frame
    M = np.array([[1 / sc, 0, s0], [0, -1 / sc, a1], [0, 0, 1]])
    img = cv2.imread(a.frame)
    out = cv2.warpPerspective(img, H @ M, (w, h), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)

    def px(side, ahead):
        return int((side - s0) * sc), int((a1 - ahead) * sc)

    for v in range(int(np.ceil(s0 / 100) * 100), int(s1) + 1, 100):
        cv2.line(out, px(v, a0), px(v, a1), (255, 255, 0) if v == 0 else (90, 90, 90), 1)
        if v % 200 == 0:
            cv2.putText(out, str(v), (px(v, a1)[0] + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1)
    for v in range(int(np.ceil(a0 / 100) * 100), int(a1) + 1, 100):
        cv2.line(out, px(s0, v), px(s1, v), (255, 255, 0) if v == 0 else (90, 90, 90), 1)
        if v % 200 == 0:
            cv2.putText(out, str(v), (2, px(s0, v)[1] - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1)
    if a.seed:
        import lm
        d = lm.dump(a.seed[0], int(a.seed[1], 16))[0]
        for o in d["objects"]:
            p = px(o["side"], o["ahead"])
            cv2.circle(out, p, 10, (255, 0, 255), 2)
            cv2.putText(out, o["names"][-1][:12], (p[0] + 10, p[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 0, 255), 1)
    cv2.imwrite(a.out, out)


if __name__ == "__main__":
    main()
