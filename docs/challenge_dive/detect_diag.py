"""Diagnostic images of Pikmin detection in a dive.

    python docs/challenge_dive/detect_diag.py VIDEO RESULT.json OUT.png [--cand 0] [--frames 8]

Columns per sampled frame: the video crop; detections (rings at each detected Pikmin's sprite
centre, in the Pikmin's colour, brighter = stronger); the response map of the first colour; and the
candidate state's predicted positions (dots) over the detections, to compare by eye.
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "p2seeds", "src"))
from p2seeds import challenge_dive as cd, dive_detect as dd, dive_rgb as dr  # noqa: E402

BGR = {"red": (40, 40, 255), "yellow": (0, 230, 255), "blue": (255, 140, 0), "white": (255, 255, 255),
       "purple": (230, 80, 200)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("result")
    ap.add_argument("out")
    ap.add_argument("--cand", type=int, default=0)
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--thr", type=float, default=0.35)
    ap.add_argument("--zoom", type=int, default=3)
    a = ap.parse_args()
    r = json.load(open(a.result))
    counts, region = r["counts"], tuple(r["region"])
    c = r["candidates"][a.cand]
    sp = dr.load_sprites()
    g = dr.shifted_geometry(cd.geometry_from_vector(c["geometry"]), sp)
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    rd = dr.RGBDive(a.video, int(g.f0) + 2, int(g.f0) + span, region, drop=r.get("dropped", []), sp=sp)
    colours = [cd.COLOURS[k] for k, n in enumerate(counts) if n]
    det = dd.Detector(sp, colours, g.sx, g.sy)
    flat = cd.flatten(cd.dive_params(c["state"], counts))
    pf = cd.predicted_frames(flat, g, rd.frames)
    mass = [np.abs(rd.raw[f] - rd.bg).sum() for f in rd.frames]
    busy = [f for f, m in zip(rd.frames, mass) if m > 0.1 * max(mass)]
    pick = [busy[int(i)] for i in np.linspace(0, len(busy) - 1, min(a.frames, len(busy)))]
    z = a.zoom
    # sprite centre offset from the anchor, per colour (to draw rings where the Pikmin appears)
    cen = {col: dr.anchor_shift(sp, col, g.sx, g.sy) for col in colours}
    rows = []
    for f in pick:
        fr = rd.raw[f]
        up = lambda im: cv2.resize(np.clip(im, 0, 255).astype(np.uint8), None, fx=z, fy=z,  # noqa: E731
                                   interpolation=cv2.INTER_NEAREST)
        maps = det.maps(fr, rd.bg)
        d1 = up(fr)
        n_det = 0
        for col in colours:
            for x, y, v in dd.peaks(maps[col], a.thr):
                n_det += 1
                p = (int((x + cen[col][0]) * z), int((y + cen[col][1]) * z))
                cv2.circle(d1, p, 4 * z, (0, 0, 0), 3)
                cv2.circle(d1, p, 4 * z, tuple(int(cc * min(1, 0.4 + v)) for cc in BGR[col]), 2)
        m0 = maps[colours[0]]
        mp = up(cv2.cvtColor((np.clip(m0, 0, 1) * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR))
        d2 = d1.copy()
        us, vs = pf[f]
        for u, v, k in zip(us, vs, flat[:, 3].astype(int)):
            if u != u:
                continue
            col = cd.COLOURS[k]
            p = (int((u - region[0] + cen[col][0]) * z), int((v - region[1] + cen[col][1]) * z))
            cv2.circle(d2, p, z + 1, (0, 0, 0), -1)
            cv2.circle(d2, p, z, (0, 255, 0), -1)
        row = np.hstack([np.pad(t, ((2, 2), (2, 2), (0, 0)), constant_values=60) for t in (up(fr), d1, mp, d2)])
        cv2.putText(row, f"{f}  {n_det} detections", (6, 18), 0, 0.55, (0, 255, 255), 2)
        rows.append(row)
    head = np.full((26, rows[0].shape[1], 3), 30, np.uint8)
    w = rows[0].shape[1] // 4
    for k, n in enumerate(["video", "detections (rings)", f"{colours[0]} response",
                           f"{c['state']:08X} predicted (green dots)"]):
        cv2.putText(head, n, (k * w + 4, 18), 0, 0.5, (230, 230, 230), 1)
    cv2.imwrite(a.out, np.vstack([head] + rows))
    print("wrote", a.out, pick)


if __name__ == "__main__":
    main()
