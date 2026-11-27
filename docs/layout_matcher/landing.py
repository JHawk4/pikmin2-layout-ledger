"""The "READY?" landing view (CaveGen3 render.rs LANDING_CAMERA, Olimar without L: looking toward
world heading 110°, aimed at the captain, who lands look_ahead units ahead of the pod) as a
homography from world (x, z) to 1280x720 pixels, and a tool drawing a sublevel's spots on a READY
frame.

    python docs/layout_matcher/landing.py CH FRAME SEED OUT.jpg [HEADING] [SPOTS|seed]

SEED gives the pod (fixed on single-room stages). POD_PX=u,v (env) moves the view so the pod is at
that pixel. With "seed" as the last argument the seed's own
objects are drawn instead of the spots list.
"""
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lm  # noqa: E402

DIST, ANGLE, FOV, LIFT, LOOK = 900.0, 25.0, 26.0, 40.0, -55.0


def shape(aspect):
    rad = math.pi / 180
    height = DIST * math.sin(ANGLE * rad) + LIFT
    back = DIST * math.cos(ANGLE * rad) - LOOK
    half = FOV / 2 * rad
    tan_side = math.tan(half) * aspect

    def edge(p):
        ground = height / math.tan(p)
        depth = math.hypot(ground, height) * math.cos(half)
        return ground - back, depth * tan_side
    near, nh = edge(ANGLE * rad + half)
    far, fh = edge(ANGLE * rad - half)
    return [(near, -nh), (near, nh), (far, fh), (far, -fh)]


def homography(pod_x, pod_z, pod_deg, heading=110.0, aspect=16 / 9, w=1280, h=720):
    a, hh = math.radians(pod_deg), math.radians(heading)
    qx, qz = pod_x + LOOK * (math.sin(a) - math.sin(hh)), pod_z + LOOK * (math.cos(a) - math.cos(hh))
    f = (math.sin(hh), math.cos(hh))
    r = (-f[1], f[0])
    world = [(qx + f[0] * ah + r[0] * sd, qz + f[1] * ah + r[1] * sd) for ah, sd in shape(aspect)]
    screen = [(0, h), (w, h), (w, 0), (0, 0)]
    return cv2.getPerspectiveTransform(np.array(world, np.float32), np.array(screen, np.float32))


def homography_pod_at(pod_x, pod_z, pod_deg, pod_px, heading=110.0, aspect=16 / 9):
    """The landing homography moved along the floor so that the pod lands on pixel pod_px (the
    camera aims at the captain, whose start in Challenge Mode isn't next to the pod)."""
    H0 = homography(pod_x, pod_z, pod_deg, heading, aspect)
    W = cv2.perspectiveTransform(np.array([[pod_px]], np.float32), np.linalg.inv(H0))[0, 0]
    sx, sz = pod_x - W[0], pod_z - W[1]
    T = np.array([[1, 0, -sx], [0, 1, -sz], [0, 0, 1]], np.float64)
    return H0 @ T


def pod_to_world(pod, ahead, side):
    t = math.radians(pod["angle"])
    f, r = (math.sin(t), math.cos(t)), (-math.cos(t), math.sin(t))
    return pod["x"] + side * r[0] + ahead * f[0], pod["z"] + side * r[1] + ahead * f[1]


def main():
    ch, n, seed, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3], 16), sys.argv[4]
    heading = float(sys.argv[5]) if len(sys.argv) > 5 else 110.0
    mode = sys.argv[6] if len(sys.argv) > 6 else "spots"
    from inventory import WR
    from wr_comedown import INV, crop_for
    e = next(x for x in json.load(open(INV)) if x["ch"] == ch)
    video = os.path.join(WR, e["video"])
    x, y, w, h = crop_for(video)
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    img = cv2.resize(cap.read()[1][y:y + h, x:x + w], (1280, 720), interpolation=cv2.INTER_CUBIC)
    d = lm.dump(f"CH{ch}-1", seed)[0]
    pod = d["pod"]
    if os.environ.get("POD_PX"):
        H = homography_pod_at(pod["x"], pod["z"], pod["angle"], [float(v) for v in os.environ["POD_PX"].split(",")], heading)
    else:
        H = homography(pod["x"], pod["z"], pod["angle"], heading)
    if mode == "seed":
        pts = [((o["x"], o["z"]), o["names"][0], (0, 255, 255) if o["kind"] == "item" else (255, 0, 255)) for o in d["objects"]]
    else:
        spots = json.load(open(os.path.join(lm.ROOT, "data", "lm", f"spots_CH{ch}-1.json")))
        pts = [(pod_to_world(pod, s["ahead"], s["side"]), str(i), (0, 255, 255)) for i, s in enumerate(spots)]
    pts.append(((pod["x"], pod["z"]), "pod", (0, 0, 255)))
    for (X, Z), lab, col in pts:
        p = cv2.perspectiveTransform(np.array([[[X, Z]]], np.float32), H)[0, 0]
        if -50 < p[0] < 1330 and -50 < p[1] < 770:
            cv2.circle(img, (int(p[0]), int(p[1])), 8, col, 1)
            cv2.putText(img, lab, (int(p[0]) + 8, int(p[1]) - 4), 0, 0.45, col, 1)
    cv2.imwrite(out, img)


if __name__ == "__main__":
    main()
