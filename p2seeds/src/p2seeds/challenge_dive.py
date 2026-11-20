"""Read the RNG from the Challenge Mode stage-select "dive" (Pikmin jumping into the chosen stage).

Decomp: plugProjectMorimuraU/challengeSelect2D.cpp, TChallengePiki::jumpStart / update / draw.
On confirming a stage the game makes 5 colours x 50 Pikmin x 4 randFloat() draws (1000 in all),
colour order red, yellow, blue, white, purple; Pikmin i of colour c gets
    T0 = 0.1*r0 - 0.1*i - 0.5*c        launch timer (advances 0.15 per frame, starts at T >= 0)
    dx = 30*r1, negated if r2 > 0.5    sideways hop: x = X0 - dx*sin(T) while T <= pi/2
    dy = 15 + 10*r3                    hop height:   y = Y0 - |dy*sin(2T)|
then it climbs 12 units/frame up to y = 100, jumps in an arc (x linear to the panel +-8, y - 70 sin)
over T in [0, pi] and falls 12/frame onto the panel. Only the stage's starting Pikmin of each colour
are moved and drawn (at most 50); the not-yet-launched ones are drawn at the origin.
The state after the dive's 1000th draw is the floor-1 layout seed.

Coordinates here are video pixels. A layout ("geometry") maps the game's 2D units onto them:
sx, sy (px per unit), each colour's origin, the video row of y = 100 (top of the climb) and the
panel the Pikmin jump to.
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import rng

M31 = 1 << 31
COLOURS = ("red", "yellow", "blue", "white", "purple")          # dive order
# CaveGen3 challenge_stages.csv colour index (game enum): blue 0, red 1, yellow 2, purple 3, white 4
_GAME_INDEX = {"red": 1, "yellow": 2, "blue": 0, "white": 4, "purple": 3}
TIMER_SPEED, MOVE, ARC = 0.15, 12.0, 70.0


def _stages_csv() -> str:
    env = os.environ.get("P2SEEDS_CAVEGEN3_DATA")
    if env:
        return os.path.join(env, "resources", "jhawk_judge", "challenge_stages.csv")
    here = os.path.dirname(os.path.abspath(__file__))
    for up in range(2, 9):
        root = os.path.abspath(os.path.join(here, *([".."] * up)))
        p = os.path.join(root, "cavegen3", "data", "resources", "jhawk_judge", "challenge_stages.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("challenge_stages.csv (CaveGen3) not found; set P2SEEDS_CAVEGEN3_DATA")


def stage_counts(ch: int) -> list[int]:
    """Starting Pikmin per dive colour (red, yellow, blue, white, purple) for challenge stage `ch` (1..30)."""
    with open(_stages_csv(), encoding="utf8") as f:
        for row in csv.reader(f):
            if row and row[0] == f"CH{ch}":
                v = [int(x) for x in row[1:22]]
                return [sum(v[3 * _GAME_INDEX[c]: 3 * _GAME_INDEX[c] + 3]) for c in COLOURS]
    raise KeyError(ch)


def rand_value(state: int) -> float:
    return ((state >> 16) & 0x7FFF) / 32768.0


@dataclass
class Piki:
    T0: float
    dx: float
    dy: float


def dive_params(first_state: int, counts=(50,) * 5) -> list[list[Piki]]:
    """first_state: the RNG state whose value is the dive's first draw."""
    out = []
    a1, c1 = rng.jump(1)
    s = first_state
    for c in range(5):
        col = []
        for i in range(50):
            r = []
            for _ in range(4):
                r.append(rand_value(s))
                s = (a1 * s + c1) & 0xFFFFFFFF
            if i < counts[c]:
                dx = 30 * r[1] * (-1 if r[2] > 0.5 else 1)
                col.append(Piki(0.1 * r[0] - 0.1 * i - 0.5 * c, dx, 15 + 10 * r[3]))
        out.append(col)
    return out


def layout_seed(first_state: int) -> int:
    """Floor-1 layout seed: the state after the dive's 1000th draw."""
    return rng.next_seed(first_state, 999)


@dataclass
class Geometry:
    sx: float
    sy: float
    origins: dict                 # colour -> (u, v) in video px
    v100: float                   # video row of game y = 100 (top of the climb)
    goal: tuple                   # (u, v) of the panel the Pikmin jump to
    f0: float = 0.0               # video frame of the first update after jumpStart

    def copy(self, **kw):
        g = Geometry(self.sx, self.sy, dict(self.origins), self.v100, tuple(self.goal), self.f0)
        for k, v in kw.items():
            setattr(g, k, v)
        return g


def trajectory(p: Piki, i: int, origin, g: Geometry, n_updates: int):
    """Video positions after 0..n_updates-1 updates; None when not drawn (landed)."""
    u0, v0 = origin
    t = p.T0
    state = 0
    u, v = u0, v0
    ui = vi = 0.0
    out = []
    calc = {0: -8.0, 1: 8.0}.get(i % 3, 0.0) * g.sx
    for _ in range(n_updates):
        t += TIMER_SPEED
        if state == 0:
            if t >= 0:
                if t > math.pi / 2:
                    state = 3
                u = u0 - g.sx * p.dx * math.sin(t)
                v = v0 - g.sy * abs(math.sin(2 * t) * p.dy)
        elif state == 3:
            if v > g.v100:
                v -= MOVE * g.sy
            else:
                state, ui, vi, t = 4, u, v, 0.0
        elif state == 4:
            if t > math.pi:
                state, t = 5, math.pi
            u = ui + t * (g.goal[0] - ui + calc) / math.pi
            v = vi - ARC * g.sy * math.sin(t)
        elif state == 5:
            if v < g.goal[1] - 40 * g.sy:
                v += MOVE * g.sy
            else:
                state = 6
        out.append(None if state == 6 else (u, v))
    return out


class DiveVideo:
    """Background-subtracted frames of one dive and a sprite template."""

    def __init__(self, path: str, first: int, last: int, bg_frame: int | None, region, template=None, blur=3,
                 frames=None, scale: float = 1.0):
        """bg_frame None: per-pixel median of the window (each pixel shows a Pikmin only briefly).
        frames: preloaded {frame: BGR image} (full video frames) to avoid decoding twice.
        scale: template scale (reference template is for 640x360 Wii captures)."""
        self.path, self.first, self.last = path, first, last
        x0, y0, x1, y1 = region
        self.region = region
        raw = {}
        if frames is not None:
            raw = {fr: frames[fr][y0:y1, x0:x1].astype(np.float32) for fr in range(first, last + 1) if fr in frames}
        else:
            cap = cv2.VideoCapture(path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, first)
            for fr in range(first, last + 1):
                ok, f = cap.read()
                if not ok:
                    break
                raw[fr] = f[y0:y1, x0:x1].astype(np.float32)
        if bg_frame is None:
            bg = np.median(np.stack(list(raw.values())), axis=0)
        else:
            cap = cv2.VideoCapture(path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, bg_frame)
            ok, b = cap.read()
            bg = b.astype(np.float32)[y0:y1, x0:x1]
        self.bg = bg
        self.obs = {}
        for fr, f in raw.items():
            d = np.abs(f - bg).sum(2)
            o = np.clip((d - 60) / 150, 0, 1)
            self.obs[fr] = cv2.GaussianBlur(o, (blur, blur), 0) if blur else o
        t = template if template is not None else default_template()
        if scale != 1.0:
            t = cv2.resize(t, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        self.template = t
        self.renderer = Renderer(self.template, region)


_TEMPLATE = None


def default_template() -> np.ndarray:
    """A Pikmin sprite's background-difference blob (red Pikmin from the reference video, 640x360)."""
    global _TEMPLATE
    if _TEMPLATE is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "challenge_dive_template.npy")
        _TEMPLATE = np.load(p).astype(np.float32)
    return _TEMPLATE


def flatten(params):
    """Per-Pikmin arrays (T0, dx, dy, colour, index) for the vectorised simulation."""
    rows = [(p.T0, p.dx, p.dy, c, i) for c, col in enumerate(params) for i, p in enumerate(col)]
    if not rows:
        return np.zeros((0, 5))
    return np.array(rows, dtype=np.float64)


def simulate(flat: np.ndarray, g: Geometry, n_updates: int):
    """Video positions of every Pikmin after 1..n_updates updates: arrays (n_updates, P), NaN = not drawn.
    Same state machine as trajectory(), vectorised over Pikmin."""
    P = len(flat)
    T0, dx, dy, col, idx = (flat[:, k] for k in range(5))
    org = np.array([g.origins[COLOURS[int(c)]] for c in col]).reshape(P, 2)
    u0, v0 = org[:, 0].copy(), org[:, 1].copy()
    t = T0.copy()
    state = np.zeros(P, np.int8)
    u, v = u0.copy(), v0.copy()
    ui, vi = np.zeros(P), np.zeros(P)
    calc = np.where(idx % 3 == 0, -8.0, np.where(idx % 3 == 1, 8.0, 0.0)) * g.sx
    U = np.full((n_updates, P), np.nan)
    V = np.full((n_updates, P), np.nan)
    half = math.pi / 2
    for n in range(n_updates):
        t += TIMER_SPEED
        st = state.copy()
        # 0: standby / hop
        m0 = (st == 0) & (t >= 0)
        u = np.where(m0, u0 - g.sx * dx * np.sin(t), u)
        v = np.where(m0, v0 - g.sy * np.abs(np.sin(2 * t) * dy), v)
        state = np.where(m0 & (t > half), 3, state)
        # 3: climb to the top, then start the jump
        m3 = st == 3
        up = m3 & (v > g.v100)
        top = m3 & ~up
        v = np.where(up, v - MOVE * g.sy, v)
        ui = np.where(top, u, ui)
        vi = np.where(top, v, vi)
        t = np.where(top, 0.0, t)
        state = np.where(top, 4, state)
        # 4: jump arc
        m4 = st == 4
        over = m4 & (t > math.pi)
        t = np.where(over, math.pi, t)
        u = np.where(m4, ui + t * (g.goal[0] - ui + calc) / math.pi, u)
        v = np.where(m4, vi - ARC * g.sy * np.sin(t), v)
        state = np.where(over, 5, state)
        # 5: fall onto the panel
        m5 = st == 5
        fall = m5 & (v < g.goal[1] - 40 * g.sy)
        v = np.where(fall, v + MOVE * g.sy, v)
        state = np.where(m5 & ~fall, 6, state)
        drawn = state != 6
        U[n] = np.where(drawn, u, np.nan)
        V[n] = np.where(drawn, v, np.nan)
    return U, V


class Renderer:
    """Fast sprite pasting with a bank of sub-pixel shifted templates."""

    def __init__(self, template: np.ndarray, region, sub: int = 4):
        x0, y0, x1, y1 = region
        self.x0, self.y0, self.W, self.H = x0, y0, x1 - x0, y1 - y0
        self.sub = sub
        th, tw = template.shape
        self.th, self.tw = th + 2, tw + 2
        self.cx, self.cy = tw / 2.0 + 1, th * 0.5 + 1
        base = np.zeros((self.th, self.tw), np.float32)
        base[1:-1, 1:-1] = template
        self.bank = {}
        for a in range(sub):
            for b in range(sub):
                M = np.float32([[1, 0, a / sub], [0, 1, b / sub]])
                self.bank[a, b] = cv2.warpAffine(base, M, (self.tw, self.th))

    def render(self, us, vs) -> np.ndarray:
        img = np.zeros((self.H, self.W), np.float32)
        for u, v in zip(us, vs):
            if u != u:
                continue
            x = u - self.x0 - self.cx
            y = v - self.y0 - self.cy
            ix, iy = math.floor(x), math.floor(y)
            a = min(self.sub - 1, int((x - ix) * self.sub))
            b = min(self.sub - 1, int((y - iy) * self.sub))
            t = self.bank[a, b]
            xa, ya = max(ix, 0), max(iy, 0)
            xb, yb = min(ix + self.tw, self.W), min(iy + self.th, self.H)
            if xa >= xb or ya >= yb:
                continue
            np.maximum(img[ya:yb, xa:xb], t[ya - iy:yb - iy, xa - ix:xb - ix], out=img[ya:yb, xa:xb])
        return img


def predicted_frames(flat, g: Geometry, frames):
    """{frame: (us, vs)} for the given video frames. Pikmin still waiting sit at their origin."""
    nmax = int(max(frames) - g.f0) + 2
    if nmax <= 0:
        nmax = 1
    U, V = simulate(flat, g, nmax)
    out = {}
    org = np.array([g.origins[COLOURS[int(c)]] for c in flat[:, 3]]).reshape(len(flat), 2)
    for fr in frames:
        n = int(math.floor(fr - g.f0))          # updates done by this frame
        if n <= 0:
            out[fr] = (org[:, 0], org[:, 1])
        else:
            out[fr] = (U[min(n, nmax) - 1], V[min(n, nmax) - 1])
    return out


def image_loss(dv: "DiveVideo", flat, g: Geometry, frames=None, renderer: Renderer | None = None) -> float:
    frames = list(frames or dv.obs)
    rd = renderer or dv.renderer
    pf = predicted_frames(flat, g, frames)
    err = 0.0
    for fr in frames:
        r = rd.render(*pf[fr])
        err += float(((r - dv.obs[fr]) ** 2).sum())
    return err


# ---------------------------------------------------------------- seed-free measurement

def _flat_from(est, counts):
    rows = []
    for c in range(5):
        for i in range(counts[c] if c < len(counts) else 0):
            if i >= 50:
                break
            r0, dx, dy = est[(c, i)]
            rows.append((0.1 * r0 - 0.1 * i - 0.5 * c, dx, dy, c, i))
    return np.array(rows, dtype=np.float64).reshape(-1, 5)


def measure(dv: DiveVideo, counts, g: Geometry, frames, sweeps: int = 3, max_per_colour: int = 50,
            progress=None):
    """Fit every visible Pikmin's (launch jitter r0, signed sideways dx, hop height dy) to the video
    with the geometry fixed. Coordinate sweeps: each Pikmin on a dx grid with others held fixed.
    Returns {(colour, i): dict(dx, lo, hi, r0, dy, curve)} where [lo, hi] bounds dx."""
    counts = [min(k, 50, max_per_colour) for k in counts]
    est = {(c, i): (0.5, 0.0, 20.0) for c in range(5) for i in range(counts[c])}
    keys = sorted(est, key=lambda k: -(0.1 * k[1] + 0.5 * k[0]))   # launch order
    frames = sorted(frames)
    # frames in which Pikmin (c, i) hops or climbs: launch ~ (0.1 i + 0.5 c)/0.15 updates after f0
    def window(k):
        c, i = k
        n0 = (0.1 * i + 0.5 * c) / TIMER_SPEED
        a, b = g.f0 + n0 - 1, g.f0 + n0 + 10.5 + 14
        w = [f for f in frames if a <= f <= b]
        return w or frames
    out = {}
    grid_r0 = (0.15, 0.5, 0.85)
    grid_dy = (17.0, 20.0, 23.0)
    for sweep in range(sweeps):
        for k in keys:
            w = window(k)
            best = None
            curve = {}
            dxs = np.arange(-30, 30.01, 1.0) if sweep == 0 or k not in out else \
                np.arange(max(-30, est[k][1] - 4), min(30, est[k][1] + 4) + 0.01, 0.5)
            for dxv in dxs:
                for r0 in grid_r0:
                    for dyv in grid_dy:
                        est[k] = (r0, float(dxv), dyv)
                        l = image_loss(dv, _flat_from(est, counts), g, w)
                        if best is None or l < best[0]:
                            best = (l, r0, float(dxv), dyv)
                        curve[float(dxv)] = min(curve.get(float(dxv), 1e18), l)
            est[k] = best[1:]
            if sweep == sweeps - 1 or True:
                xs = np.array(sorted(curve))
                ys = np.array([curve[x] for x in xs])
                thr = best[0] + max(3.0, 0.03 * best[0])
                ok = xs[ys <= thr]
                out[k] = dict(r0=best[1], dx=best[2], dy=best[3], lo=float(ok.min()), hi=float(ok.max()),
                              loss=best[0])
        if progress:
            progress(sweep, out)
    return out


def constraints_from(meas, min_tol: float = 1.5, sign_margin: float = 3.0):
    """Draw-index constraints (offset from the dive's first draw, rand lo, rand hi, kind).
    |dx| bounds draw 4i+1 (r1 = |dx|/30); the sign bounds draw 4i+2 (r2 > 0.5 <=> dx < 0) when the
    whole [lo, hi] interval is clearly on one side."""
    cons = []
    for (c, i), m in meas.items():
        j = 200 * c + 4 * i
        lo, hi = m["lo"] - min_tol / 2, m["hi"] + min_tol / 2
        if lo >= sign_margin or hi <= -sign_margin:
            a, b = sorted((abs(lo), abs(hi)))
            cons.append((j + 1, max(0.0, a / 30), min(1.0, b / 30), "dx", (c, i)))
            cons.append((j + 2, 0.5, 1.0, "sign", (c, i)) if hi < 0 else (j + 2, 0.0, 0.5, "sign", (c, i)))
        else:
            # straddles zero: only |dx| <= max(|lo|, |hi|)
            cons.append((j + 1, 0.0, min(1.0, max(abs(lo), abs(hi)) / 30), "dx", (c, i)))
    return cons


def lattice_candidates(cons, max_dim: int = 12, max_nodes: int = 50_000_000, kinds=("dx",)):
    """States s (value of the dive's first draw) meeting the tightest constraints, by lattice enumeration."""
    from .lattice import box_points
    UNIT = 1 << 16
    cs = sorted([k for k in cons if k[3] in kinds], key=lambda k: k[2] - k[1])[:max_dim]
    if len(cs) < 3:
        return None
    jp, plo, phi = cs[0][:3]
    lo = [int(plo * 32768) * UNIT]
    hi = [min(32768, math.ceil(phi * 32768)) * UNIT - 1]
    gens = [[1]]
    for (j, l, h, *_) in cs[1:]:
        a, c = rng.jump(j - jp)
        a %= M31
        c %= M31
        gens[0].append(a)
        lo.append(int(l * 32768) * UNIT - c)
        hi.append(min(32768, math.ceil(h * 32768)) * UNIT - 1 - c)
    for t in range(len(cs) - 1):
        row = [0] * len(cs)
        row[t + 1] = M31
        gens.append(row)
    pts = box_points(gens, lo, hi, max_nodes)
    if pts is None:
        return None
    return sorted({rng.next_seed(p[0] % M31, -jp) % M31 for p in pts})


def violations(state: int, cons) -> int:
    bad = 0
    for (j, l, h, *_) in cons:
        r = rand_value(rng.next_seed(state, j))
        bad += not (l <= r <= h)
    return bad


# ---------------------------------------------------------------- finding dives in a video

def _menu_feats(f):
    f = f.astype(np.int16)
    b, gg, r = f[..., 0], f[..., 1], f[..., 2]
    blue = ((b > r + 40) & (b > gg + 15) & (b > 70)).mean()
    pink = ((r > 150) & (b > 120) & (gg < 140)).mean()
    return blue, pink


def menu_visits(path: str, step: int = 6, min_len: int = 30):
    """[(first, last)] frame ranges showing the challenge stage select (blue screen with pink flowers)."""
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    hits = []
    i = 0
    while i < n:
        if not cap.grab():
            break
        if i % step == 0:
            ok, f = cap.retrieve()
            if ok:
                small = cv2.resize(f, (160, 90))
                blue, pink = _menu_feats(small)
                if blue > 0.2 and pink > 0.008:
                    hits.append(i)
        i += 1
    runs = []
    for h in hits:
        if runs and h - runs[-1][1] <= 3 * step:
            runs[-1][1] = h
        else:
            runs.append([h, h])
    return [(a, b) for a, b in runs if b - a >= min_len]


# reference: cmal04 (Wii U, NTSC-U, 640x360) frame 11792, region R0 of the stage select
REF_VIDEO_FRAME = ("cmal04_tcbtrio_wiiu_usa", 11792)
REF_R0 = (20, 0, 600, 300)


def _prep(f):
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return cv2.GaussianBlur(g, (3, 3), 0)


def reference_menu() -> np.ndarray:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "challenge_menu_ref.png")
    return cv2.imread(p)


def register(frame, ref=None, sx_range=(0.6, 1.4), sy_range=(0.7, 1.3), step=0.03):
    """Scale/translation mapping reference-menu pixels onto this frame: u' = lx + (u - R0x) * sx, ..."""
    ref = reference_menu() if ref is None else ref
    x0, y0, x1, y1 = REF_R0
    R = _prep(ref)[y0:y1, x0:x1]
    T = _prep(frame)
    best = None
    for sy in np.arange(sy_range[0], sy_range[1] + 1e-9, step):
        for sx in np.arange(sx_range[0], sx_range[1] + 1e-9, step):
            r = cv2.resize(R, None, fx=sx, fy=sy)
            if r.shape[0] > T.shape[0] or r.shape[1] > T.shape[1]:
                continue
            m = cv2.matchTemplate(T, r, cv2.TM_CCOEFF_NORMED)
            _, sc, _, loc = cv2.minMaxLoc(m)
            if best is None or sc > best[0]:
                best = (sc, sx, sy, loc)
    sc, sx, sy, loc = best
    # refine
    for sy2 in np.arange(sy - step, sy + step + 1e-9, step / 4):
        for sx2 in np.arange(sx - step, sx + step + 1e-9, step / 4):
            r = cv2.resize(R, None, fx=sx2, fy=sy2)
            if r.shape[0] > T.shape[0] or r.shape[1] > T.shape[1]:
                continue
            m = cv2.matchTemplate(T, r, cv2.TM_CCOEFF_NORMED)
            _, s2, _, l2 = cv2.minMaxLoc(m)
            if s2 > best[0]:
                best = (s2, sx2, sy2, l2)
    return dict(score=float(best[0]), sx=float(best[1]), sy=float(best[2]), lx=float(best[3][0]), ly=float(best[3][1]))


def map_geometry(g: Geometry, reg) -> Geometry:
    """Reference-video geometry mapped through a registration."""
    x0, y0 = REF_R0[0], REF_R0[1]
    f = lambda u, v: (reg["lx"] + (u - x0) * reg["sx"], reg["ly"] + (v - y0) * reg["sy"])
    return Geometry(g.sx * reg["sx"], g.sy * reg["sy"], {c: f(*o) for c, o in g.origins.items()},
                    f(0, g.v100)[1], f(*g.goal), g.f0)


def geometry_vector(g: Geometry):
    return [g.sx, g.sy, g.f0, g.v100, g.goal[0], g.goal[1]] + [x for c in COLOURS for x in g.origins[c]]


def geometry_from_vector(th) -> Geometry:
    sx, sy, f0, v100, gu, gv = th[:6]
    o = th[6:]
    return Geometry(sx, sy, {c: (o[2 * k], o[2 * k + 1]) for k, c in enumerate(COLOURS)}, v100, (gu, gv), f0)


def fit_geometry(dv: DiveVideo, flat, g0: Geometry, frames, free_scale=True, origin_slack=12.0, f0_slack=8.0):
    """Fit geometry (and the dive's frame phase) for a known dive (flat params)."""
    from scipy.optimize import minimize
    th0 = geometry_vector(g0)
    B = [(g0.sx * 0.85, g0.sx * 1.15) if free_scale else (g0.sx, g0.sx),
         (g0.sy * 0.8, g0.sy * 1.2) if free_scale else (g0.sy, g0.sy),
         (g0.f0 - f0_slack, g0.f0 + f0_slack), (g0.v100 - 25, g0.v100 + 25),
         (g0.goal[0] - 80, g0.goal[0] + 80), (g0.goal[1] - 60, g0.goal[1] + 60)]
    B += [(x - origin_slack, x + origin_slack) for x in th0[6:]]
    best = None
    for df0 in (-3, 0, 3):
        t = list(th0)
        t[2] = min(max(t[2] + df0, B[2][0]), B[2][1])
        r = minimize(lambda th: image_loss(dv, flat, geometry_from_vector(th), frames), t, method="Powell",
                     bounds=B, options=dict(maxiter=8000, xtol=0.02, ftol=1e-6))
        if best is None or r.fun < best.fun:
            best = r
    return geometry_from_vector(best.x), float(best.fun)


def load_reference():
    import json
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "challenge_dive_ref.json")
    with open(p) as f:
        return json.load(f)


def panel_centre(ch: int, ref=None, reg=None):
    ref = ref or load_reference()
    gr = ref["grid"]
    k = ch - 1
    u, v = gr["x0"] + gr["dx"] * (k % gr["cols"]), gr["y0"] + gr["dy"] * (k // gr["cols"])
    if reg is not None:
        x0, y0 = REF_R0[0], REF_R0[1]
        u, v = reg["lx"] + (u - x0) * reg["sx"], reg["ly"] + (v - y0) * reg["sy"]
    return u, v


def selected_stage(frame, reg, ref=None):
    """The stage whose flower is drawn enlarged (the selected panel), from pink area around each panel."""
    ref = ref or load_reference()
    f = frame.astype(np.int16)
    b, gg, r = f[..., 0], f[..., 1], f[..., 2]
    pink = (r > 150) & (b > 120) & (gg < 160)
    best = None
    for ch in range(1, 31):
        u, v = panel_centre(ch, ref, reg)
        hw, hh = 18 * reg["sx"], 14 * reg["sy"]
        a = pink[int(max(0, v - hh)):int(v + hh), int(max(0, u - hw)):int(u + hw)].sum()
        if best is None or a > best[0]:
            best = (a, ch)
    return best[1]


def reference_geometry(ch: int, reg=None, f0: float = 0.0) -> Geometry:
    ref = load_reference()
    pu, pv = panel_centre(ch, ref)
    g = Geometry(ref["sx"], ref["sy"], {c: tuple(o) for c, o in ref["origins"].items()}, ref["v100"],
                 (pu + ref["goal_offset"][0], pv + ref["goal_offset"][1]), f0)
    return map_geometry(g, reg) if reg is not None else g


def landing_stage(path: str, first: int, last: int, reg, ref=None):
    """The stage panel where the dive lands: most near-white pixels around a panel over the visit's
    last frames (the flower burst when the Pikmin arrive). Returns (stage, score share)."""
    ref = ref or load_reference()
    cap = cv2.VideoCapture(path)
    a = max(first, last - 60)
    cap.set(cv2.CAP_PROP_POS_FRAMES, a)
    tot = np.zeros(30)
    for fr in range(a, last + 1):
        ok, f = cap.read()
        if not ok:
            break
        f = f.astype(np.int16)
        w = (f[..., 0] > 200) & (f[..., 1] > 200) & (f[..., 2] > 200)
        for ch in range(1, 31):
            u, v = panel_centre(ch, ref, reg)
            hw, hh = 20 * reg["sx"], 16 * reg["sy"]
            tot[ch - 1] += w[int(max(0, v - hh)):int(v + hh), int(max(0, u - hw)):int(u + hw)].sum()
    k = int(np.argmax(tot))
    return k + 1, float(tot[k] / max(1.0, tot.sum()))


# ---------------------------------------------------------------- brute-force search over all states

def _draw_values(states: np.ndarray, j: int) -> np.ndarray:
    """rand values (0..1) of draw j after each dive first state (uint64 array, values < 2^32)."""
    a, c = rng.jump(j)
    s = (states * np.uint64(a % (1 << 32)) + np.uint64(c % (1 << 32))) & np.uint64(0xFFFFFFFF)
    return ((s >> np.uint64(16)) & np.uint64(0x7FFF)).astype(np.float32) / np.float32(32768.0)


def _hop_frames(c: int, i: int, t_lo: float = 0.7, t_hi: float = 1.5):
    """Update counts n at which Pikmin (c, i) is late in its hop for every launch jitter r0."""
    base = -(0.1 * i + 0.5 * c)
    n_lo = math.ceil((t_lo - (base + 0.1)) / TIMER_SPEED)
    n_hi = math.floor((t_hi - base) / TIMER_SPEED)
    return list(range(n_lo, n_hi + 1))


def _pikmin_score(states, dv: DiveVideo, g: Geometry, c: int, i: int):
    """Sum of observation values at the Pikmin's predicted hop positions (higher = fits better)."""
    r0 = _draw_values(states, 200 * c + 4 * i)
    r1 = _draw_values(states, 200 * c + 4 * i + 1)
    r2 = _draw_values(states, 200 * c + 4 * i + 2)
    r3 = _draw_values(states, 200 * c + 4 * i + 3)
    T0 = 0.1 * r0 - np.float32(0.1 * i + 0.5 * c)
    dx = np.where(r2 > 0.5, -30.0 * r1, 30.0 * r1).astype(np.float32)
    dy = (15.0 + 10.0 * r3).astype(np.float32)
    u0, v0 = g.origins[COLOURS[c]]
    x0, y0, x1, y1 = dv.region
    H, W = y1 - y0, x1 - x0
    score = np.zeros(len(states), np.float32)
    for n in _hop_frames(c, i):
        fr = math.ceil(g.f0 + n)
        if fr not in dv.obs:
            continue
        t = T0 + np.float32(TIMER_SPEED * (fr - g.f0 - (fr - g.f0 - n)))   # = T0 + 0.15 n
        t = T0 + np.float32(TIMER_SPEED * n)
        t = np.minimum(t, np.float32(math.pi / 2))
        u = u0 - g.sx * dx * np.sin(t) - x0
        v = v0 - g.sy * np.abs(np.sin(2 * t) * dy) - y0
        ui = np.clip(np.rint(u).astype(np.int32), 0, W - 1)
        vi = np.clip(np.rint(v).astype(np.int32), 0, H - 1)
        score += dv.obs_search[fr][vi, ui]
    return score


def brute_force(dv: DiveVideo, counts, g: Geometry, first_pikmin: int = 3, keep_first: int = 1_000_000,
                per_stage_keep: int = 50_000, chunk_bits: int = 24, progress=None, states=None):
    """Search all 2^31 dive first states (or `states`). Stage 1 scores the first `first_pikmin` Pikmin
    of the first colour present, keeping the best `keep_first`; then every other visible Pikmin is added
    in launch order, pruning to `per_stage_keep`. Returns (states, scores) best first."""
    if not hasattr(dv, "obs_search"):
        dv.obs_search = {fr: cv2.GaussianBlur(o, (5, 5), 0) for fr, o in dv.obs.items()}
    order = sorted([(c, i) for c in range(5) for i in range(min(counts[c], 50))],
                   key=lambda k: 0.1 * k[1] + 0.5 * k[0])
    first = order[:first_pikmin]
    rest = order[first_pikmin:]
    if states is None:
        best_s = np.zeros(0, np.uint64)
        best_v = np.zeros(0, np.float32)
        step = 1 << chunk_bits
        for k, start in enumerate(range(0, 1 << 31, step)):
            s = np.arange(start, start + step, dtype=np.uint64)
            sc = np.zeros(step, np.float32)
            for (c, i) in first:
                sc += _pikmin_score(s, dv, g, c, i)
            # keep the chunk's best
            m = min(keep_first // ((1 << 31) // step) * 4, step)
            idx = np.argpartition(-sc, m - 1)[:m]
            best_s = np.concatenate([best_s, s[idx]])
            best_v = np.concatenate([best_v, sc[idx]])
            if len(best_s) > 2 * keep_first:
                o = np.argpartition(-best_v, keep_first - 1)[:keep_first]
                best_s, best_v = best_s[o], best_v[o]
            if progress:
                progress(k)
        o = np.argsort(-best_v)[:keep_first]
        states, scores = best_s[o], best_v[o]
    else:
        states = np.asarray(states, np.uint64)
        scores = np.zeros(len(states), np.float32)
        for (c, i) in first:
            scores += _pikmin_score(states, dv, g, c, i)
    for (c, i) in rest:
        scores = scores + _pikmin_score(states, dv, g, c, i)
        if len(states) > per_stage_keep:
            o = np.argpartition(-scores, per_stage_keep - 1)[:per_stage_keep]
            states, scores = states[o], scores[o]
    o = np.argsort(-scores)
    return states[o], scores[o]


# ---------------------------------------------------------------- compiled brute force (numba)

def _kernel():
    import numba as nb

    @nb.njit(parallel=True, fastmath=True, cache=True)
    def score_range(start, count, A, C, base, u0, v0, ns, slots, sx, sy, O, x0, y0, out, states):
        # A, C: (P, 4) jump coefficients for each Pikmin's 4 draws; base: -(0.1 i + 0.5 c)
        # ns, slots: (P, K) update counts and frame slots (-1 = unused)
        P, K = ns.shape
        H, W = O.shape[1], O.shape[2]
        for k in nb.prange(count):
            if states.shape[0] > 0:
                s = states[k]
            else:
                s = np.uint64(start + k)
            tot = 0.0
            for p in range(P):
                r = np.empty(4, np.float32)
                for d in range(4):
                    st = (A[p, d] * s + C[p, d]) & np.uint64(0xFFFFFFFF)
                    r[d] = np.float32((st >> np.uint64(16)) & np.uint64(0x7FFF)) / np.float32(32768.0)
                T0 = 0.1 * r[0] + base[p]
                dx = 30.0 * r[1]
                if r[2] > 0.5:
                    dx = -dx
                dy = 15.0 + 10.0 * r[3]
                for q in range(K):
                    sl = slots[p, q]
                    if sl < 0:
                        continue
                    t = T0 + 0.15 * ns[p, q]
                    if t > 1.5707963:
                        t = 1.5707963
                    if t < 0.0:
                        continue
                    u = u0[p] - sx * dx * np.sin(t) - x0
                    v = v0[p] - sy * abs(np.sin(2.0 * t) * dy) - y0
                    ui = int(u + 0.5)
                    vi = int(v + 0.5)
                    if ui < 0:
                        ui = 0
                    if ui >= W:
                        ui = W - 1
                    if vi < 0:
                        vi = 0
                    if vi >= H:
                        vi = H - 1
                    tot += O[sl, vi, ui]
            out[k] = tot
    return score_range


_SCORE = None
_EMPTY = np.zeros(0, np.uint64)


def _prep_search(dv: DiveVideo, counts, g: Geometry, pikmin):
    if not hasattr(dv, "obs_search"):
        dv.obs_search = {fr: cv2.GaussianBlur(o, (5, 5), 0) for fr, o in dv.obs.items()}
    frames = sorted(dv.obs_search)
    slot = {fr: k for k, fr in enumerate(frames)}
    O = np.stack([dv.obs_search[fr] for fr in frames]).astype(np.float32)
    P = len(pikmin)
    K = 8
    A = np.zeros((P, 4), np.uint64)
    C = np.zeros((P, 4), np.uint64)
    base = np.zeros(P, np.float32)
    u0 = np.zeros(P, np.float32)
    v0 = np.zeros(P, np.float32)
    ns = np.zeros((P, K), np.float32)
    sl = -np.ones((P, K), np.int64)
    for p, (c, i) in enumerate(pikmin):
        for d in range(4):
            a, cc = rng.jump(200 * c + 4 * i + d)
            A[p, d], C[p, d] = a % (1 << 32), cc % (1 << 32)
        base[p] = -(0.1 * i + 0.5 * c)
        u0[p], v0[p] = g.origins[COLOURS[c]]
        q = 0
        for n in _hop_frames(c, i):
            fr = math.ceil(g.f0 + n)
            if fr in slot and q < K:
                ns[p, q], sl[p, q] = n, slot[fr]
                q += 1
    x0, y0 = dv.region[0], dv.region[1]
    return A, C, base, u0, v0, ns, sl, O, x0, y0


def search_all(dv: DiveVideo, counts, g: Geometry, first_pikmin: int = 6, keep: int = 2_000_000,
               chunk: int = 1 << 25, progress=None):
    """Score all 2^31 dive first states on the first `first_pikmin` Pikmin (in launch order) with the
    compiled kernel; keep the best `keep`. Returns (states uint64, scores)."""
    global _SCORE
    if _SCORE is None:
        _SCORE = _kernel()
    order = sorted([(c, i) for c in range(5) for i in range(min(counts[c], 50))],
                   key=lambda k: 0.1 * k[1] + 0.5 * k[0])
    A, C, base, u0, v0, ns, sl, O, x0, y0 = _prep_search(dv, counts, g, order[:first_pikmin])
    best_s = np.zeros(0, np.uint64)
    best_v = np.zeros(0, np.float32)
    per = max(1, keep * chunk // (1 << 31) * 3)
    out = np.empty(chunk, np.float32)
    for k, start in enumerate(range(0, 1 << 31, chunk)):
        _SCORE(start, chunk, A, C, base, u0, v0, ns, sl, np.float32(g.sx), np.float32(g.sy), O,
               np.float32(x0), np.float32(y0), out, _EMPTY)
        idx = np.argpartition(-out, per - 1)[:per]
        best_s = np.concatenate([best_s, (idx + start).astype(np.uint64)])
        best_v = np.concatenate([best_v, out[idx]])
        if progress:
            progress(k)
    o = np.argsort(-best_v)[:keep]
    return best_s[o], best_v[o]


def rescore(dv: DiveVideo, counts, g: Geometry, states, pikmin=None):
    """Kernel score of given states over the given Pikmin (default: all visible)."""
    global _SCORE
    if _SCORE is None:
        _SCORE = _kernel()
    order = sorted([(c, i) for c in range(5) for i in range(min(counts[c], 50))],
                   key=lambda k: 0.1 * k[1] + 0.5 * k[0])
    pk = order if pikmin is None else pikmin
    A, C, base, u0, v0, ns, sl, O, x0, y0 = _prep_search(dv, counts, g, pk)
    states = np.ascontiguousarray(states, np.uint64)
    out = np.empty(len(states), np.float32)
    _SCORE(0, len(states), A, C, base, u0, v0, ns, sl, np.float32(g.sx), np.float32(g.sy), O,
           np.float32(x0), np.float32(y0), out, states)
    return out
