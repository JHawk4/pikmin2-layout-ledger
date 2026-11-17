"""The camera's views of a sublevel's start, drawn on a layout render.

Landing view: what the camera shows once the pod has landed. Port of CaveGen3's web page
(web/app.js, formerly comedownShape / comedownCorners): the camera sits `dist` units back and
`angle` degrees down with a vertical field of view of `fov` degrees, aimed `lift` units above
a target `lookAhead` units ahead of the pod, looking the way the pod faces. On the floor that
is a trapezoid ahead of the pod. GameCube runs are 4:3.

Comedown view: the higher, wider view while the sublevel's title is still on screen, as the
pod comes down. Its camera is not known yet (COMEDOWN is None), so only the landing view and
the pod's facing are drawn until it is.

Java CaveGen's renders are 80 px per map cell and a cell is 170 game units, from the map's corner.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

LANDING = {"dist": 900.0, "angle": 25.0, "fov": 26.0, "lift": 40.0, "lookAhead": -55.0}
COMEDOWN: dict | None = None
PX_PER_UNIT = 80.0 / 170.0
LANDING_BGR = (40, 180, 255)       # orange
COMEDOWN_BGR = (255, 200, 60)      # light blue


def shape(camera: dict = LANDING, aspect: float = 4 / 3) -> dict:
    rad = math.pi / 180
    height = camera["dist"] * math.sin(camera["angle"] * rad) + camera["lift"]
    back = camera["dist"] * math.cos(camera["angle"] * rad) - camera["lookAhead"]
    half = camera["fov"] / 2 * rad
    tan_side = math.tan(half) * aspect

    def edge(pitch):
        if pitch >= math.pi / 2:                   # looking straight down or past: the edge is behind
            ground = -height * math.tan(pitch - math.pi / 2)
        else:
            ground = height / math.tan(pitch)
        depth = math.hypot(ground, height) * math.cos(half)
        return ground - back, depth * tan_side

    near, near_half = edge(camera["angle"] * rad + half)
    far, far_half = edge(camera["angle"] * rad - half)
    return {"near": near, "far": far, "nearHalf": near_half, "farHalf": far_half}


def corners(x: float, z: float, degrees: float, s: dict | None = None) -> list[tuple[float, float]]:
    s = s or shape()
    a = math.radians(degrees)
    f = (math.sin(a), math.cos(a))
    r = (-f[1], f[0])

    def at(ahead, side):
        return (x + f[0] * ahead + r[0] * side, z + f[1] * ahead + r[1] * side)
    return [at(s["near"], -s["nearHalf"]), at(s["near"], s["nearHalf"]), at(s["far"], s["farHalf"]), at(s["far"], -s["farHalf"])]


def _box(img: np.ndarray, ship: dict, camera: dict, bgr, aspect: float) -> np.ndarray:
    pts = np.array([[x * PX_PER_UNIT, z * PX_PER_UNIT] for x, z in corners(ship["x"], ship["z"], ship["angle"], shape(camera, aspect))],
                   np.int32)
    overlay = img.copy()
    cv2.fillPoly(overlay, [pts], bgr)
    img = cv2.addWeighted(overlay, 0.15, img, 0.85, 0)
    cv2.polylines(img, [pts], True, bgr, 4, cv2.LINE_AA)
    return img


def draw(render: Path, ship: dict, out: Path, aspect: float = 4 / 3) -> Path:
    """Copy `render` (a Java CaveGen layout PNG) to `out` with the comedown view (when its
    camera is known), the landing view and the pod's facing drawn on it."""
    img = cv2.imread(str(render))
    if COMEDOWN is not None:
        img = _box(img, ship, COMEDOWN, COMEDOWN_BGR, aspect)
    img = _box(img, ship, LANDING, LANDING_BGR, aspect)
    cx, cz = ship["x"] * PX_PER_UNIT, ship["z"] * PX_PER_UNIT
    a = math.radians(ship["angle"])
    tip = (cx + math.sin(a) * 60, cz + math.cos(a) * 60)
    cv2.circle(img, (int(cx), int(cz)), 10, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.arrowedLine(img, (int(cx), int(cz)), (int(tip[0]), int(tip[1])), (255, 255, 255), 4, cv2.LINE_AA, tipLength=0.35)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    return out
