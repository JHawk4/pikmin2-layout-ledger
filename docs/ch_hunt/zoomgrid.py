"""Crop, brighten and enlarge part of a frame with a labelled pixel grid, for reading marks.

    python docs/ch_hunt/zoomgrid.py FRAME.png X0,Y0,X1,Y1 OUT.png [--fx 2] [--gain 1.8]
Grid lines every 20 source pixels, labelled every 40 with source coordinates.
"""
import argparse

import cv2

ap = argparse.ArgumentParser()
ap.add_argument("frame"), ap.add_argument("box"), ap.add_argument("out")
ap.add_argument("--fx", type=float, default=2), ap.add_argument("--gain", type=float, default=1.8)
a = ap.parse_args()
x0, y0, x1, y1 = (int(v) for v in a.box.split(","))
c = cv2.resize(cv2.imread(a.frame)[y0:y1, x0:x1], None, fx=a.fx, fy=a.fx)
c = cv2.convertScaleAbs(c, alpha=a.gain, beta=10)
for x in range(0, x1 - x0, 20):
    X = int(x * a.fx)
    cv2.line(c, (X, 0), (X, c.shape[0]), (80, 80, 80), 1)
    if (x0 + x) % 40 == 0:
        cv2.putText(c, str(x0 + x), (X + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
for y in range(0, y1 - y0, 20):
    Y = int(y * a.fx)
    cv2.line(c, (0, Y), (c.shape[1], Y), (80, 80, 80), 1)
    if (y0 + y) % 40 == 0:
        cv2.putText(c, str(y0 + y), (2, Y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
cv2.imwrite(a.out, c)
