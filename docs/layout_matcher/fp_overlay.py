"""Draw a layout's unit footprints (cells) through the comedown camera on a frame image.

    python docs/layout_matcher/fp_overlay.py IMG.jpg SUB SEED OUT.jpg [ZOOM TURN]
"""
import math
import sys

import cv2
import numpy as np

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def main():
    img = cv2.resize(cv2.imread(sys.argv[1]), (1280, 720))
    d = lm.dump(sys.argv[2], int(sys.argv[3], 16))[0]
    zoom = float(sys.argv[5]) if len(sys.argv) > 5 else None
    turn = float(sys.argv[6]) if len(sys.argv) > 6 else None
    H = cd.homography(1280, 720, 16 / 9, zoom, turn)
    P = d["pod"]
    t = math.radians(P["angle"])
    f = (math.sin(t), math.cos(t))
    r = (-f[1], f[0])
    for u in d["units"]:
        w, h = u["w"], u["h"]
        for cx in range(w):
            for cz in range(h):
                corners = []
                for ox, oz in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    X, Z = (u["x"] + cx + ox) * 170 - P["x"], (u["z"] + cz + oz) * 170 - P["z"]
                    corners.append((X * r[0] + Z * r[1], X * f[0] + Z * f[1]))   # (side, ahead)
                p = cv2.perspectiveTransform(np.float32([corners]), H)[0].astype(np.int32)
                cv2.polylines(img, [p], True, (255, 255, 0) if "room" in u["name"] else (0, 255, 255), 1)
    c = cv2.perspectiveTransform(np.float32([[[0, 0]]]), H)[0, 0]
    cv2.drawMarker(img, (int(c[0]), int(c[1])), (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
    a = cv2.perspectiveTransform(np.float32([[[0, 150]]]), H)[0, 0]
    cv2.arrowedLine(img, (int(c[0]), int(c[1])), (int(a[0]), int(a[1])), (255, 255, 255), 2)
    cv2.imwrite(sys.argv[4], img)


if __name__ == "__main__":
    main()
