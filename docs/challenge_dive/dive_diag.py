"""Diagnostic images of a dive read: what the reader sees, and where a candidate state puts each Pikmin.

    python docs/challenge_dive/dive_diag.py VIDEO RESULT.json OUT.png [--cand 0 1] [--frames 10]

RESULT.json is a read_dive result (run_wrs.py / crosscheck output with "candidates", "region",
"reg"). One row per sampled frame. Columns:
  1. the video crop (the dive region);
  2. what the reader compares against: |frame - background| thresholded and blurred (white = changed);
  3. per candidate: the crop with the candidate's predicted Pikmin positions as dots in each
     Pikmin's colour;
  4. per candidate: the residual (green = changed in the video but not predicted, magenta = predicted
     but not there, white = both), with that frame's share of the loss.
The reader has no per-Pikmin detector: it renders a sprite at each predicted position and scores the
squared difference from column 2 over all frames (image_loss).
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "p2seeds", "src"))
from p2seeds.challenge import dive as cd  # noqa: E402

BGR = {"red": (40, 40, 255), "yellow": (0, 230, 255), "blue": (255, 120, 0), "white": (255, 255, 255),
       "purple": (200, 60, 160)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("result")
    ap.add_argument("out")
    ap.add_argument("--cand", type=int, nargs="+", default=[0])
    ap.add_argument("--state", nargs="*", default=[], help="extra states (hex) to draw at the first candidate's geometry")
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--zoom", type=int, default=3)
    a = ap.parse_args()
    r = json.load(open(a.result))
    counts = r["counts"]
    region = tuple(r["region"])
    scale = float(np.sqrt(r["reg"]["sx"] * r["reg"]["sy"]))
    cands = [(c["state"], cd.geometry_from_vector(c["geometry"]), f"#{k} {c['state']:08X}")
             for k, c in enumerate(r["candidates"]) if k in a.cand]
    for s in a.state:
        cands.append((int(s, 16), cands[0][1], f"{int(s, 16):08X}"))
    g = cands[0][1]
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    dv = cd.DiveVideo(a.video, int(g.f0) + 2, int(g.f0) + span, None, region, scale=scale)
    frames = sorted(dv.obs)
    # sample frames where something is moving
    mass = np.array([dv.obs[f].sum() for f in frames])
    busy = [f for f, m in zip(frames, mass) if m > 0.05 * mass.max()]
    pick = [busy[int(i)] for i in np.linspace(0, len(busy) - 1, min(a.frames, len(busy)))]
    cap = cv2.VideoCapture(a.video)
    raw = {}
    for f in pick:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, im = cap.read()
        x0, y0, x1, y1 = region
        raw[f] = im[y0:y1, x0:x1].copy()
    z = a.zoom
    preds = []
    for s, gc, label in cands:
        flat = cd.flatten(cd.dive_params(s, counts))
        pf = cd.predicted_frames(flat, gc, frames)
        losses = {f: float(((dv.renderer.render(*pf[f]) - dv.obs[f]) ** 2).sum()) for f in frames}
        preds.append((flat, gc, pf, losses, label))
    rows = []
    for f in pick:
        up = lambda im: cv2.resize(im, None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)  # noqa: E731
        tiles = [up(raw[f]), up(cv2.cvtColor((dv.obs[f] * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR))]
        for flat, gc, pf, losses, label in preds:
            dots = up(raw[f])
            us, vs = pf[f]
            for u, v, c in zip(us, vs, flat[:, 3].astype(int)):
                if u != u:
                    continue
                p = (int(round((u - region[0]) * z)), int(round((v - region[1]) * z)))
                cv2.circle(dots, p, z + 1, (0, 0, 0), -1)
                cv2.circle(dots, p, z, BGR[cd.COLOURS[c]], -1)
            rend = dv.renderer.render(*pf[f])
            res = np.zeros(rend.shape + (3,), np.uint8)
            o = dv.obs[f]
            res[..., 1] = (np.clip(o, 0, 1) * 255).astype(np.uint8)
            res[..., 0] = res[..., 2] = (np.clip(rend, 0, 1) * 255).astype(np.uint8)
            res = np.maximum(res, (np.minimum(o, rend)[..., None] * 255).astype(np.uint8))
            res = up(res)
            cv2.putText(res, f"{losses[f] / 1000:.1f}k", (4, 16), 0, 0.5, (0, 255, 255), 1)
            tiles += [dots, res]
        row = np.hstack([np.pad(t, ((2, 2), (2, 2), (0, 0)), constant_values=60) for t in tiles])
        cv2.putText(row, str(f), (6, 18), 0, 0.55, (0, 255, 255), 2)
        rows.append(row)
    head = np.full((28, rows[0].shape[1], 3), 30, np.uint8)
    w = raw[pick[0]].shape[1] * z + 4
    names = ["video", "reader input"] + sum([[f"{l} positions", f"{l} residual  total {sum(ls.values()) / 1000:.0f}k"]
                                             for _, _, _, ls, l in preds], [])
    for k, n in enumerate(names):
        cv2.putText(head, n, (k * w + 4, 19), 0, 0.45, (230, 230, 230), 1)
    cv2.imwrite(a.out, np.vstack([head] + rows))
    print("wrote", a.out, "frames", pick)


if __name__ == "__main__":
    main()
