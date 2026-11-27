"""Gameplay marks -> layoutmatch observations through a similarity camera fitted on one seed.

    python docs/hunt/gp2obs.py SUB PTS.json SEED OUT.json [TOL=80] [SKIP=i,j]

PTS.json is simfit's format ({"points": [{"px", "names", "label"}]}). The pod-frame -> pixel similarity
(rotation, scale, shift) is fitted by least squares on the marks, each assigned to the nearest object of
its kind in SEED's layout (iterated). The marks are then mapped back to the pod frame and written as
"near" observations, so the camera comes from one seed but the scan over the window is blind to which
objects sit where. Prints per-mark residuals; marks in SKIP are left out of the fit (kept in the output).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "layout_matcher"))
import lm  # noqa: E402


def sim_fit(src, dst):
    """complex least squares: dst = a*src + b"""
    s = src[:, 0] + 1j * src[:, 1]
    d = dst[:, 0] + 1j * dst[:, 1]
    A = np.stack([s, np.ones_like(s)], 1)
    a, b = np.linalg.lstsq(A, d, rcond=None)[0]
    return a, b


def main():
    sub, pts, seed, out = sys.argv[1:5]
    tol = float(sys.argv[5]) if len(sys.argv) > 5 else 80.0
    skip = {int(i) for i in sys.argv[6].split(",")} if len(sys.argv) > 6 and sys.argv[6] else set()
    P = json.load(open(pts))["points"]
    d = lm.dump(sub, int(seed, 16))[0]
    objs = [("pod", 0.0, 0.0)] + [(o["names"][0], o["side"], -o["ahead"]) for o in d["objects"]]  # screen y down = -ahead
    px = np.array([p["px"] for p in P], float)
    # start: anchor on the first two marks' nearest... use all-pairs search on the two rarest kinds
    best = None
    cand = [[(x, y) for n, x, y in objs if n in p["names"]] for p in P]
    order = sorted(range(len(P)), key=lambda i: len(cand[i]) if cand[i] else 1e9)
    i0, i1 = order[0], order[1]
    for c0 in cand[i0]:
        for c1 in cand[i1]:
            if c0 == c1:
                continue
            a, b = sim_fit(np.array([c0, c1], float), px[[i0, i1]])
            for _ in range(3):
                src, dst, res = [], [], []
                for i, p in enumerate(P):
                    q = np.array(cand[i], float)
                    if len(q) == 0:
                        res.append(1e9)
                        continue
                    pr = a * (q[:, 0] + 1j * q[:, 1]) + b
                    j = int(np.argmin(np.abs(pr - (px[i, 0] + 1j * px[i, 1]))))
                    res.append(float(np.abs(pr[j] - (px[i, 0] + 1j * px[i, 1]))))
                    if i not in skip and res[-1] < 80:
                        src.append(q[j]); dst.append(px[i])
                if len(src) >= 2:
                    a, b = sim_fit(np.array(src), np.array(dst))
            score = sum(r < 40 for r in res)
            if best is None or (score, -np.median(res)) > (best[0], -np.median(best[3])):
                best = (score, a, b, res)
    score, a, b, res = best
    print(f"fit on {seed}: {score}/{len(P)} within 40 px; scale {abs(a):.3f} rot {np.degrees(np.angle(a)):.1f}")
    obs = []
    for i, p in enumerate(P):
        z = (px[i, 0] + 1j * px[i, 1] - b) / a
        print(f"  {i} {p.get('label','')}: res {res[i]:.0f} px -> ahead {-z.imag:.0f} side {z.real:.0f}")
        names = [n for n in p["names"] if n != "pod"]
        if names:
            obs.append({"label": p.get("label", str(i)), "names": names, "ahead": round(-z.imag), "side": round(z.real), "tol": tol})
    json.dump(obs, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
