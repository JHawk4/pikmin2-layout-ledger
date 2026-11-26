"""afit.py SUB OBS.json SEED...: per seed, fit a homography from pod frame to the observed pixels, assigning each
observed point to an object of an allowed type (iterated nearest assignment, starting from the OBS initial
mapping cx,cy,s). Prints RMS and per-point residuals (px)."""
import sys, json, numpy as np, cv2
sys.path.insert(0, "docs/layout_matcher"); import lm
sub, obsf = sys.argv[1], sys.argv[2]
cfg = json.load(open(obsf)); pts = cfg["points"]; cx, cy, s = cfg["init"]
img = np.float32([p["px"] for p in pts])
for sd in sys.argv[3:]:
    objs = lm.dump(sub, int(sd, 16))[0]["objects"]
    def proj(H, o):
        return cv2.perspectiveTransform(np.float32([[[o["side"], o["ahead"]]]]), H)[0, 0]
    H = np.float32([[s, 0, cx], [0, -s, cy], [0, 0, 1]])
    for it in range(6):
        src, used = [], set()
        for p in pts:
            cands = [(np.linalg.norm(proj(H, o) - p["px"]), i) for i, o in enumerate(objs) if o["names"][0] in p["names"] and i not in used]
            if not cands: src.append(None); continue
            dd, i = min(cands); used.add(i); src.append((objs[i]["side"], objs[i]["ahead"]))
        ok = [j for j, v in enumerate(src) if v is not None]
        if len(ok) < 5: break
        H2, _ = cv2.findHomography(np.float32([src[j] for j in ok]), img[ok], 0)
        if H2 is None: break
        H = H2
    res = [float(np.linalg.norm(cv2.perspectiveTransform(np.float32([[src[j]]]), H)[0, 0] - img[j])) if src[j] else 999 for j in range(len(pts))]
    print(sd, "rms %.1f" % np.sqrt(np.mean(np.square(np.minimum(res, 300)))), "max %.0f" % max(res), [round(r) for r in res])
