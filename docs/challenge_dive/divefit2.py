import sys, math, cv2, numpy as np
from scipy.optimize import minimize
sys.path.insert(0, __import__("os").path.dirname(__file__))
from divesim import dive_params, rng
VID = "data/challenge/videos/cmal04_tcbtrio_wiiu_usa.mp4"
cap = cv2.VideoCapture(VID)
def frame(i):
    cap.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = cap.read(); return f.astype(np.float32)
BG = frame(5930)
def obsimg(i):
    d = np.abs(frame(i) - BG).sum(2); return np.clip((d - 60) / 150, 0, 1)
# groups: colour index, crop (x0,y0,x1,y1), frames, template frame+point
GROUPS = [dict(c=0, crop=(300, 40, 400, 130), frames=range(5893, 5903), tpl=(5904, 341, 79)),
          dict(c=3, crop=(430, 50, 530, 140), frames=range(5900, 5912), tpl=(5908, 490, 108))]
for g in GROUPS:
    x0, y0, x1, y1 = g['crop']
    g['obs'] = {i: cv2.GaussianBlur(obsimg(i)[y0:y1, x0:x1], (3, 3), 0) for i in g['frames']}
    fr, px, py = g['tpl']; o = obsimg(fr)
    m = (o > 0.4).astype(np.uint8); n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    k = min(range(1, n), key=lambda k: (cen[k][0] - px) ** 2 + (cen[k][1] - py) ** 2)
    xa, ya, w, h = st[k][:4]; patch = o[ya:ya + h, xa:xa + w] * (lab[ya:ya + h, xa:xa + w] == k)
    g['tpl_img'] = cv2.GaussianBlur(patch.astype(np.float32), (3, 3), 0)
    g['tc'] = (cen[k][0] - xa, cen[k][1] - ya)

def offsets(p, n, climb):
    t = p['T0'] + 0.15 * n
    if n <= 0 or t < 0: return (0.0, 0.0)
    if t <= math.pi / 2: return (-p['dx'] * math.sin(t), -abs(math.sin(2 * t) * p['dy']))
    k = int((t - math.pi / 2) / 0.15) + 1   # updates spent climbing
    return (-p['dx'], -min(12.0 * k, climb + 12.0))

def render(g, pts):
    x0, y0, x1, y1 = g['crop']; W, H = x1 - x0, y1 - y0; img = np.zeros((H, W), np.float32)
    tcx, tcy = g['tc']
    for (u, v) in pts:
        M = np.float32([[1, 0, u - x0 - tcx], [0, 1, v - y0 - tcy]])
        img = np.maximum(img, cv2.warpAffine(g['tpl_img'], M, (W, H)))
    return img

def loss(th, d, nvis, f0):
    sx, sy, ur, vr, hr, uw, vw, hw = th
    err = 0.0
    for g, (u0, v0, hc) in zip(GROUPS, ((ur, vr, hr), (uw, vw, hw))):
        ps = d[g['c']][:nvis]
        for fr, o in g['obs'].items():
            pts = []
            for p in ps:
                ox, oy = offsets(p, fr - f0, hc); pts.append((u0 + sx * ox, v0 + sy * oy))
            err += float(((render(g, pts) - o) ** 2).sum())
    return err

def fit(d, nvis=5):
    best = None
    for f0 in range(5887, 5892):
        for sx0 in (0.5, 0.65):
            th0 = [sx0, 0.6, 345, 95, 20, 480, 115, 20]
            r = minimize(loss, th0, args=(d, nvis, f0), method="Powell", bounds=[(0.45, 1.1), (0.3, 1.0), (320, 370), (75, 115), (0, 60), (450, 500), (95, 135), (0, 60)], options=dict(maxiter=3000, xtol=0.05, ftol=1e-4))
            if best is None or r.fun < best[0]: best = (r.fun, f0, r.x)
    return best

if __name__ == "__main__":
    base = 0x04047550
    if sys.argv[1] == "offsets":
        offs = [int(a) for a in sys.argv[2].split(",")]
        for off in offs:
            b = fit(dive_params(rng.next_seed(base, off)))
            print(off, round(b[0], 1), b[1], np.round(b[2], 2), flush=True)
    else:
        rs = np.random.default_rng(int(sys.argv[3]))
        for k in range(int(sys.argv[2])):
            s = int(rs.integers(0, 2 ** 31)); b = fit(dive_params(s))
            print("rand", hex(s), round(b[0], 1), b[1], np.round(b[2], 2), flush=True)
