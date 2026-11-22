"""Score seeds by how many marked comedown points (e.g. Glowcaps, which glow in the comedown even
though enemies aren't drawn) have an object of the given names nearby, over a grid of comedown
cameras. Keeps each seed's best count over the cameras.

    python docs/layout_matcher/pointscan.py SUB END K_LO K_HI NAMES "u,v;u,v;..." OUT_PREFIX
        [--zooms lo,hi,step] [--turns lo,hi,step] [--tol T] [--shift "dx,dy;dx,dy"]

Points are pixels of a 1280x720 frame; NAMES a comma list (CaveGen3 internal names).
Writes OUT_PREFIX.npz (best count and camera index per seed) and prints the top seeds.
"""
import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def rng(s):
    lo, hi, st = (float(v) for v in s.split(","))
    return np.round(np.arange(lo, hi + st / 2, st), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sub"), ap.add_argument("end"), ap.add_argument("lo", type=int), ap.add_argument("hi", type=int)
    ap.add_argument("names"), ap.add_argument("points"), ap.add_argument("out")
    ap.add_argument("--zooms", default="0.8,1.2,0.05"), ap.add_argument("--turns", default="-12,8,4")
    ap.add_argument("--tol", type=float, default=100), ap.add_argument("--shift", default="0,0", help="shifts dx,dy;dx,dy;... of the pod from the centre")
    a = ap.parse_args()
    names = a.names.split(",")
    px = np.array([[float(v) for v in p.split(",")] for p in a.points.split(";")], np.float32)
    SHIFTS = [tuple(float(v) for v in sh.split(",")) for sh in a.shift.split(";")]
    end = int(a.end, 16)
    start = lm.seed_at(end, a.lo)
    n = a.hi - a.lo
    best = np.zeros(n, np.uint8)
    cam = np.zeros(n, np.uint16)
    cams = [(float(z), float(t), sx, sy) for z in rng(a.zooms) for t in rng(a.turns) for sx, sy in SHIFTS]
    per = max(1, 32 // len(px))                  # cameras per scan (32 observation bits)
    for c0 in range(0, len(cams), per):
        group = cams[c0:c0 + per]
        obs = []
        for z, t, sx, sy in group:
            Hinv = np.linalg.inv(cd.homography(1280, 720, 16 / 9, z, t))
            pod = cv2.perspectiveTransform((px - [sx, sy])[None].astype(np.float32), Hinv)[0]   # (side, ahead)
            obs += [dict(names=names, ahead=float(p[1]), side=float(p[0]), tol=a.tol) for p in pod]
        bits = lm.scan(a.sub, start, n, obs, a.out + "_tmp.bin")
        for gi in range(len(group)):
            c = np.zeros(n, np.uint8)
            for i in range(len(px)):
                c += ((bits >> (gi * len(px) + i)) & 1).astype(np.uint8)
            better = c > best
            best[better] = c[better]
            cam[better] = c0 + gi
            print(f"camera {group[gi]}: max {c.max()} ({(c == c.max()).sum()} seeds)", flush=True)
    np.savez(a.out + ".npz", best=best, cam=cam, cams=np.array(cams))
    order = np.argsort(-best.astype(int), kind="stable")[:25]
    print(f"of {len(px)} points: count histogram top", np.bincount(best)[-6:])
    for i in order:
        s = lm.seed_at(start, int(i)) & 0x7FFFFFFF
        print(f"  k {a.lo + int(i):8d} seed {s:08X} count {best[i]} camera {cams[cam[i]]}")


if __name__ == "__main__":
    main()
