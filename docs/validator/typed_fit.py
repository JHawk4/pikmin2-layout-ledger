"""Typed-mark fit of a frame against seeds: the share of hand-marked objects, each with its own
type, that a seed explains under the best affine map from the pod frame to pixels.

Every pair of marks matched to a same-type pair of the seed's objects (plus the pod) gives an
affine map; the best map's inliers (a mark with an object of its own type within TOL px) are
the score. Controls are random seeds within +-SPAN draws of the seed.

    python docs/validator/typed_fit.py MARKS.json SUB SEED [SEED ...] [--controls 300] [--span 200000] [--tol 35]

MARKS.json: {"pod": [x, y], "marks": [[x, y, "name|name"], ...]}
"""
import json
import os
import random
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))
import lm  # noqa: E402
from p2seeds import rng  # noqa: E402


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def score(lay, m, tol):
    pod = np.array(m["pod"], float)
    marks = [(np.array(mk[:2], float), set(mk[2].split("|"))) for mk in m["marks"]]
    objs = [(np.array([o["side"], o["ahead"]], float), o["names"][0]) for o in lay["objects"]]
    best = (0, None)
    for i, (pi, ti) in enumerate(marks):
        ci = [p for p, n in objs if n in ti]
        for j, (pj, tj) in enumerate(marks):
            if j <= i:
                continue
            cj = [p for p, n in objs if n in tj]
            for a in ci:
                for b in cj:
                    if np.allclose(a, b):
                        continue
                    A = cv2.getAffineTransform(np.float32([[0, 0], a, b]), np.float32([pod, pi, pj]))
                    if not 0.1 < abs(np.linalg.det(A[:, :2])) < 10:
                        continue
                    n = 0
                    for pk, tk in marks:
                        cand = [p for p, nm in objs if nm in tk]
                        if cand and min(np.linalg.norm(np.array(c) @ A[:, :2].T + A[:, 2] - pk) for c in cand) < tol:
                            n += 1
                    if n > best[0]:
                        best = (n, A)
    return best


def main():
    m = json.load(open(sys.argv[1]))
    sub = sys.argv[2]
    seeds = [int(s, 16) for s in sys.argv[3:] if not s.startswith("--") and len(s) == 8 and
             sys.argv[sys.argv.index(s) - 1] not in ("--controls", "--span", "--tol")]
    tol, nctl, span = float(arg("--tol", 35)), int(arg("--controls", 300)), int(arg("--span", 200000))
    for s, lay in zip(seeds, lm.dump(sub, *seeds)):
        print(f"{s:08X}: {score(lay, m, tol)[0]}/{len(m['marks'])}")
    random.seed(seeds[0])
    ks = [random.randint(-span, span) for _ in range(nctl)]
    ctl = [rng.next_seed(seeds[0], k) if k >= 0 else rng.prev_seed(seeds[0], -k) for k in ks]
    res = []
    for i in range(0, len(ctl), 50):
        res += [score(l, m, tol)[0] for l in lm.dump(sub, *ctl[i:i + 50])]
    print(f"controls ({nctl} within +-{span} draws): histogram {np.bincount(res).tolist()}")


if __name__ == "__main__":
    main()
