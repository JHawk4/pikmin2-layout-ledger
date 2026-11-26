"""Rank seeds by how well their objects explain points marked on a gameplay frame, with the camera free
(rotation, scale, translation): no calibration and no initial guess needed.

    python docs/layout_matcher/gameplay/simfit.py SUB PTS.json (--seeds S1,S2,.. | --end HEX --lo K --hi K)
        [--scale 0.6,1.4] [--squash 1.0,0.9] [--tol 40] [--top 20]

PTS.json: {"points": [{"px": [x, y], "names": ["key"], "label": "..."}, ...]} with pixels at 1280x720.
A point's names are CaveGen3 internal names (as in `layoutmatch dump`); "pod" is the pod itself.
Per seed: for every assignment of the two anchor points (the two with the fewest candidate objects) to
objects of their types, solve the similarity (pod frame -> pixels; screen y can be squashed by a fixed
factor for the camera's tilt), reject scales outside --scale (px per game unit), project every object and
count the other points with an object of an allowed type within --tol px. Score = inliers, then RMS.
Prints the best seeds with k (draws before END) when a window is given.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "p2seeds", "src"))
import lm  # noqa: E402


def objects(d):
    out = [("pod", 0.0, 0.0)]
    for o in d["objects"]:
        for n in o["names"][:1]:
            out.append((n, float(o["side"]), float(o["ahead"])))
    return out


def fit_seed(objs, pts, scale, squashes, tol):
    by = {}
    for n, x, y in objs:
        by.setdefault(n, []).append((x, y))
    cands = []
    for p in pts:
        c = [xy for n in p["names"] for xy in by.get(n, [])]
        cands.append(np.array(c, float).reshape(-1, 2))
    order = sorted(range(len(pts)), key=lambda i: (len(cands[i]) == 0, len(cands[i])))
    a, b = order[0], order[1]
    if len(cands[a]) == 0 or len(cands[b]) == 0:
        return (0, 1e9, None)
    best = (0, 1e9, None)
    P = np.array([p["px"] for p in pts], float)
    for sq in squashes:
        Pu = P.copy()
        Pu[:, 1] /= sq
        va = Pu[b] - Pu[a]
        # every anchor assignment at once
        A = np.repeat(cands[a], len(cands[b]), 0)
        Bc = np.tile(cands[b], (len(cands[a]), 1))
        vo = Bc - A
        lo = np.hypot(vo[:, 0], vo[:, 1])
        ok = lo >= 1
        s_all = np.where(ok, math.hypot(*va) / np.maximum(lo, 1e-9), 0)
        ok &= (s_all >= scale[0]) & (s_all <= scale[1])
        if not ok.any():
            continue
        A, vo, s_all = A[ok], vo[ok], s_all[ok]
        th = math.atan2(va[1], va[0]) - np.arctan2(-vo[:, 1], vo[:, 0])
        c, si = np.cos(th) * s_all, np.sin(th) * s_all
        tx = Pu[a, 0] - (c * A[:, 0] - si * (-A[:, 1]))
        ty = Pu[a, 1] - (si * A[:, 0] + c * (-A[:, 1]))
        res = np.zeros((len(A), len(pts)))
        for i in range(len(pts)):
            if len(cands[i]) == 0:
                res[:, i] = tol * 3
                continue
            mx, my = cands[i][:, 0][None], -cands[i][:, 1][None]
            qx = c[:, None] * mx - si[:, None] * my + tx[:, None]
            qy = si[:, None] * mx + c[:, None] * my + ty[:, None]
            res[:, i] = np.min(np.hypot(qx - Pu[i, 0], (qy - Pu[i, 1]) * sq), 1)
        inl0 = (res <= tol).sum(1)
        rms0 = np.sqrt(np.mean(np.minimum(res, tol * 3) ** 2, 1))
        top = np.lexsort((rms0, -inl0))[:3]
        for n in top:
            R = np.array([[c[n], -si[n]], [si[n], c[n]]])
            t = np.array([tx[n], ty[n]])
            s_ = s_all[n]
            for it in range(3):
                inl, rr, src, dst = 0, [], [], []
                for i in range(len(pts)):
                    if len(cands[i]) == 0:
                        rr.append(tol * 3)
                        continue
                    m = np.c_[cands[i][:, 0], -cands[i][:, 1]]
                    q = m @ R.T + t
                    dd = np.hypot(q[:, 0] - Pu[i, 0], (q[:, 1] - Pu[i, 1]) * sq)
                    j = int(np.argmin(dd))
                    rr.append(dd[j])
                    inl += dd[j] <= tol
                    if dd[j] <= 2 * tol:
                        src.append(m[j]); dst.append(Pu[i])
                if it == 2 or len(src) < 3:
                    break
                S, D = np.array(src), np.array(dst)
                ms, md = S.mean(0), D.mean(0)
                Sc, Dc = S - ms, D - md
                U, sv, Vt = np.linalg.svd(Dc.T @ Sc)
                Rr = U @ np.diag([1, np.sign(np.linalg.det(U @ Vt))]) @ Vt
                sc = sv.sum() / max((Sc ** 2).sum(), 1e-9)
                if not (scale[0] <= sc <= scale[1]):
                    break
                R, t, s_ = Rr * sc, md - (Rr * sc) @ ms, sc
            rms = float(np.sqrt(np.mean(np.minimum(rr, tol * 3) ** 2)))
            if (inl, -rms) > (best[0], -best[1]):
                best = (int(inl), rms, dict(scale=round(float(s_), 3),
                                            rot=round(math.degrees(math.atan2(R[1, 0], R[0, 0])), 1),
                                            squash=sq, res=[int(round(r)) for r in rr],
                                            R=R.tolist(), t=t.tolist()))
    return best


def _work(job):
    sub, chunk, pts, scale, squashes, tol = job
    out = []
    ds = lm.dump(sub, *[s for _, s in chunk])
    for (k, s), d in zip(chunk, ds):
        inl, rms, info = fit_seed(objects(d), pts, scale, squashes, tol)
        out.append((inl, -rms, k, s & 0x7FFFFFFF, info))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sub"), ap.add_argument("pts")
    ap.add_argument("--seeds"), ap.add_argument("--end"), ap.add_argument("--lo", type=int, default=0)
    ap.add_argument("--hi", type=int), ap.add_argument("--scale", default="0.5,1.5")
    ap.add_argument("--squash", default="1.0"), ap.add_argument("--tol", type=float, default=40)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--save", help="OUT.json: every seed with >= --min-save inliers (k, seed, inliers, rms)")
    ap.add_argument("--min-save", type=int, default=0)
    ap.add_argument("--overlay", help="FRAME_IMAGE,OUT.jpg: with --seeds, draw the best seed's objects (fitted) on the frame")
    ap.add_argument("--comedown", help="ZOOM,TURN: the points are on a comedown frame; unproject them through "
                    "CaveGen3's comedown camera first (then scale ~1 and the fit absorbs zoom/turn/shift errors)")
    a = ap.parse_args()
    pts = json.load(open(a.pts))["points"]
    raw_px = [list(p["px"]) for p in pts]
    Hcd = None
    if a.comedown:
        import cv2
        import comedown as cd
        z, t = (float(v) for v in a.comedown.split(","))
        Hcd = cd.homography(1280, 720, 16 / 9, z, t)
        Hinv = np.linalg.inv(Hcd)
        P = cv2.perspectiveTransform(np.array([[p["px"] for p in pts]], np.float32), Hinv)[0]
        for p, (side, ahead) in zip(pts, P):
            p["px"] = [float(side), float(-ahead)]
    scale = [float(v) for v in a.scale.split(",")]
    squashes = [float(v) for v in a.squash.split(",")]
    if a.seeds:
        items = [(None, int(s, 16)) for s in (open(a.seeds[1:]).read() if a.seeds.startswith("@") else a.seeds).strip().split(",")]
    else:
        end = int(a.end, 16)
        items = [(k, lm.seed_at(end, k)) for k in range(a.lo, a.hi)]
    B = 1000
    chunks = [(a.sub, items[i:i + B], pts, scale, squashes, a.tol) for i in range(0, len(items), B)]
    results = []
    from multiprocessing import Pool
    with Pool(int(os.environ.get("SIMFIT_PROCS", "4"))) as pool:
        for n, r in enumerate(pool.imap_unordered(_work, chunks)):
            results += r
            print(f"... chunk {n + 1} / {len(chunks)}", file=sys.stderr, flush=True)
    results.sort(key=lambda r: (r[0], r[1]), reverse=True)
    if a.save:
        json.dump([dict(k=k, seed=f"{s:08X}", inliers=int(i), rms=round(-r, 1)) for i, r, k, s, _ in results
                   if i >= a.min_save], open(a.save, "w"), indent=0)
    hist = np.bincount([r[0] for r in results])
    print(f"{len(pts)} points; inlier histogram (count: seeds) " + ", ".join(f"{i}:{n}" for i, n in enumerate(hist) if n))
    for inl, nrms, k, s, info in results[:a.top]:
        short = {kk: vv for kk, vv in (info or {}).items() if kk not in ("R", "t")}
        print(f"  {'' if k is None else f'k {k:8d} '}seed {s:08X} inliers {inl} rms {-nrms:.1f} {short}")
    if a.overlay and results and results[0][4]:
        import cv2
        frame, out = a.overlay.split(",")
        im = cv2.resize(cv2.imread(frame), (1280, 720))
        info = results[0][4]
        R, t, sq = np.array(info["R"]), np.array(info["t"]), info["squash"]
        d = lm.dump(a.sub, results[0][3])[0]
        names = {n for p in pts for n in p["names"]}
        for n, x, y in objects(d):
            q = R @ np.array([x, -y]) + t
            q = np.array([q[0], q[1] * sq])
            if Hcd is not None:
                q = cv2.perspectiveTransform(np.array([[[q[0], -q[1]]]], np.float32), Hcd)[0, 0]
            col = (0, 255, 255) if n in names else (255, 160, 0)
            cv2.circle(im, (int(q[0]), int(q[1])), 9, col, 2)
            cv2.putText(im, n[:9], (int(q[0]) + 10, int(q[1]) + 4), 0, 0.4, col, 1)
        for p in raw_px:
            cv2.drawMarker(im, (int(p[0]), int(p[1])), (0, 0, 255), cv2.MARKER_CROSS, 12, 2)
        cv2.putText(im, f"{results[0][3]:08X}: yellow = fitted objects of marked kinds, red + = marks", (10, 710), 0, 0.6, (0, 0, 255), 2)
        cv2.imwrite(out, im)


if __name__ == "__main__":
    main()
