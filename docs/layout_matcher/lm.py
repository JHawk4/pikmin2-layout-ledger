"""Layout matcher helpers: CaveGen3 layouts in the pod's frame, the landing camera, seed scans.

The Rust side is `p2seeds/cg3/src/bin/layoutmatch.rs` (built by build.sh). Positions are in the
pod's frame: `ahead` along the pod's facing, `side` to the right as seen on screen, in game units
(a map cell is 170).

The landing camera ("READY?") is views.LANDING: 900 units back from a target 55 units behind
the pod and 40 up, 25 degrees down, 26 degrees vertical field of view, looking the way the pod
faces. project()/unproject() map between the pod frame and screen pixels with that pinhole model.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "p2seeds", "src"))

from p2seeds import rng  # noqa: E402

EXE = os.environ.get("P2SEEDS_LAYOUTMATCH",
                     os.path.join(ROOT, "data", "build", "cg3lm", "release", "layoutmatch.exe"))
CAM = {"dist": 900.0, "angle": 25.0, "fov": 26.0, "lift": 40.0, "lookAhead": -55.0}


def dump(sub: str, *seeds: int) -> list[dict]:
    out = subprocess.run([EXE, "dump", sub, *[f"{s & 0xFFFFFFFF:08X}" for s in seeds]],
                         capture_output=True, text=True, check=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def scan(sub: str, end: int, count: int, obs: list[dict], out: str) -> np.ndarray:
    """Bitmask per seed k (seed = end stepped back k draws): bit j = observation j holds."""
    op = out + ".obs.json"
    json.dump(obs, open(op, "w"), indent=1)
    subprocess.run([EXE, "scan", sub, f"{end & 0xFFFFFFFF:08X}", str(count), op, out], check=True)
    return np.fromfile(out, np.uint32)


def seed_at(end: int, k: int) -> int:
    return rng.prev_seed(end, k)


# ---- landing camera -------------------------------------------------------------------------

def _basis(cam=CAM):
    th = math.radians(cam["angle"])
    # pod frame: (ahead, side, up)
    d = np.array([math.cos(th), 0.0, -math.sin(th)])      # view direction
    u = np.array([math.sin(th), 0.0, math.cos(th)])       # screen up
    r = np.array([0.0, 1.0, 0.0])                          # screen right = pod's side axis
    target = np.array([cam["lookAhead"], 0.0, cam["lift"]])
    eye = target - d * cam["dist"]
    return eye, d, u, r


def project(ahead, side, up=0.0, w=640, h=360, cam=CAM, aspect=16 / 9):
    """Pod-frame point(s) -> screen pixels (x right, y down)."""
    eye, d, u, r = _basis(cam)
    p = np.stack(np.broadcast_arrays(np.asarray(ahead, float), np.asarray(side, float), np.asarray(up, float)), -1)
    v = p - eye
    zc, xc, yc = v @ d, v @ r, v @ u
    t = math.tan(math.radians(cam["fov"] / 2))
    sx, sy = xc / (zc * t * aspect), yc / (zc * t)
    return w / 2 * (1 + sx), h / 2 * (1 - sy)


def unproject(px, py, w=640, h=360, cam=CAM, aspect=16 / 9, up=0.0):
    """Screen pixel(s) -> the pod-frame floor point (ahead, side) at height `up`."""
    eye, d, u, r = _basis(cam)
    t = math.tan(math.radians(cam["fov"] / 2))
    sx = (np.asarray(px, float) / (w / 2) - 1) * t * aspect
    sy = (1 - np.asarray(py, float) / (h / 2)) * t
    ray = d[None] + np.atleast_1d(sx)[:, None] * r[None] + np.atleast_1d(sy)[:, None] * u[None]
    lam = (up - eye[2]) / ray[:, 2]
    q = eye[None] + lam[:, None] * ray
    return q[:, 0], q[:, 1]


# ---- the RNG window --------------------------------------------------------------------------

def window(end: int, frames: float, rate_lo: float, rate_hi: float):
    """Seeds k draws before `end` with k in [frames*rate_lo, frames*rate_hi]."""
    return int(frames * rate_lo), int(math.ceil(frames * rate_hi))
