"""Draw a seed's unit outlines, plants/teki (magenta), treasures (yellow, labelled) and the
hole/geyser (green) through a comedown camera on a 1280x720 frame image.

    python docs/layout_matcher/seed_overlay.py FRAME.png SUB SEED ZOOM TURN OUT.jpg [DX,DY]
"""
import os
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comedown as cd  # noqa: E402
import lm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    frame, sub, seed, zoom, turn, out = sys.argv[1:7]
    dx, dy = (float(v) for v in (sys.argv[7] if len(sys.argv) > 7 else "0,0").split(","))
    tmp = out + ".fp.jpg"
    subprocess.run([sys.executable, os.path.join(HERE, "fp_overlay.py"), frame, sub, seed, tmp, zoom, turn], check=True)
    img = cv2.resize(cv2.imread(tmp), (1280, 720))
    os.remove(tmp)
    d = lm.dump(sub, int(seed, 16))[0]
    H = cd.homography(1280, 720, 16 / 9, float(zoom), float(turn))
    for o in d["objects"]:
        p = cv2.perspectiveTransform(np.array([[[o["side"], o["ahead"]]]], np.float32), H)[0, 0] + [dx, dy]
        u, v = int(p[0]), int(p[1])
        if o["kind"] in ("plant", "teki"):
            cv2.circle(img, (u, v), 10, (255, 0, 255), 2)
        elif o["kind"] == "item":
            cv2.circle(img, (u, v), 12, (0, 255, 255), 2)
            cv2.putText(img, o["names"][0], (u + 12, v - 8), 0, 0.45, (0, 255, 255), 1)
        elif o["kind"] in ("hole", "geyser"):
            cv2.circle(img, (u, v), 16, (0, 255, 0), 2)
    cv2.imwrite(out, img)


if __name__ == "__main__":
    main()
