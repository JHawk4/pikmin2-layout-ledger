"""Help mark a calibration frame: the frame with a labelled pixel grid, next to the known layout's
objects as a top-down pod-frame map (pod at the centre, facing up, grid every 100 units).

    python docs/layout_matcher/calib_view.py VIDEO FRAME CROP|full SUB SEED OUT.jpg [RADIUS [HEADING]]

With HEADING (degrees), the map's up is that world heading (the landing camera looks toward 110),
centred on the pod.

Read off pixel positions of 6-9 objects you can identify in both, write them as
[{"what", "ahead", "side", "px", "py"}] (ahead/side from the map, or exactly from
`lm.dump`), and fit with calib.py. Pixels are in the 1280x720 game image.
"""
import sys

import cv2
import numpy as np

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
import lm  # noqa: E402
from register import game_frames  # noqa: E402

COL = {"plant": (0, 200, 0), "item": (0, 220, 255), "teki": (0, 0, 255), "geyser": (255, 0, 255),
       "hole": (255, 255, 255), "gate": (255, 128, 0), "capteki": (0, 128, 255)}


def grid_frame(img):
    g = img.copy()
    for x in range(0, 1280, 80):
        cv2.line(g, (x, 0), (x, 719), (255, 255, 255), 1)
        cv2.putText(g, str(x), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    for y in range(0, 720, 80):
        cv2.line(g, (0, y), (1279, y), (255, 255, 255), 1)
        cv2.putText(g, str(y), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    return g


def heading_frame(d, heading):
    """Objects' (ahead, side) re-expressed with `ahead` along a world heading (degrees) instead
    of the pod's facing; heading None keeps the pod frame."""
    if heading is None:
        return d
    import math
    t = math.radians(heading)
    f, r = (math.sin(t), math.cos(t)), (-math.cos(t), math.sin(t))
    px, pz = d["pod"]["x"], d["pod"]["z"]
    for o in d["objects"]:
        dx, dz = o["x"] - px, o["z"] - pz
        o["ahead"], o["side"] = dx * f[0] + dz * f[1], dx * r[0] + dz * r[1]
    return d


def pod_map(sub, seed, radius=900, size=720, heading=None):
    d = heading_frame(lm.dump(sub, seed)[0], heading)
    s = size / (2 * radius)
    m = np.full((size, size, 3), 30, np.uint8)
    to = lambda a, sd: (int(size / 2 + sd * s), int(size / 2 - a * s))  # noqa: E731
    for v in range(-radius // 100 * 100, radius + 1, 100):
        x, _ = to(0, v)
        _, y = to(v, 0)
        c = (120, 120, 120) if v else (220, 220, 220)
        cv2.line(m, (x, 0), (x, size), c, 1)
        cv2.line(m, (0, y), (size, y), c, 1)
        if v % 200 == 0:
            cv2.putText(m, str(v), (x + 2, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1)
            cv2.putText(m, str(v), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1)
    cv2.drawMarker(m, to(0, 0), (255, 255, 255), cv2.MARKER_TRIANGLE_UP, 16, 2)
    for o in d["objects"]:
        if abs(o["ahead"]) > radius or abs(o["side"]) > radius:
            continue
        p = to(o["ahead"], o["side"])
        c = COL.get(o["kind"], (200, 200, 200))
        cv2.circle(m, p, 4, c, -1)
        cv2.putText(m, f"{o['names'][-1 if o['kind'] == 'teki' else 0][:10]} {o['ahead']:.0f},{o['side']:.0f}",
                    (p[0] + 5, p[1] + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, c, 1)
    return m


def main():
    video, frame, crop, sub, seed, out = sys.argv[1:7]
    radius = int(sys.argv[7]) if len(sys.argv) > 7 else 900
    heading = float(sys.argv[8]) if len(sys.argv) > 8 else None
    crop = None if crop == "full" else tuple(int(v) for v in crop.split(","))
    img = next(game_frames(video, int(frame), int(frame), crop))[1]
    cv2.imwrite(out, np.hstack([grid_frame(img), pod_map(sub, int(seed, 16), radius, heading=heading)]))


if __name__ == "__main__":
    main()
