"""Side-by-side check images for the WR seeds: the CaveGen3 render of floor 1 next to frames of the
video's first floor (from the dive's end onwards).

    python docs/challenge_dive/wr_gallery.py OUTDIR [CH ...]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WR = os.path.join(ROOT, "data", "challenge", "wr")
EXE = os.environ.get("P2SEEDS_CAVEGEN3") or os.path.join(ROOT, "..", "..", "..", "data", "build", "cavegen3", "cavegen3.exe")


def main():
    out = sys.argv[1]
    want = [int(a) for a in sys.argv[2:]]
    os.makedirs(out, exist_ok=True)
    for ch in range(1, 31):
        if want and ch not in want:
            continue
        p = os.path.join(WR, "dives", f"wr_{ch:02d}.json")
        if not os.path.exists(p):
            continue
        r = json.load(open(p))
        if not r.get("ok"):
            continue
        lay = r["candidates"][0]["layout_seed"] & 0x7FFFFFFF
        tmp = os.path.join(out, "_cg")
        subprocess.run([EXE, f"CH{ch}-1", f"{lay:08X}", "-o", tmp], capture_output=True)
        render = cv2.imread(os.path.join(tmp, f"CH{ch}-1_{lay:08X}.png"))
        cap = cv2.VideoCapture(os.path.join(WR, r["video"]))
        start = r["visit"][1] + 150
        frames = []
        for k in range(4):
            cap.set(cv2.CAP_PROP_POS_FRAMES, start + k * 150)
            ok, f = cap.read()
            if ok:
                frames.append(f)
        h = 360
        render = cv2.resize(render, (int(render.shape[1] * h / render.shape[0]), h))
        cv2.putText(render, f"CH{ch}-1 {lay:08X}", (6, 20), 0, 0.6, (0, 255, 255), 2)
        row = np.hstack([render] + [cv2.resize(f, (int(f.shape[1] * h / f.shape[0]), h)) for f in frames[:3]])
        cv2.imwrite(os.path.join(out, f"wr_{ch:02d}_CH{ch}-1_{lay:08X}.jpg"), row, [cv2.IMWRITE_JPEG_QUALITY, 80])
        print(ch, f"{lay:08X}")


if __name__ == "__main__":
    main()
