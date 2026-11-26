"""For candidate seeds, fit the gameplay camera to the marks (similarity, optional vertical squash), then
list the seed's objects that land inside the frame but match no mark ("extras" the video should show).

    python docs/hunt/extras.py SUB PTS.json SEED[,SEED..] [SQUASH=1.0] [KINDS=teki,item,hole,geyser]

PTS.json in simfit's format. A seed whose extras sit on bare floor in the frame is contradicted.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "layout_matcher"))
import lm  # noqa: E402
from gp2obs import sim_fit  # noqa: E402


def main():
    sub, pts, seeds = sys.argv[1:4]
    sq = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    kinds = (sys.argv[5] if len(sys.argv) > 5 else "teki,item,hole,geyser").split(",")
    P = json.load(open(pts))["points"]
    px = np.array([p["px"] for p in P], float)
    px[:, 1] /= sq
    for seed in seeds.split(","):
        d = lm.dump(sub, int(seed, 16))[0]
        objs = [("pod", 0.0, 0.0, "pod")] + [(o["names"][0], o["side"], -o["ahead"], o["kind"]) for o in d["objects"]]
        cand = [[(x, y) for n, x, y, _ in objs if n in p["names"]] for p in P]
        best = None
        order = sorted(range(len(P)), key=lambda i: len(cand[i]) or 1e9)
        for c0 in cand[order[0]]:
            for c1 in cand[order[1]]:
                if c0 == c1:
                    continue
                a, b = sim_fit(np.array([c0, c1]), px[[order[0], order[1]]])
                for _ in range(3):
                    src, dst, res = [], [], []
                    for i in range(len(P)):
                        q = np.array(cand[i], float).reshape(-1, 2)
                        pr = a * (q[:, 0] + 1j * q[:, 1]) + b
                        r = np.abs(pr - (px[i, 0] + 1j * px[i, 1]))
                        j = int(np.argmin(r)) if len(r) else -1
                        res.append(float(r[j]) if j >= 0 else 1e9)
                        if j >= 0 and r[j] < 60:
                            src.append(q[j]); dst.append(px[i])
                    if len(src) >= 2:
                        a, b = sim_fit(np.array(src), np.array(dst))
                sc = (sum(r < 35 for r in res), -float(np.sqrt(np.mean(np.square(np.minimum(res, 200))))))
                if best is None or sc > best[0]:
                    best = (sc, a, b)
        (n, rms), a, b = best
        extra = []
        for name, x, y, k in objs:
            if k not in kinds and name != "pod":
                continue
            z = a * (x + 1j * y) + b
            u, v = z.real, z.imag * sq
            if 0 <= u < 1280 and 0 <= v < 720 and min(np.hypot(px[:, 0] - z.real, px[:, 1] - z.imag)) > 40:
                extra.append(f"{name}@({u:.0f},{v:.0f})")
        print(f"{seed}: {n}/{len(P)} marks, rms {-rms:.0f}; unmarked in frame: {', '.join(extra) or 'none'}")


if __name__ == "__main__":
    main()
