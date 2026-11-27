"""Draw a layout's objects through the comedown camera on the raw (cropped) frame.

    python docs/layout_matcher/cd_overlay.py VIDEO FRAME CROP ASPECT SUB SEED OUT.jpg [kinds]
"""
import sys

import cv2
import numpy as np

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
import comedown as c  # noqa: E402
import lm  # noqa: E402


def main():
    video, n, crop, aspect, sub, seed, out = sys.argv[1:8]
    kinds = sys.argv[8].split(",") if len(sys.argv) > 8 else ["plant", "item", "geyser", "hole", "gate", "teki"]
    aspect = 16 / 9 if aspect == "16:9" else 4 / 3
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(n))
    _, img = cap.read()
    x, y, w, h = (int(v) for v in crop.split(","))
    img = cv2.resize(img[y:y + h, x:x + w], (1280, int(1280 / aspect)), interpolation=cv2.INTER_CUBIC)
    H = c.homography(img.shape[1], img.shape[0], aspect)
    d = lm.dump(sub, int(seed, 16))[0]
    pts = [(0, 0, "POD", "pod")] + [(o["ahead"], o["side"], o["names"][-1 if o["kind"] == "teki" else 0][:8], o["kind"])
                                    for o in d["objects"] if o["kind"] in kinds]
    for a, s, name, kind in pts:
        p = cv2.perspectiveTransform(np.float32([[[s, a]]]), H)[0, 0]
        col = c.COL.get(kind, (0, 255, 255))
        cv2.circle(img, (int(p[0]), int(p[1])), 7, col, 2)
        cv2.putText(img, name, (int(p[0]) + 8, int(p[1])), 0, 0.45, col, 1)
    cv2.imwrite(out, img)


if __name__ == "__main__":
    main()
