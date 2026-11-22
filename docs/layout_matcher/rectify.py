"""Warp a registered fly-over frame into the pod's frame: a top-down image with the pod at the
centre, its facing up, and a grid every 100 units (labelled every 200), for reading where things
are in game units.

    python docs/layout_matcher/rectify.py VIDEO FRAME CROP|full REG.json H_REF.json OUT.png [SEED SUB]

REG.json is register.py's output (or refs.py match's, whose entries carry H_pod; pass - for H_REF) (homography video-frame -> reference frame; the entry for FRAME
is used). H_REF.json maps pod-frame (side, ahead) to reference pixels (calib.py). With SEED, that
layout's objects are drawn on top (for checking a candidate).
"""

import json
import sys

import cv2
import numpy as np

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
import lm  # noqa: E402
from register import W, H, game_frames  # noqa: E402

SCALE = 0.6          # output pixels per game unit
SIDE, AHEAD = (-750, 750), (-450, 650)


def out_to_pod():
    """Affine: output pixel -> (side, ahead)."""
    w = int((SIDE[1] - SIDE[0]) * SCALE)
    h = int((AHEAD[1] - AHEAD[0]) * SCALE)
    M = np.array([[1 / SCALE, 0, SIDE[0]], [0, -1 / SCALE, AHEAD[1]], [0, 0, 1]])
    return M, (w, h)


def pod_to_out(ahead, side):
    return (side - SIDE[0]) * SCALE, (AHEAD[1] - ahead) * SCALE


def rectify(frame_img, H_reg, H_ref, H_pod=None):
    """H_pod (pod frame -> video pixels) if given, else inv(H_reg) @ H_ref."""
    M, size = out_to_pod()
    if H_pod is None:
        H_pod = np.linalg.inv(np.asarray(H_reg)) @ np.asarray(H_ref)
    T = np.asarray(H_pod) @ M        # output -> video pixel
    out = cv2.warpPerspective(frame_img, T, size, flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR,
                              borderValue=(40, 40, 40))
    for v in range(-700, 701, 100):
        x, _ = pod_to_out(0, v)
        cv2.line(out, (int(x), 0), (int(x), size[1]), (255, 255, 255) if v % 200 == 0 else (150, 150, 150), 1)
        if v % 200 == 0:
            cv2.putText(out, str(v), (int(x) + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
    for a in range(-400, 601, 100):
        _, y = pod_to_out(a, 0)
        cv2.line(out, (0, int(y)), (size[0], int(y)), (255, 255, 255) if a % 200 == 0 else (150, 150, 150), 1)
        if a % 200 == 0:
            cv2.putText(out, str(a), (2, int(y) - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
    return out


def draw_layout(out, sub, seed):
    d = lm.dump(sub, seed)[0]
    for o in d["objects"]:
        x, y = pod_to_out(o["ahead"], o["side"])
        if 0 <= x < out.shape[1] and 0 <= y < out.shape[0]:
            c = {"plant": (0, 255, 0), "item": (0, 255, 255), "teki": (0, 0, 255)}.get(o["kind"], (255, 0, 255))
            cv2.circle(out, (int(x), int(y)), 6, c, 2)
            cv2.putText(out, o["names"][0][:9], (int(x) + 7, int(y) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, c, 1)
    return out


def main():
    video, frame = sys.argv[1], int(sys.argv[2])
    crop = None if sys.argv[3] == "full" else tuple(int(v) for v in sys.argv[3].split(","))
    reg = {e["frame"]: e for e in json.load(open(sys.argv[4]))}[frame]
    H_ref = json.load(open(sys.argv[5])) if sys.argv[5] != "-" else None
    out_path = sys.argv[6]
    img = next(game_frames(video, frame, frame, crop))[1]
    out = rectify(img, reg.get("H"), H_ref, reg.get("H_pod"))
    if len(sys.argv) > 8:
        out = draw_layout(out, sys.argv[8], int(sys.argv[7], 16))
    cv2.imwrite(out_path, out)


if __name__ == "__main__":
    main()
