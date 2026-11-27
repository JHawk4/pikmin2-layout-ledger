"""Check candidate seeds against objects marked on any frame (comedown, fly-over or gameplay),
without a calibrated camera: per seed, fit a homography from the seed's objects (pod frame) to the
marked pixels by RANSAC over label-consistent assignments, and report how many marks it explains.

    python docs/ch_hunt/hfit.py SUB OBS.json SEED [SEED ...] [--tol PX] [--draw FRAME.png OUT.jpg]

OBS.json: {"points": [{"u": 363, "v": 218, "names": ["daiodogreen"]}, ...]} in 1280x720 pixels.
A name "pod" matches the pod at (0, 0). Names are CaveGen3 internal names as layoutmatch dumps
them (an object matches when any of its names is listed).

Output per seed: inliers (marks within --tol px of a same-named object after the fit), the mean
residual of the inliers, and the fitted homography. A wrong seed can fit 4 marks exactly by
chance; what counts is the inlier count beyond 4 and the residual.
"""
import argparse
import itertools
import json
import os
import random
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))
import lm  # noqa: E402


def objects(sub, seed):
    d = lm.dump(sub, seed)[0]
    objs = [dict(names=["pod"], side=0.0, ahead=0.0)]
    objs += [dict(names=o["names"], side=o["side"], ahead=o["ahead"]) for o in d["objects"]]
    return objs, d


def candidates_for(pt, objs):
    return [i for i, o in enumerate(objs) if set(pt["names"]) & set(o["names"])]


def fit_seed(pts, objs, tol=25.0, iters=4000, rng=None):
    rng = rng or random.Random(0)
    cand = [candidates_for(p, objs) for p in pts]
    usable = [i for i, c in enumerate(cand) if c]
    P = np.array([[p["u"], p["v"]] for p in pts], np.float64)
    O = np.array([[o["side"], o["ahead"]] for o in objs], np.float64)
    best = (0, 1e9, None, None)
    if len(usable) < 4:
        return best
    for _ in range(iters):
        sel = rng.sample(usable, 4)
        asg = [rng.choice(cand[i]) for i in sel]
        if len(set(asg)) < 4:
            continue
        try:
            H = cv2.getPerspectiveTransform(O[asg].astype(np.float32), P[sel].astype(np.float32))
        except cv2.error:
            continue
        if not np.isfinite(H).all() or abs(np.linalg.det(H[:2, :2])) < 1e-9:
            continue
        proj = cv2.perspectiveTransform(O[None].astype(np.float64), H)[0]
        inl, res, match = 0, 0.0, {}
        for i in usable:
            d = np.linalg.norm(proj[cand[i]] - P[i], axis=1)
            j = int(d.argmin())
            if d[j] <= tol:
                inl += 1
                res += d[j]
                match[i] = cand[i][j]
        if inl > best[0] or (inl == best[0] and res / max(inl, 1) < best[1]):
            best = (inl, res / max(inl, 1), H, match)
    # refine on all inliers
    inl, res, H, match = best
    if match and len(match) >= 5:
        src = O[[match[i] for i in match]].astype(np.float32)
        dst = P[list(match)].astype(np.float32)
        H2, _ = cv2.findHomography(src, dst, 0)
        if H2 is not None:
            proj = cv2.perspectiveTransform(O[None].astype(np.float64), H2)[0]
            d = [np.linalg.norm(proj[match[i]] - P[i]) for i in match]
            best = (inl, float(np.mean(d)), H2, match)
    return best


def draw(frame, out, objs, H, pts, match):
    img = cv2.imread(frame)
    O = np.array([[o["side"], o["ahead"]] for o in objs], np.float64)
    proj = cv2.perspectiveTransform(O[None], H)[0]
    for o, q in zip(objs, proj):
        x, y = int(q[0]), int(q[1])
        if -50 < x < img.shape[1] + 50 and -50 < y < img.shape[0] + 50:
            cv2.circle(img, (x, y), 9, (255, 0, 255), 2)
            cv2.putText(img, o["names"][-1][:10], (x + 8, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)
    for i, p in enumerate(pts):
        c = (0, 255, 0) if i in match else (0, 0, 255)
        cv2.drawMarker(img, (int(p["u"]), int(p["v"])), c, cv2.MARKER_CROSS, 16, 2)
    cv2.imwrite(out, img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sub"), ap.add_argument("obs"), ap.add_argument("seeds", nargs="+")
    ap.add_argument("--tol", type=float, default=25.0), ap.add_argument("--iters", type=int, default=4000)
    ap.add_argument("--draw", nargs=2, metavar=("FRAME", "OUT"))
    a = ap.parse_args()
    pts = json.load(open(a.obs))["points"]
    rows = []
    for s in a.seeds:
        seed = int(s, 16)
        objs, d = objects(a.sub, seed)
        inl, res, H, match = fit_seed(pts, objs, a.tol, a.iters)
        rows.append((inl, -res, s, H, match, objs))
        print(f"{s}: {inl}/{len(pts)} marks within {a.tol:.0f}px, mean residual {res:.1f}px", flush=True)
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    if a.draw and rows[0][3] is not None:
        inl, nres, s, H, match, objs = rows[0]
        draw(a.draw[0], a.draw[1], objs, H, pts, match)
        print("drew", s, "->", a.draw[1])


if __name__ == "__main__":
    main()
