"""The comedown view: the still, nearly top-down shot under the floor title (frame 0 of the
cutscene s0B_cv_coursein), on every floor. Its camera is known (CaveGen3 render.rs,
COMEDOWN_CAMERA), so the pod-frame <-> screen homography needs no calibration.

    python docs/layout_matcher/comedown.py VIDEO FRAME CROP|full ASPECT(16:9|4:3) OUT.png [SEED SUB]

Writes the frame rectified to the pod frame (grid every 100 units), optionally with a layout drawn
on it.
"""

import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lm  # noqa: E402
from register import game_frames  # noqa: E402

EYE = np.array([-0.286, 1320.99, -3.170])
TARGET = np.array([4.737, 6.729, -1.692])
FOVY, ROLL = 74.11, 87.82


def corners(aspect):
    """(ahead, side) of the screen corners bottom-left, bottom-right, top-right, top-left."""
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


# Correction measured on videos: the shot appears this much closer and turned (degrees) than
# CaveGen3's frame-0 camera model (fitted on the CH10 record, checked on cmal04/cmal08).
ZOOM = float(os.environ.get("CD_ZOOM", 1.576))
TURN = float(os.environ.get("CD_TURN", -6.17))


def homography(w, h, aspect, zoom=None, turn=None):
    """Pod frame (side, ahead) -> pixels of a w x h game image."""
    zoom = ZOOM if zoom is None else zoom
    turn = TURN if turn is None else turn
    src = np.float32([[s, a] for a, s in corners(aspect)])
    dst = np.float32([[0, h], [w, h], [w, 0], [0, 0]])
    H = cv2.getPerspectiveTransform(src, dst)
    r = math.radians(turn)
    C = np.array([[1, 0, w / 2], [0, 1, h / 2], [0, 0, 1]])
    S = np.array([[zoom * math.cos(r), -zoom * math.sin(r), 0], [zoom * math.sin(r), zoom * math.cos(r), 0], [0, 0, 1]])
    return C @ S @ np.linalg.inv(C) @ H


SCALE = 0.35
SIDE, AHEAD = (-1300, 1300), (-1300, 1300)


def rectify(img, aspect, scale=SCALE, side=SIDE, ahead=AHEAD):
    h, w = img.shape[:2]
    H = homography(w, h, aspect)
    M = np.array([[1 / scale, 0, side[0]], [0, -1 / scale, ahead[1]], [0, 0, 1]])
    size = (int((side[1] - side[0]) * scale), int((ahead[1] - ahead[0]) * scale))
    out = cv2.warpPerspective(img, H @ M, size, flags=cv2.WARP_INVERSE_MAP | cv2.INTER_CUBIC, borderValue=(40, 40, 40))
    to_out = lambda a, s: ((s - side[0]) * scale, (ahead[1] - a) * scale)  # noqa: E731
    for v in range(-1200, 1201, 100):
        x, _ = to_out(0, v)
        _, y = to_out(v, 0)
        col = (255, 255, 255) if v % 400 == 0 else (110, 110, 110)
        cv2.line(out, (int(x), 0), (int(x), size[1]), col, 1)
        cv2.line(out, (0, int(y)), (size[0], int(y)), col, 1)
        if v % 400 == 0:
            cv2.putText(out, str(v), (int(x) + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
            cv2.putText(out, str(v), (2, int(y) - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
    return out, to_out


COL = {"plant": (0, 255, 0), "item": (0, 255, 255), "teki": (0, 0, 255), "geyser": (255, 0, 255),
       "hole": (255, 255, 255), "gate": (255, 128, 0), "capteki": (0, 128, 255)}


def draw(out, to_out, sub, seed, labels=True):
    d = lm.dump(sub, seed)[0]
    for o in d["objects"]:
        x, y = to_out(o["ahead"], o["side"])
        if 0 <= x < out.shape[1] and 0 <= y < out.shape[0]:
            c = COL.get(o["kind"], (200, 200, 200))
            cv2.circle(out, (int(x), int(y)), 5, c, 1)
            if labels:
                cv2.putText(out, o["names"][-1 if o["kind"] == "teki" else 0][:8], (int(x) + 5, int(y) + 3),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, c, 1)
    return out


def main():
    video, frame = sys.argv[1], int(sys.argv[2])
    crop = None if sys.argv[3] == "full" else tuple(int(v) for v in sys.argv[3].split(","))
    aspect = 16 / 9 if sys.argv[4] == "16:9" else 4 / 3
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
    ok, img = cap.read()
    if crop:
        x, y, w, h = crop
        img = img[y:y + h, x:x + w]
    img = cv2.resize(img, (1280, int(1280 / aspect)), interpolation=cv2.INTER_CUBIC)
    out, to_out = rectify(img, aspect)
    if len(sys.argv) > 7:
        out = draw(out, to_out, sys.argv[7], int(sys.argv[6], 16))
    cv2.imwrite(sys.argv[5], out)


if __name__ == "__main__":
    main()
