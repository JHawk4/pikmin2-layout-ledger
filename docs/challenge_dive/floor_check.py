"""Floor-1 layout check of dive candidates: the overhead "comedown" shot under the floor title.

    python docs/challenge_dive/floor_check.py VIDEO.mp4 --rows anch3_VIDEO.json --out OUT.json

For each dive row (anchored_eval.py output) the comedown frames are found after the menu fades,
the lit floor is sampled on a probe grid, and layoutmatch `floor2` (layout-matcher branch, Rust on
CaveGen3) scores candidate floor-1 layouts: +1 per bright probe on a unit cell, -0.7 per dark one,
best of a grid of camera zooms and turns. Scored here: the states within +-NB draws of the expected
dive state, against a background of BG consecutive states further back.

The floor-1 layout seed is the dive first state + 999 draws.
"""
import argparse
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "p2seeds", "src"))
from p2seeds import rng  # noqa: E402

EXE = os.environ.get("P2SEEDS_LAYOUTMATCH", os.path.abspath(os.path.join(
    ROOT, "..", "wii-digits-728a39", "data", "build", "cg3lm", "release", "layoutmatch.exe")))

# CaveGen3 comedown camera (render.rs COMEDOWN_CAMERA), as in the layout matcher (comedown.py)
EYE = np.array([-0.286, 1320.99, -3.170])
TARGET = np.array([4.737, 6.729, -1.692])
FOVY, ROLL = 74.11, 87.82
NB, BG = 40, 20000
STEP, DARK = 14, 0.7
ZOOMS = np.round(np.arange(0.9, 1.71, 0.05), 2)
TURNS = np.arange(-12, 5, 2)


def corners(aspect):
    back = EYE - TARGET
    back /= np.linalg.norm(back)
    right = np.cross([0.0, 1.0, 0.0], back)
    right /= np.linalg.norm(right)
    up = np.cross(back, right)
    t = math.tan(math.radians(FOVY / 2))
    s, c = math.sin(math.radians(ROLL)), math.cos(math.radians(ROLL))
    out = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x, y = sx * t * aspect, sy * t
        x, y = x * c - y * s, x * s + y * c
        d = right * x + up * y - back
        k = -EYE[1] / d[1]
        out.append((EYE[2] + k * d[2], -(EYE[0] + k * d[0])))
    return out


def homography(w, h, aspect, zoom, turn):
    """Pod frame (side, ahead) -> pixels of a w x h game image."""
    src = np.float32([[s, a] for a, s in corners(aspect)])
    dst = np.float32([[0, h], [w, h], [w, 0], [0, 0]])
    H = cv2.getPerspectiveTransform(src, dst)
    r = math.radians(turn)
    C = np.array([[1, 0, w / 2], [0, 1, h / 2], [0, 0, 1]])
    S = np.array([[zoom * math.cos(r), -zoom * math.sin(r), 0], [zoom * math.sin(r), zoom * math.cos(r), 0], [0, 0, 1]])
    return C @ S @ np.linalg.inv(C) @ H


def frames(cap, a, b):
    cap.set(cv2.CAP_PROP_POS_FRAMES, a)
    out = []
    for _ in range(a, b):
        ok, f = cap.read()
        if not ok:
            break
        out.append(f)
    return out


def game_area(cap, visit):
    """Bounding box of the bright challenge menu during the visit (rows contiguous from its middle,
    so a splits bar under the game is left out)."""
    fs = frames(cap, visit[0], min(visit[1], visit[0] + 30))
    g = np.mean([f.max(2) for f in fs], 0)
    h, w = g.shape
    cols = np.where(g[h // 4:3 * h // 4].mean(0) > 40)[0]
    on = g[:, cols.min():cols.max()].mean(1) > 40
    y0 = y1 = h // 3
    while y0 > 0 and on[y0 - 1]:
        y0 -= 1
    while y1 < h - 1 and on[y1 + 1]:
        y1 += 1
    return int(cols.min()), int(y0), int(cols.max() - cols.min() + 1), int(y1 - y0 + 1)


def comedown_frames(cap, visit, crop, span=500):
    """The lit overhead shot under the floor title. After the menu goes dark the title stands on
    black; the shot is the first rise of the brightness outside the title box above that level.
    Returns its frame numbers, the frames, and the title-only reference (median of frames before)."""
    x, y, w, h = crop
    fs = [f[y:y + h, x:x + w] for f in frames(cap, visit[1], visit[1] + span)]
    m = np.ones((h, w), bool)
    m[int(0.05 * h):int(0.65 * h), int(0.15 * w):int(0.85 * w)] = False      # title box
    b = np.array([f.max(2)[m].mean() for f in fs])
    dark = float(b.min()) + 4
    if False:
        return None, None, None, dict(why="menu never dark")
    d0 = int(np.argmax(b < dark))
    base = float(np.median(b[d0:d0 + 40]))
    up = np.where(b[d0:] > base + 6)[0]
    if not len(up):
        return None, None, None, dict(why="no rise")
    i = d0 + int(up[0])
    j = i
    while j < len(b) - 1 and j - i < 45 and b[j + 1] > base + 6:
        j += 1
    seg = b[i:j + 1]
    # the first frames carry the petal burst of the falling pod, the last ones the fade-out:
    # take the stillest frames of the second half that are still lit
    small = [cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.float32) for f in fs[i:j + 1]]
    mot = np.array([np.abs(small[k + 1] - small[k]).mean() for k in range(len(small) - 1)] + [1e9])
    ok = [k for k in range(len(seg) // 2, len(seg) - 2) if seg[k:k + 3].min() >= 0.7 * np.median(seg)]
    if not ok:
        return None, None, None, dict(why="shot too short", run=[visit[1] + i, visit[1] + j])
    k = min(ok, key=lambda k: mot[k] + mot[k + 1])
    sel = [i + k, i + k + 1, i + k + 2]
    ref = np.median(np.stack(fs[max(d0, i - 24):max(d0 + 1, i - 4)]), 0).astype(np.uint8)
    return [visit[1] + k for k in sel], [fs[k] for k in sel], ref, dict(run=[visit[1] + i, visit[1] + j], peak=float(seg.max()), base=base)


def probes(img, ref, w, h):
    """Probe grid: lit floor = brighter than the title-only reference. Probes on the title text
    (bright in the reference) are dropped."""
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 2).astype(np.float32)
    r = cv2.GaussianBlur(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), (0, 0), 2).astype(np.float32)
    us, vs = np.meshgrid(np.arange(STEP // 2, w, STEP), np.arange(STEP // 2, h, STEP))
    us, vs = us.ravel(), vs.ravel()
    keep = r[vs, us] < 30
    us, vs = us[keep], vs[keep]
    val = np.clip(g[vs, us] - r[vs, us], 0, 255).astype(np.uint8)
    thr, _ = cv2.threshold(val.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return us, vs, val > thr, float(thr)


def write_probes(path, us, vs, bright, w, h, aspect):
    pix = np.stack([us, vs], 1).astype(np.float32)[None]
    blocks, cams = [], []
    for z in ZOOMS:
        for t in TURNS:
            Hinv = np.linalg.inv(homography(w, h, aspect, float(z), float(t)))
            blocks.append(cv2.perspectiveTransform(pix, Hinv)[0])
            cams.append((float(z), float(t)))
    wt = np.where(bright, 1.0, -DARK).astype(np.float32)
    with open(path, "wb") as f:
        np.array([len(us), len(blocks)], np.uint32).tofile(f)
        np.concatenate(blocks).astype(np.float32).tofile(f)
        wt.tofile(f)
    return cams


def score(sub, start, count, probes_path, tmp):
    """Scores of `count` layout seeds: start, start-1 draw, start-2 draws, ..."""
    subprocess.run([EXE, "floor2", sub, f"{start & 0xFFFFFFFF:08X}", str(count), probes_path, tmp], check=True)
    return np.fromfile(tmp, np.float32).reshape(-1, 2)


GAME_REF = (50, 6, 541, 304)      # the game picture in the menu registration's reference frame
REF_R0 = (20, 0)


def game_rect(reg, shape):
    """The game picture in this video, from the per-video menu registration."""
    H, W = shape[:2]
    x = reg["lx"] + (GAME_REF[0] - REF_R0[0]) * reg["sx"]
    y = reg["ly"] + (GAME_REF[1] - REF_R0[1]) * reg["sy"]
    x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
    x1, y1 = min(W, int(round(x + GAME_REF[2] * reg["sx"]))), min(H, int(round(y + GAME_REF[3] * reg["sy"])))
    return x0, y0, x1 - x0, y1 - y0


def check(video, cap, row, tmp, aspect, save=None, reg=None):
    visit = row["visit"]
    crop = game_rect(reg, (int(cap.get(4)), int(cap.get(3)))) if reg else game_area(cap, visit)
    ns, fs, ref, info = comedown_frames(cap, visit, crop)
    res = dict(ch=row["ch"], visit=visit, crop=crop, **info)
    if ns is None:
        return res
    x, y, w, h = crop
    W, Hh = int(round(720 * aspect)), 720
    img = np.mean([cv2.resize(f, (W, Hh), interpolation=cv2.INTER_AREA) for f in fs], 0).astype(np.uint8)
    ref = cv2.resize(ref, (W, Hh), interpolation=cv2.INTER_AREA)
    us, vs, bright, thr = probes(img, ref, W, Hh)
    if save:
        vis = img.copy()
        for u, v, b in zip(us, vs, bright):
            cv2.circle(vis, (int(u), int(v)), 2, (0, 255, 0) if b else (0, 0, 255), -1)
        cv2.imwrite(save, vis)
    cams = write_probes(tmp + ".probes", us, vs, bright, W, Hh, aspect)
    sub = f"CH{row['ch']}-1"
    truth = rng.next_seed(row["truth"], 999)                    # floor-1 layout seed
    near = score(sub, rng.next_seed(truth, NB), 2 * NB + 1, tmp + ".probes", tmp + ".near")
    bg = score(sub, rng.prev_seed(truth, 1000), BG, tmp + ".probes", tmp + ".bg")[:, 0]
    sc = near[::-1, 0]                                          # index = offset + NB
    cam = near[::-1, 1]
    med = float(np.median(bg))
    mad = float(np.median(np.abs(bg - med)) * 1.4826 + 1e-6)
    order = np.argsort(-sc)
    res.update(frames=ns, bright=int(bright.sum()), probes=int(len(us)), thr=thr, bg_median=med, bg_mad=mad,
               bg_max=float(bg.max()),
               offs={str(o): dict(score=float(sc[o + NB]), z=(float(sc[o + NB]) - med) / mad,
                                  rank=int((sc > sc[o + NB]).sum()) + 1,
                                  bg_rank=int((bg >= sc[o + NB]).sum()) + 1,
                                  cam=cams[int(cam[o + NB])])
                     for o in (0, 1, 2, -4, 4, -8, 8)},
               best=[dict(off=int(i) - NB, score=float(sc[i])) for i in order[:5]])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--aspect", default=None)
    ap.add_argument("--only", type=int, nargs="*")
    ap.add_argument("--save")
    ap.add_argument("--reg", help="per-video menu registration JSON (anchored_eval cache)")
    a = ap.parse_args()
    if a.aspect:
        p, q = a.aspect.split(":")
        aspect = float(p) / float(q)
    else:
        aspect = 16 / 9 if "wiiu" in a.video else 4 / 3
    rows = json.load(open(a.rows))
    rows = rows if isinstance(rows, list) else list(rows.values())
    cap = cv2.VideoCapture(a.video)
    reg = json.load(open(a.reg)) if a.reg else None
    out = []
    for r in rows:
        if a.only and r["ch"] not in a.only:
            continue
        save = os.path.join(a.save, f"{os.path.basename(a.video)[:6]}_ch{r['ch']}.jpg") if a.save else None
        res = check(a.video, cap, r, a.out + ".tmp", aspect, save, reg)
        res["dive_off"] = r.get("grey_off")
        out.append(res)
        if "offs" in res:
            o = res["offs"]
            print(f"CH{res['ch']:<3} dive off {str(res['dive_off']):>5}  bright {res['bright']:4d}/{res['probes']}  " +
                  "  ".join(f"{k:>2}: z {o[k]['z']:5.1f} nr {o[k]['rank']:2d} bg {o[k]['bg_rank']:5d}" for k in ("0", "1", "2", "4", "-4")) +
                  f"  best {[(b['off'], round(b['score'])) for b in res['best'][:3]]}", flush=True)
        else:
            print(f"CH{res['ch']:<3} no comedown found {res.get('why')}", flush=True)
        json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
