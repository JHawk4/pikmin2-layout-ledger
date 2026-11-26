"""Several candidate seeds' loose treasures, hole and geyser (and optionally plants) projected through
one comedown camera onto the same frame, tiled for side-by-side comparison.

    python docs/hunt/objgrid.py FRAME.png SUB ZOOM TURN DX,DY SEED[,SEED...] OUT.jpg [--plants] [--crop x0,y0,x1,y1]
"""
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "layout_matcher"))
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def draw(img, sub, seed, H, plants):
    img = img.copy()
    d = lm.dump(sub, int(seed, 16))[0]
    for o in d["objects"]:
        u, v = (int(c) for c in cv2.perspectiveTransform(np.array([[[o["side"], o["ahead"]]]], np.float32), H)[0, 0])
        if (o["kind"] == "plant" or "gashiba" in o["names"] or "elechiba" in o["names"]) and plants:
            cv2.circle(img, (u, v), 8, (255, 0, 255), 1)
            cv2.putText(img, o["names"][-1][:6], (u + 8, v + 4), 0, 0.35, (255, 0, 255), 1)
        elif o["kind"] in ("item", "gate"):
            cv2.circle(img, (u, v), 12, (0, 255, 255), 2)
            cv2.putText(img, o["names"][0], (u + 12, v - 8), 0, 0.5, (0, 0, 0), 3)
            cv2.putText(img, o["names"][0], (u + 12, v - 8), 0, 0.5, (0, 255, 255), 1)
        elif o["kind"] in ("hole", "geyser"):
            cv2.circle(img, (u, v), 16, (0, 255, 0), 2)
            cv2.putText(img, o["kind"], (u + 14, v + 14), 0, 0.5, (0, 255, 0), 1)
    cv2.rectangle(img, (0, 0), (300, 30), (0, 0, 0), -1)
    cv2.putText(img, f"{sub} {seed}", (6, 22), 0, 0.7, (255, 255, 255), 2)
    return img


def main():
    frame, sub, zoom, turn, shift, seeds, out = sys.argv[1:8]
    plants = "--plants" in sys.argv
    dx, dy = (float(v) for v in shift.split(","))
    img = cv2.resize(cv2.imread(frame), (1280, 720))
    H = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]]) @ cd.homography(1280, 720, 16 / 9, float(zoom), float(turn))
    tiles = [img] + [draw(img, sub, s.upper(), H, plants) for s in seeds.split(",")]
    if "--crop" in sys.argv:
        x0, y0, x1, y1 = (int(v) for v in sys.argv[sys.argv.index("--crop") + 1].split(","))
        tiles = [t[y0:y1, x0:x1] for t in tiles]
    while len(tiles) % 2:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)]))


if __name__ == "__main__":
    main()
