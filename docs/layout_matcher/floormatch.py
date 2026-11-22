"""Automatic floor-1 matcher on the comedown shot: the lit floor around the pod against the black
void, compared with every candidate layout's unit footprints.

    python docs/layout_matcher/floormatch.py CH FRAME[,FRAME...] K_LO K_HI OUT_PREFIX [TRUTH_SEED|- [VIDEO CROP END_STATE]]

Seeds are the stage's results-roll first state (data/lm/inventory.json) stepped back k draws.
Probe points every STEP units in the pod's frame are projected through the comedown camera
(comedown.py); those landing in the centre box (title, falling pod) or off screen are dropped.
Each remaining point is floor (bright) or void (dark) by Otsu's threshold on the blurred frame(s)
(the frames are averaged, which suppresses particles). Bright points weigh +1 and dark ones
-DARK_W; layoutmatch's `floor` mode sums the weights of points on unit footprints. Writes
OUT_PREFIX.f32 (score per k), OUT_PREFIX_mask.jpg (the classified points over the frame) and
prints the best k with their seeds and robust z-scores.
"""
import json
import os
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comedown as cd  # noqa: E402
import lm  # noqa: E402
from inventory import WR  # noqa: E402
from wr_comedown import INV, crop_for, read  # noqa: E402

STEP = 40.0
RADIUS = 1300.0
DARK_W = float(os.environ.get("FM_DARK_W", 0.3))
MARGIN = float(os.environ.get("FM_MARGIN", 40))
CENTRE = tuple(int(v) for v in os.environ.get("FM_CENTRE", "250,140,1030,450").split(","))


def frame_image(video, frames, crop):
    x, y, w, h = crop
    acc = None
    for n in frames:
        img = read(video, n)[y:y + h, x:x + w]
        img = cv2.resize(img, (1280, 720), interpolation=cv2.INTER_AREA).astype(np.float32)
        acc = img if acc is None else acc + img
    return (acc / len(frames)).astype(np.uint8)


def probes(img):
    H = cd.homography(1280, 720, 16 / 9)
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 3)
    v = np.arange(-RADIUS, RADIUS + 1, STEP)
    A, S = np.meshgrid(v, v, indexing="ij")
    pts = np.stack([S.ravel(), A.ravel()], 1).astype(np.float32)
    px = cv2.perspectiveTransform(pts[None], H)[0]
    x0, y0, x1, y1 = CENTRE
    ok = (px[:, 0] >= 8) & (px[:, 0] < 1272) & (px[:, 1] >= 8) & (px[:, 1] < 712)
    ok &= ~((px[:, 0] > x0) & (px[:, 0] < x1) & (px[:, 1] > y0) & (px[:, 1] < y1))
    pts, px = pts[ok], px[ok]
    val = g[px[:, 1].astype(int), px[:, 0].astype(int)]
    thr, _ = cv2.threshold(val.reshape(-1, 1).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = val > thr
    return pts, px, bright, thr


def main():
    ch = int(sys.argv[1])
    frames = [int(f) for f in sys.argv[2].split(",")]
    lo, hi, prefix = int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    truth = int(sys.argv[6], 16) & 0x7FFFFFFF if len(sys.argv) > 6 and sys.argv[6] != "-" else None
    if len(sys.argv) > 9:
        # another video: VIDEO CROP END_STATE
        video, crop, end_state = sys.argv[7], tuple(int(v) for v in sys.argv[8].split(",")), sys.argv[9]
        e = dict(roll_state=end_state)
    else:
        e = next(x for x in json.load(open(INV)) if x["ch"] == ch)
        video = os.path.join(WR, e["video"])
        crop = crop_for(video)
    img = frame_image(video, frames, crop)
    pts, px, bright, thr = probes(img)
    vis = img.copy()
    for (u, w), b in zip(px, bright):
        cv2.circle(vis, (int(u), int(w)), 3, (0, 255, 0) if b else (0, 0, 255), -1)
    cv2.rectangle(vis, CENTRE[:2], CENTRE[2:], (255, 255, 255), 1)
    cv2.imwrite(prefix + "_mask.jpg", vis)
    rows = np.stack([pts[:, 1], pts[:, 0], np.where(bright, 1.0, -DARK_W)], 1).astype(np.float32)
    rows.tofile(prefix + "_pts.bin")
    end = int(e["roll_state"], 16)
    start = lm.seed_at(end, lo)
    subprocess.run([lm.EXE, "floor", f"CH{ch}-1", f"{start:08X}", str(hi - lo), prefix + "_pts.bin",
                    str(MARGIN), prefix + ".f32"], check=True)
    sc = np.fromfile(prefix + ".f32", np.float32)
    med = np.median(sc)
    mad = np.median(np.abs(sc - med)) * 1.4826 + 1e-6
    order = np.argsort(-sc)
    print(f"CH{ch}: {len(pts)} probes ({bright.sum()} bright, threshold {thr:.0f}), window k {lo}..{hi}")
    if truth is not None:
        for t in (truth, truth | 0x80000000):
            d = lm.rng.distance(t, start, limit=1 << 26)
            if d is not None and d < len(sc):
                print(f"  truth k {lo + d}: score {sc[d]:.1f}, z {(sc[d] - med) / mad:.1f}, rank {int((sc > sc[d]).sum()) + 1}")
    best = []
    for i in order[:15]:
        s = lm.seed_at(start, int(i)) & 0x7FFFFFFF
        best.append(dict(k=lo + int(i), seed=f"{s:08X}", score=float(sc[i]), z=float((sc[i] - med) / mad)))
        print(f"  k {lo + int(i):8d} seed {s:08X} score {sc[i]:7.1f} z {(sc[i] - med) / mad:6.1f}")
    json.dump(dict(ch=ch, frames=frames, window=[lo, hi], best=best, median=float(med), mad=float(mad)),
              open(prefix + ".json", "w"), indent=1)


if __name__ == "__main__":
    main()
