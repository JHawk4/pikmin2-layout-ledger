"""where.py SUB PTS.json SEED X,Y [X,Y ...]: fit SEED to the marked points, then give each extra pixel's pod-frame
position and the SEED's nearest objects there (to read what a video object should be, or spot a mismatch)."""
import json, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import lm
from simfit import fit_seed, objects
sub, ptsf, seed = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
pts = json.load(open(ptsf))["points"]
d = lm.dump(sub, seed)[0]
inl, rms, info = fit_seed(objects(d), pts, (0.5, 1.5), (1.0,), 45)
R, t = np.array(info["R"]), np.array(info["t"])
print(f"fit inliers {inl} rms {rms:.1f}")
for xy in sys.argv[4:]:
    p = np.array([float(v) for v in xy.split(",")])
    q = np.linalg.solve(R, p - t)
    side, ahead = q[0], -q[1]
    near = sorted((float(np.hypot(x - side, y - ahead)), n) for n, x, y in objects(d))[:3]
    print(f"pixel {xy}: pod frame ahead {ahead:.0f} side {side:.0f}; nearest: " + ", ".join(f"{n} {dd:.0f}" for dd, n in near))
