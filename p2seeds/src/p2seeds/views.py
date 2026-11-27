"""The camera's views of a sublevel's start, drawn on a layout render.

Landing view: what the camera shows once the pod has landed. Port of CaveGen3's web page
(web/app.js, formerly comedownShape / comedownCorners): the camera sits `dist` units back and
`angle` degrees down with a vertical field of view of `fov` degrees, aimed `lift` units above
a target `lookAhead` units ahead of the pod, looking the way the pod faces. On the floor that
is a trapezoid ahead of the pod. GameCube runs are 4:3.

Comedown view: the still, nearly top-down shot the game holds while the sublevel's title is
up (frame 0 of the floor-start cutscene s0B_cv_coursein; found in CaveGen3, JHawk4/CaveGen3#1).

render() draws a layout with both views and the pod's facing using CaveGen3's command line
(`cavegen3 <sublevel> <seed> --show landingBox,comedownBox,podAngle`). Without that program
it falls back to drawing the landing view on a Java CaveGen render (draw()).

Java CaveGen's renders are 80 px per map cell and a cell is 170 game units, from the map's corner.
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
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


def cavegen3_exe() -> Path | None:
    """CaveGen3's command line: $P2SEEDS_CAVEGEN3, else data/build/cavegen3/cavegen3.exe."""
    env = os.environ.get("P2SEEDS_CAVEGEN3")
    for p in ([Path(env)] if env else []) + [Path("data/build/cavegen3/cavegen3.exe"),
                                              Path(__file__).resolve().parents[3] / "data/build/cavegen3/cavegen3.exe"]:
        if p.is_file():
            return p
    return None


def render(cave: str, sublevel: int, layout_seed: int, out: Path, fallback: Path | None = None,
           aspect: str = "4:3") -> Path | None:
    """The layout with the comedown and landing views and the pod's facing, as a JPEG at `out`."""
    exe = cavegen3_exe()
    if exe is not None:
        with tempfile.TemporaryDirectory() as tmp:
            from .cavegen import _cg3_seed_args
            subprocess.run([str(exe), f"{cave}-{sublevel}", *_cg3_seed_args(layout_seed), "--show",
                            "landingBox,comedownBox,podAngle", "--screen", aspect, "-o", tmp],
                           check=True, capture_output=True, timeout=120)
            png = next(Path(tmp).glob("*.png"))
            cv2.imwrite(str(out), cv2.imread(str(png)), [cv2.IMWRITE_JPEG_QUALITY, 85])
        return out
    if fallback is None:
        return None
    from . import cg3
    ship = cg3.layout(cave, sublevel, layout_seed).get("ship")
    if not ship:
        return None
    tmp = out.with_suffix(".tmp.png")
    draw(fallback, ship, tmp)
    cv2.imwrite(str(out), cv2.imread(str(tmp)), [cv2.IMWRITE_JPEG_QUALITY, 82])
    tmp.unlink()
    return out
