"""Rank pointscan.py's top seeds by further comedown evidence: marked treasures (any treasure, or
named ones) near their projected positions, and how well the unit footprints cover the bright
floor. Uses each seed's best camera from pointscan.

    python docs/layout_matcher/rank_cands.py SUB END K_LO PREFIX FRAME.png MIN_COUNT
        "u,v[,name|name];..."

Prints per seed: k, seed, dot count, camera, per-treasure pixel distance, floor IoU.
"""
import math
import sys
import os

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def main():
    sub, end, lo, prefix, frame, mn, marks = sys.argv[1:8]
    end, lo, mn = int(end, 16), int(lo), int(mn)
    z = np.load(prefix + ".npz")
    best, cam, cams = z["best"], z["cam"], z["cams"]
    ks = np.where(best >= mn)[0]
    start = lm.seed_at(end, lo)
    seeds = [lm.seed_at(start, int(k)) & 0xFFFFFFFF for k in ks]
    D = []
    for i in range(0, len(seeds), 200):
        D += lm.dump(sub, *seeds[i:i + 200])
    M = []
    for m in marks.split(";"):
        p = m.split(",")
        M.append((float(p[0]), float(p[1]), p[2].split("|") if len(p) > 2 else None))
    img = cv2.resize(cv2.imread(frame), (1280, 720))
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 3)
    _, bright = cv2.threshold(g, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    rows = []
    for k, s, d in zip(ks, seeds, D):
        zz, tt, sx, sy = cams[cam[k]]
        H = cd.homography(1280, 720, 16 / 9, float(zz), float(tt))
        items = [o for o in d["objects"] if o["kind"] in ("item", "hole", "geyser")]
        P = cv2.perspectiveTransform(np.array([[[o["side"], o["ahead"]] for o in items]], np.float32), H)[0] + [sx, sy] if items else np.zeros((0, 2))
        dist = []
        for u, v, names in M:
            ok = [i for i, o in enumerate(items) if names is None or o["names"][0] in names]
            dist.append(min([float(np.hypot(*(P[i] - (u, v)))) for i in ok], default=999))
        # floor IoU
        pod = d["pod"]
        t = math.radians(pod["angle"])
        f, r = (math.sin(t), math.cos(t)), (-math.cos(t), math.sin(t))
        polys = []
        for u in d["units"]:
            c = [(u["x"], u["z"]), (u["x"] + u["w"], u["z"]), (u["x"] + u["w"], u["z"] + u["h"]), (u["x"], u["z"] + u["h"])]
            q = []
            for X, Z in c:
                X, Z = X * 170 - pod["x"], Z * 170 - pod["z"]
                q.append((X * r[0] + Z * r[1], X * f[0] + Z * f[1]))
            polys.append(cv2.perspectiveTransform(np.array([q], np.float32), H)[0] + [sx, sy])
        m = np.zeros((720, 1280), np.uint8)
        cv2.fillPoly(m, [p.astype(np.int32) for p in polys], 1)
        iou = float((m & bright).sum() / max(1, (m | bright).sum()))
        rows.append((sum(min(x, 150) for x in dist), int(lo + k), f"{s & 0x7FFFFFFF:08X}", int(best[k]), tuple(float(v) for v in cams[cam[k]]), [round(x) for x in dist], round(iou, 3)))
    rows.sort()
    for r in rows:
        print(f"k {r[1]:8d} {r[2]} dots {r[3]} cam {r[4]} treasure px {r[5]} floor IoU {r[6]}")


if __name__ == "__main__":
    main()
