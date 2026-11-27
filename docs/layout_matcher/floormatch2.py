"""Automatic floor-1 matcher on the comedown shot, with the camera's zoom and turn fitted per seed.

    python docs/layout_matcher/floormatch2.py --video V --crop x,y,w,h --frames a,b,c --sub CHn-1
        --end STATE --lo K --hi K --out PREFIX [--truth SEED]
    python docs/layout_matcher/floormatch2.py --ch N --frames a,b,c --lo K --hi K --out PREFIX
        (a score WR: video, crop and window end from data/lm/inventory.json)

The comedown is the still-ish overhead shot under the floor title. Floor is bright, the void is
black; the title and falling pod sit in a fixed centre box, which is ignored. Probe pixels every
STEP px are classified by Otsu's threshold (frames averaged). For each camera in a grid of zoom x
turn around CaveGen3's model (comedown.py), the probes are mapped to the pod's frame, and
layoutmatch `floor2` scores every seed: +1 per bright probe on a unit cell, -DARK per dark probe on
one, best camera kept. Prints the truth's rank (with --truth) and the best seeds with robust z.
"""
import argparse
import json
import os
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comedown as cd  # noqa: E402
import lm  # noqa: E402

STEP = 28
DARK = 0.7
CENTRE = (250, 140, 1030, 450)
ZOOMS = np.round(np.arange(0.9, 1.71, 0.1), 2)
TURNS = np.arange(-12, 5, 4)
if os.environ.get("FM_FULLTURN"):
    ZOOMS = np.round(np.arange(0.8, 1.61, 0.1), 2)
    TURNS = np.arange(-180, 180, 10)
if os.environ.get("FM_ZOOMS"):          # "lo,hi,step"
    lo, hi, st = (float(v) for v in os.environ["FM_ZOOMS"].split(","))
    ZOOMS = np.round(np.arange(lo, hi + st / 2, st), 3)
if os.environ.get("FM_TURNS"):
    lo, hi, st = (float(v) for v in os.environ["FM_TURNS"].split(","))
    TURNS = np.arange(lo, hi + st / 2, st)


def averaged(video, frames, crop):
    x, y, w, h = crop
    cap = cv2.VideoCapture(video)
    acc = None
    for n in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        img = cv2.resize(cap.read()[1][y:y + h, x:x + w], (1280, 720), interpolation=cv2.INTER_AREA).astype(np.float32)
        acc = img if acc is None else acc + img
    return (acc / len(frames)).astype(np.uint8)


def probes(img):
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 3)
    us, vs = np.meshgrid(np.arange(STEP // 2, 1280, STEP), np.arange(STEP // 2, 720, STEP))
    us, vs = us.ravel(), vs.ravel()
    x0, y0, x1, y1 = CENTRE
    keep = ~((us > x0) & (us < x1) & (vs > y0) & (vs < y1))
    us, vs = us[keep], vs[keep]
    val = g[vs, us]
    thr, _ = cv2.threshold(val.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return us, vs, val > thr, thr


def write_probes(path, us, vs, bright):
    pix = np.stack([us, vs], 1).astype(np.float32)[None]
    blocks, cams = [], []
    for z in ZOOMS:
        for t in TURNS:
            Hinv = np.linalg.inv(cd.homography(1280, 720, 16 / 9, float(z), float(t)))
            blocks.append(cv2.perspectiveTransform(pix, Hinv)[0])     # (side, ahead)
            cams.append((float(z), float(t)))
    w = np.where(bright, 1.0, -DARK).astype(np.float32)
    with open(path, "wb") as f:
        np.array([len(us), len(blocks)], np.uint32).tofile(f)
        np.concatenate(blocks).astype(np.float32).tofile(f)
        w.tofile(f)
    return cams


def run(video, crop, frames, sub, end, lo, hi, prefix, truth=None):
    img = averaged(video, frames, crop)
    us, vs, bright, thr = probes(img)
    vis = img.copy()
    for u, v, b in zip(us, vs, bright):
        cv2.circle(vis, (int(u), int(v)), 2, (0, 255, 0) if b else (0, 0, 255), -1)
    cv2.rectangle(vis, CENTRE[:2], CENTRE[2:], (255, 255, 255), 1)
    cv2.imwrite(prefix + "_mask.jpg", vis)
    cams = write_probes(prefix + "_probes.bin", us, vs, bright)
    start = lm.seed_at(end, lo)
    subprocess.run([lm.EXE, "floor2", sub, f"{start:08X}", str(hi - lo), prefix + "_probes.bin", prefix + ".f32"], check=True)
    a = np.fromfile(prefix + ".f32", np.float32).reshape(-1, 2)
    sc, cam = a[:, 0], a[:, 1].astype(int)
    med = float(np.median(sc))
    mad = float(np.median(np.abs(sc - med)) * 1.4826 + 1e-6)
    print(f"{sub}: {len(us)} probes, {int(bright.sum())} bright (threshold {thr:.0f}); k {lo}..{hi}; median {med:.1f}, MAD {mad:.1f}")
    res = dict(sub=sub, frames=frames, window=[lo, hi], median=med, mad=mad, best=[])
    if truth is not None:
        for t in (truth & 0x7FFFFFFF, truth | 0x80000000):
            d = lm.rng.distance(t, start, limit=1 << 26)
            if d is not None and d < len(sc):
                rank = int((sc > sc[d]).sum()) + 1
                print(f"  truth k {lo + d}: score {sc[d]:.1f} z {(sc[d] - med) / mad:.1f} rank {rank} camera {cams[cam[d]]}")
                res["truth"] = dict(k=lo + d, score=float(sc[d]), rank=rank, camera=cams[cam[d]])
                break
    for i in np.argsort(-sc)[:20]:
        s = lm.seed_at(start, int(i)) & 0x7FFFFFFF
        e = dict(k=lo + int(i), seed=f"{s:08X}", score=float(sc[i]), z=(float(sc[i]) - med) / mad, camera=cams[cam[i]])
        res["best"].append(e)
    for e in res["best"][:10]:
        print(f"  k {e['k']:8d} seed {e['seed']} score {e['score']:7.1f} z {e['z']:5.1f} camera {e['camera']}")
    json.dump(res, open(prefix + ".json", "w"), indent=1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video")
    ap.add_argument("--crop")
    ap.add_argument("--ch", type=int)
    ap.add_argument("--sub")
    ap.add_argument("--end")
    ap.add_argument("--frames", required=True)
    ap.add_argument("--lo", type=int, default=0)
    ap.add_argument("--hi", type=int, default=1_000_000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--truth")
    a = ap.parse_args()
    frames = [int(f) for f in a.frames.split(",")]
    if a.ch:
        from inventory import WR
        from wr_comedown import INV, crop_for
        e = next(x for x in json.load(open(INV)) if x["ch"] == a.ch)
        video = os.path.join(WR, e["video"])
        crop = crop_for(video)
        sub, end = f"CH{a.ch}-1", int(e["roll_state"], 16)
    else:
        video, crop, sub, end = a.video, tuple(int(v) for v in a.crop.split(",")), a.sub, int(a.end, 16)
    run(video, crop, frames, sub, end, a.lo, a.hi, a.out, int(a.truth, 16) if a.truth else None)


if __name__ == "__main__":
    main()
