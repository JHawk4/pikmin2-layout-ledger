import sys, json, cv2, numpy as np
sys.path.insert(0, __import__("os").path.dirname(__file__))
import divefit2 as F
from divesim import dive_params, rng
geom = json.loads(sys.argv[1]); off = int(sys.argv[2]); out = sys.argv[3]
d = dive_params(rng.next_seed(0x04047550, off))
tiles = []
for fr in range(5895, 5911, 2):
    f = F.frame(fr).astype(np.uint8)[30:150, 290:540].copy()
    for g, key, col in zip(F.GROUPS, ('red', 'white'), ((0, 255, 255), (255, 255, 0))):
        u0, v0, hc = geom[key]
        for i, p in enumerate(d[g['c']][:5]):
            ox, oy = F.offsets(p, fr - geom['f0'], hc)
            if fr - geom['f0'] <= 0 or p['T0'] + 0.15 * (fr - geom['f0']) < 0: continue
            u, v = u0 + geom['sx'] * ox - 290, v0 + geom['sy'] * oy - 30
            cv2.circle(f, (int(round(u)), int(round(v))), 2, col, -1)
    f = cv2.resize(f, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    cv2.putText(f, str(fr), (4, 18), 0, 0.6, (0, 255, 255), 2); tiles.append(f)
cv2.imwrite(out, np.vstack([np.hstack(tiles[k:k + 4]) for k in range(0, 8, 4)]), [cv2.IMWRITE_JPEG_QUALITY, 85])
