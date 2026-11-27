"""Turn objects marked on a 1280x720 comedown frame into layoutmatch observations in the pod frame.

    python docs/hunt/marks2obs.py SUB ZOOM TURN DX,DY "u,v,WHAT;u,v,WHAT;..." OUT.json [TOL]

WHAT: `item` (any loose treasure of SUB), `hole`, `geyser`, `plant`, `gate`, a name list
`a|b|c` (CaveGen3 internal names), or `-` for "no object at all here" (absent). Names come from
sampling 300 layouts of SUB. TOL in game units (default 80).
"""
import collections
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "layout_matcher"))
import comedown as cd  # noqa: E402
import lm  # noqa: E402


def kinds(sub, n=300):
    k = collections.defaultdict(set)
    seeds = [(i * 0x9E3779B1 + 777) & 0xFFFFFFFF for i in range(n)]
    for d in lm.dump(sub, *seeds):
        for o in d["objects"]:
            k[o["kind"]].update(o["names"])
    return k


def main():
    sub, zoom, turn, shift, marks, out = sys.argv[1:7]
    tol = float(sys.argv[7]) if len(sys.argv) > 7 else 80.0
    dx, dy = (float(v) for v in shift.split(","))
    H = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]]) @ cd.homography(1280, 720, 16 / 9, float(zoom), float(turn))
    Hi = np.linalg.inv(H)
    K = kinds(sub)
    obs = []
    for m in marks.split(";"):
        u, v, what = m.split(",", 2)
        s, a = cv2.perspectiveTransform(np.array([[[float(u), float(v)]]], np.float32), Hi)[0, 0]
        o = {"label": f"{what} at px ({u},{v})", "ahead": round(float(a)), "side": round(float(s)), "tol": tol}
        if what == "-":
            o.update(absent=True, names=[])
        elif what in K:
            o["names"] = sorted(K[what])
        else:
            o["names"] = what.split("|")
        obs.append(o)
    json.dump(obs, open(out, "w"), indent=1)
    for o in obs:
        print(o["label"], "->", o["ahead"], o["side"], len(o.get("names", [])), "names")


if __name__ == "__main__":
    main()
