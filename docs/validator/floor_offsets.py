"""Floor-shape score of a seed and its neighbours +-NB draws, on hand-picked comedown frames.

floor_check.py's scorer (layoutmatch floor2: lit probes on unit cells, best of a camera grid),
but with the comedown frames and the title-only reference frames given explicitly, for videos
where its automatic shot finder fails. Answers: does the seed beat its own draw neighbours
(the "one draw late" risk) and a background of unrelated seeds?

    python docs/validator/floor_offsets.py VIDEO SUB SEED F0,F1,F2 R0-R1 [--aspect 16:9] [--crop x,y,w,h] [--save OUT.jpg]
"""
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "challenge_dive"))
import floor_check as fc  # noqa: E402
from p2seeds import rng  # noqa: E402


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    video, sub, seed = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
    fs = [int(v) for v in sys.argv[4].split(",")]
    r0, r1 = (int(v) for v in sys.argv[5].split("-"))
    p, q = arg("--aspect", "16:9").split(":")
    aspect = float(p) / float(q)
    cap = cv2.VideoCapture(video)
    W0, H0 = int(cap.get(3)), int(cap.get(4))
    x, y, w, h = (int(v) for v in arg("--crop", f"0,0,{W0},{H0}").split(","))

    def get(f):
        return fc.frames(cap, f, f + 1)[0][y:y + h, x:x + w]

    W, Hh = int(round(720 * aspect)), 720
    img = np.mean([cv2.resize(get(f), (W, Hh), interpolation=cv2.INTER_AREA) for f in fs], 0).astype(np.uint8)
    ref = np.median(np.stack([cv2.resize(get(f), (W, Hh)) for f in range(r0, r1 + 1, 2)]), 0).astype(np.uint8)
    us, vs, bright, thr = fc.probes(img, ref, W, Hh)
    if "--save" in sys.argv:
        vis = img.copy()
        for u, v, b in zip(us, vs, bright):
            cv2.circle(vis, (int(u), int(v)), 2, (0, 255, 0) if b else (0, 0, 255), -1)
        cv2.imwrite(arg("--save", ""), vis)
    tmp = os.path.join("data", "val", "fo_tmp")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    cams = fc.write_probes(tmp + ".probes", us, vs, bright, W, Hh, aspect)
    nb = fc.NB
    near = fc.score(sub, rng.next_seed(seed, nb), 2 * nb + 1, tmp + ".probes", tmp + ".near")
    bg = fc.score(sub, rng.prev_seed(seed, 1000), fc.BG, tmp + ".probes", tmp + ".bg")[:, 0]
    sc, cam = near[::-1, 0], near[::-1, 1]
    med = float(np.median(bg))
    mad = float(np.median(np.abs(bg - med)) * 1.4826 + 1e-6)
    print(f"{sub} {seed:08X}: {int(bright.sum())}/{len(us)} probes lit; background median {med:.0f}, max {bg.max():.0f}")
    for o in (-2, -1, 0, 1, 2):
        s = sc[o + nb]
        print(f"  offset {o:+d}: score {s:7.1f} z {(s - med) / mad:5.1f} rank among +-{nb}: {int((sc > s).sum()) + 1:2d}, "
              f"background seeds scoring >= : {int((bg >= s).sum())}/{len(bg)}  cam {cams[int(cam[o + nb])]}")
    top = np.argsort(-sc)[:5]
    print("  best offsets:", [(int(i) - nb, round(float(sc[i]))) for i in top])


if __name__ == "__main__":
    main()
