"""Numbered object spots of a sublevel drawn on a comedown/fly-over frame, plus an enlarged crop of
each spot, for reading which object sits where on floors whose pod room is fixed.

    python docs/hunt/spotsheet.py FRAME.png SUB ZOOM TURN DX,DY OUT_PREFIX [KINDS] [N]

KINDS: comma list of layoutmatch kinds (default item,hole,geyser,plant); N seeds sampled (2000).
The camera (ZOOM, TURN, DX,DY) comes from docs/hunt/cdcheck.py on any seed (the room is fixed).
Writes OUT_PREFIX_spots.jpg (numbered), OUT_PREFIX_crops.jpg (one tile per spot, labelled with
what CaveGen3 can put there) and OUT_PREFIX_spots.json (spot number -> ahead, side, names).
Only spots that land inside the frame are drawn.
"""
import collections
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "layout_matcher"))
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def spots(sub, kinds, n):
    seeds = [(i * 0x9E3779B1 + 12345) & 0xFFFFFFFF for i in range(n)]
    sp = collections.defaultdict(collections.Counter)
    for i in range(0, n, 250):
        for d in lm.dump(sub, *seeds[i:i + 250]):
            for o in d["objects"]:
                if o["kind"] in kinds:
                    key = (round(o["ahead"] / 10) * 10, round(o["side"] / 10) * 10)
                    sp[key][o["names"][-1] if o["kind"] in ("plant", "teki") else o["names"][0]] += 1
    # merge spots within 30 units
    out = []
    for (a, s), c in sorted(sp.items(), key=lambda kv: -sum(kv[1].values())):
        for e in out:
            if (e["ahead"] - a) ** 2 + (e["side"] - s) ** 2 < 30 ** 2:
                e["names"].update(c)
                break
        else:
            out.append({"ahead": a, "side": s, "names": collections.Counter(c)})
    return out


def main():
    frame, sub, zoom, turn, shift, prefix = sys.argv[1:7]
    kinds = (sys.argv[7] if len(sys.argv) > 7 else "item,hole,geyser,plant").split(",")
    n = int(sys.argv[8]) if len(sys.argv) > 8 else 2000
    dx, dy = (float(v) for v in shift.split(","))
    img = cv2.resize(cv2.imread(frame), (1280, 720))
    sp = spots(sub, kinds, n)
    H = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]]) @ cd.homography(1280, 720, 16 / 9, float(zoom), float(turn))
    px = cv2.perspectiveTransform(np.array([[[s["side"], s["ahead"]] for s in sp]], np.float32), H)[0]
    out, tiles, js = img.copy(), [], []
    for i, ((u, v), s) in enumerate(zip(px, sp)):
        if not (0 <= u < 1280 and 0 <= v < 720):
            continue
        cv2.circle(out, (int(u), int(v)), 12, (0, 255, 255), 1)
        cv2.putText(out, str(i), (int(u) + 9, int(v) - 7), 0, 0.45, (0, 0, 0), 3)
        cv2.putText(out, str(i), (int(u) + 9, int(v) - 7), 0, 0.45, (0, 255, 255), 1)
        x0, y0 = int(u) - 40, int(v) - 40
        pad = cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT)
        t = cv2.resize(pad[y0 + 40:y0 + 120, x0 + 40:x0 + 120], (240, 240), interpolation=cv2.INTER_CUBIC)
        cv2.circle(t, (120, 120), 30, (0, 255, 255), 1)
        top = ",".join(f"{k}" for k, _ in s["names"].most_common(4))
        lab = np.zeros((40, 240, 3), np.uint8)
        cv2.putText(lab, f"{i}", (4, 16), 0, 0.5, (0, 255, 255), 1)
        cv2.putText(lab, top[:34], (4, 34), 0, 0.38, (255, 255, 255), 1)
        tiles.append(np.vstack([lab, t]))
        js.append({"spot": i, "ahead": s["ahead"], "side": s["side"], "u": round(float(u)), "v": round(float(v)),
                   "names": dict(s["names"].most_common())})
    o = cv2.perspectiveTransform(np.array([[[0, 0], [0, 300]]], np.float32), H)[0]
    cv2.arrowedLine(out, tuple(int(v) for v in o[0]), tuple(int(v) for v in o[1]), (0, 0, 255), 2)
    cv2.imwrite(prefix + "_spots.jpg", out)
    cols = 8
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(prefix + "_crops.jpg", np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))
    json.dump(js, open(prefix + "_spots.json", "w"), indent=0)
    print(f"{len(js)} spots in view")


if __name__ == "__main__":
    main()
