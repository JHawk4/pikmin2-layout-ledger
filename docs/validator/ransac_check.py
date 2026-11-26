"""Seed vs controls on one frame: fit the frame's camera from one kind of object, then score another.

Marks (pixels in one frame, e.g. a fly-over or early gameplay frame) are given per class, plus the
pod's pixel. For each seed, every assignment of two "fit" marks to two objects of the fit class
(plus the pod) gives an affine map; the one with the most fit-class inliers is refined to a
homography on its inliers. The seed's score is then the number of "test" marks (a class the
original read did not use) with an object of that class within TOL px. The same is done for
control seeds a few thousand draws around the seed (the realistic alternatives), so the output
says whether the test class picks out the seed.

    python docs/validator/ransac_check.py MARKS.json SUB SEED [--controls 300] [--span 200000] [--tol 30] [--draw OUT.jpg FRAME.png]

MARKS.json: {"pod": [x, y], "fit": {"names": ["hikarikinoko"], "px": [[x, y], ...]},
             "test": {"names": ["chappy"], "px": [[x, y], ...]}, "tol": 30}
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


def pts(lay, names):
    return np.array([(o["side"], o["ahead"]) for o in lay["objects"] if o["names"][0] in names], float).reshape(-1, 2)


def nearest(a, b):
    """For each row of a, the distance to the nearest row of b."""
    if len(b) == 0:
        return np.full(len(a), 1e9)
    return np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2).min(1)


def fit_seed(lay, m, tol):
    pod = np.array(m["pod"], float)
    F = pts(lay, m["fit"]["names"])
    D = np.array(m["fit"]["px"], float)
    best = (-1, None)
    if len(F) < 2:
        return best
    for i in range(len(F)):
        for j in range(len(F)):
            if i == j:
                continue
            src = np.array([[0, 0], F[i], F[j]], np.float32)
            for a in range(len(D)):
                for b in range(len(D)):
                    if a == b:
                        continue
                    dst = np.array([pod, D[a], D[b]], np.float32)
                    A = cv2.getAffineTransform(src, dst)
                    det = np.linalg.det(A[:, :2])
                    if not 0.2 < abs(det) < 6:
                        continue
                    P = F @ A[:, :2].T + A[:, 2]
                    n = int((nearest(D, P) < tol).sum())
                    if n > best[0]:
                        best = (n, A)
    return best


def refine(lay, m, A, tol):
    """Homography from the pod + fit-class inliers of A (if 4+), else A as a 3x3."""
    H = np.vstack([A, [0, 0, 1]])
    F = pts(lay, m["fit"]["names"])
    D = np.array(m["fit"]["px"], float)
    P = F @ A[:, :2].T + A[:, 2]
    src, dst = [[0, 0]], [m["pod"]]
    for d in D:
        k = np.argmin(np.linalg.norm(P - d, axis=1))
        if np.linalg.norm(P[k] - d) < tol:
            src.append(F[k])
            dst.append(d)
    if len(src) >= 5:
        Hh, _ = cv2.findHomography(np.array(src, np.float32), np.array(dst, np.float32), 0)
        if Hh is not None:
            H = Hh
    return H


def project(H, P):
    if len(P) == 0:
        return P
    return cv2.perspectiveTransform(P.reshape(-1, 1, 2).astype(np.float32), H).reshape(-1, 2)


def score(lay, m, tol):
    nfit, A = fit_seed(lay, m, tol)
    if A is None:
        return nfit, 0, None
    H = refine(lay, m, A, tol)
    T = project(H, pts(lay, m["test"]["names"]))
    test = int((nearest(np.array(m["test"]["px"], float), T) < m.get("test_tol", 2 * tol)).sum())
    return nfit, test, H


def main():
    m = json.load(open(sys.argv[1]))
    sub, seed = sys.argv[2], int(sys.argv[3], 16)
    tol = float(arg("--tol", m.get("tol", 30)))
    nctl, span = int(arg("--controls", 300)), int(arg("--span", 200000))
    lay = lm.dump(sub, seed)[0]
    nfit, ntest, H = score(lay, m, tol)
    print(f"{seed:08X}: fit {nfit}/{len(m['fit']['px'])}, test {ntest}/{len(m['test']['px'])}")
    random.seed(seed)
    ks = [random.randint(-span, span) for _ in range(nctl)]
    seeds = [rng.next_seed(seed, k) if k >= 0 else rng.prev_seed(seed, -k) for k in ks]
    res = []
    for i in range(0, len(seeds), 50):
        for c in lm.dump(sub, *seeds[i:i + 50]):
            res.append(score(c, m, tol)[:2])
    res = np.array(res)
    beat = int(((res[:, 0] >= nfit) & (res[:, 1] >= ntest)).sum())
    print(f"controls ({nctl} seeds within +-{span} draws): fit max {res[:, 0].max()}, "
          f"test histogram {np.bincount(res[:, 1]).tolist()}; {beat} match or beat the seed on both")
    if "--draw" in sys.argv:
        out, frame = sys.argv[sys.argv.index("--draw") + 1:sys.argv.index("--draw") + 3]
        img = cv2.imread(frame)
        for o in lay["objects"]:
            (u, v), = project(H, np.array([[o["side"], o["ahead"]]], float))
            col = (255, 255, 0) if o["names"][0] in m["fit"]["names"] else \
                (0, 0, 255) if o["names"][0] in m["test"]["names"] else (180, 180, 180)
            cv2.circle(img, (int(u), int(v)), 12, col, 2)
            cv2.putText(img, o["names"][0][:9], (int(u) + 12, int(v) - 6), 0, 0.4, col, 1)
        for x, y in m["test"]["px"]:
            cv2.drawMarker(img, (int(x), int(y)), (0, 255, 0), cv2.MARKER_TILTED_CROSS, 16, 2)
        cv2.putText(img, f"{seed:08X} fit {nfit} test {ntest}", (10, 60), 0, 0.8, (0, 255, 255), 2)
        cv2.imwrite(out, img)
        print(out)


if __name__ == "__main__":
    main()
