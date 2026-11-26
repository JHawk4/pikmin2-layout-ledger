"""Draw a seed's objects on a near top-down gameplay or fly-over frame, through an affine map fitted
from a few hand-marked landmarks (pod-frame point -> pixel).

Useful to check objects the original read did not use (enemies, treasures) in other frames.
With 3 marks the fit is exact; with more, the residuals are printed (a check of the marks).

    python docs/validator/affine_overlay.py FRAME.png SUB SEED "px,py=ahead,side;..." OUT.jpg [--only kind,kind]

A mark's pod-frame point may also be "pod" (0,0).
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))
import lm  # noqa: E402

COL = {"plant": (255, 255, 0), "teki": (0, 0, 255), "item": (0, 255, 255), "geyser": (0, 255, 0),
       "hole": (0, 255, 0), "gate": (200, 200, 200), "capteki": (0, 128, 255)}


def main():
    frame, sub, seed, marks, out = sys.argv[1:6]
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    src, dst = [], []
    for m in marks.split(";"):
        p, q = m.split("=")
        px, py = map(float, p.split(","))
        a, s = (0.0, 0.0) if q.strip() == "pod" else map(float, q.split(","))
        src.append((s, a))
        dst.append((px, py))
    src, dst = np.array(src, np.float32), np.array(dst, np.float32)
    A = np.c_[src, np.ones(len(src))]
    M, *_ = np.linalg.lstsq(A, dst, rcond=None)
    res = np.linalg.norm(A @ M - dst, axis=1)
    print("mark residuals px:", np.round(res, 1))
    img = cv2.imread(frame)
    d = lm.dump(sub, int(seed, 16))[0]
    for o in d["objects"]:
        if only and o["kind"] not in only:
            continue
        u, v = np.array([o["side"], o["ahead"], 1.0]) @ M
        c = COL.get(o["kind"], (255, 255, 255))
        cv2.circle(img, (int(u), int(v)), 14, c, 2)
        cv2.putText(img, o["names"][0][:10], (int(u) + 14, int(v) - 6), 0, 0.45, c, 1)
    u, v = np.array([0, 0, 1.0]) @ M
    cv2.drawMarker(img, (int(u), int(v)), (255, 0, 255), cv2.MARKER_CROSS, 24, 2)
    cv2.putText(img, seed, (10, 30), 0, 0.9, (0, 255, 255), 2)
    cv2.imwrite(out, img)
    print(out)


if __name__ == "__main__":
    main()
