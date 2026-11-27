"""Draw a layout's objects, projected through the landing camera, on a video frame.

    python docs/layout_matcher/overlay.py SUB SEED FRAME.png OUT.png
"""
import sys

import cv2

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
import lm  # noqa: E402

COL = {"teki": (0, 0, 255), "plant": (0, 255, 0), "item": (0, 255, 255), "gate": (255, 0, 255),
       "hole": (255, 255, 255), "geyser": (255, 255, 0), "capteki": (0, 128, 255)}


def overlay(sub, seed, frame, out, label=True):
    d = lm.dump(sub, seed)[0]
    img = cv2.imread(frame)
    h, w = img.shape[:2]
    px, py = lm.project(0, 0, w=w, h=h)
    cv2.drawMarker(img, (int(px), int(py)), (255, 255, 255), cv2.MARKER_CROSS, 14, 2)
    for o in d["objects"]:
        if o["ahead"] < -700 or abs(o["side"]) > 1500 or o["ahead"] > 2500:
            continue
        x, y = lm.project(o["ahead"], o["side"], w=w, h=h)
        x, y = int(x), int(y)
        if not (0 <= x < w and 0 <= y < h):
            continue
        c = COL.get(o["kind"], (200, 200, 200))
        cv2.circle(img, (x, y), 5, c, 2)
        if label:
            cv2.putText(img, o["names"][0][:10], (x + 6, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, c, 1)
    cv2.imwrite(out, img)


if __name__ == "__main__":
    overlay(sys.argv[1], int(sys.argv[2], 16), sys.argv[3], sys.argv[4])
