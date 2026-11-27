"""ovl.py SUB FRAME.jpg OUT.jpg CX CY SCALE SEED... : draw each seed's objects on a top-down gameplay frame
(screen up = pod's ahead, right = side; pod at pixel (CX,CY) of the 640x360 frame, SCALE px/unit)."""
import sys, cv2, numpy as np
sys.path.insert(0, "docs/layout_matcher"); import lm
sub, fr, out, cx, cy, s = sys.argv[1], sys.argv[2], sys.argv[3], *map(float, sys.argv[4:7])
seeds = sys.argv[7:]
base = cv2.resize(cv2.imread(fr), (640, 360))
panels = []
for sd in seeds:
    im = cv2.resize(base, (1280, 720)).copy()
    d = lm.dump(sub, int(sd, 16))[0]
    for o in d["objects"]:
        x, y = cx + s * o["side"], cy - s * o["ahead"]
        p = (int(2 * x), int(2 * y))
        cv2.circle(im, p, 10, (0, 255, 255), 2)
        cv2.putText(im, o["names"][0][:10], (p[0] + 12, p[1] + 4), 0, 0.5, (0, 255, 255), 1)
    cv2.putText(im, sd, (10, 700), 0, 1, (0, 0, 255), 2)
    panels.append(im)
cv2.imwrite(out, np.vstack(panels) if len(panels) < 3 else np.vstack([np.hstack(panels[i:i+2]) if i+1 < len(panels) else np.hstack([panels[i], np.zeros_like(panels[i])]) for i in range(0, len(panels), 2)]))
