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
# observation model: True = background is the pre-dive menu (icons shown) and a waiting Pikmin shows no
# difference while a launched colour leaves its icon missing; False = background is the dive's own
# median and waiting Pikmin are drawn at their origin
ICON_MODEL = False


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

    def __init__(self, path: str, first: int, last: int, bg_frame, region, template=None, blur=3,
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
        elif isinstance(bg_frame, (tuple, list)):
            # median of a range of frames (the clean menu before the "Pick one!" window)
            cap = cv2.VideoCapture(path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, bg_frame[0])
            bgs = []
            for _ in range(bg_frame[0], bg_frame[1] + 1):
                ok, b = cap.read()
                if ok:
                    bgs.append(b.astype(np.float32)[y0:y1, x0:x1])
            pre = np.median(np.stack(bgs), axis=0)
            stack = np.stack(list(raw.values()))
            dive_med = np.median(stack, axis=0)
            # a pixel that shows the pre-dive value in a good share of the dive frames is static
            # background (only sometimes covered by a Pikmin); elsewhere something else changed
            # (cursor, selection effect, brightness), so the dive's own median is used there
            same = (np.abs(stack - pre[None]).sum(3) < 40).mean(0)
            bg = np.where((same >= 0.25)[..., None], pre, dive_med)
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
        # drop frames dominated by something other than Pikmin (the "Pick one!" window fading out)
        masses = {fr: float(o.sum()) for fr, o in self.obs.items()}
        med = float(np.median(list(masses.values()))) if masses else 0.0
        self.dropped = [fr for fr, m in masses.items() if m > 3.0 * med + 500]
        for fr in self.dropped:
            del self.obs[fr]
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
    """{frame: (us, vs)}: where the difference from the pre-dive menu shows a Pikmin sprite.
    A Pikmin waiting at its origin looks exactly like the tally icon (the icon is drawn with the same
    panes), so it shows no difference; once every Pikmin of a colour has launched, the icon is
    missing, which shows as one sprite-sized difference at the origin."""
    nmax = int(max(frames) - g.f0) + 2
    if nmax <= 0:
        nmax = 1
    U, V = simulate(flat, g, nmax)
    out = {}
    T0 = flat[:, 0]
    col = flat[:, 3].astype(int)
    present = sorted(set(col.tolist()))
    for fr in frames:
        n = int(math.floor(fr - g.f0))          # updates done by this frame
        if n <= 0:
            if ICON_MODEL:
                out[fr] = (np.zeros(0), np.zeros(0))
            else:
                org = np.array([g.origins[COLOURS[int(c)]] for c in col]).reshape(len(col), 2)
                out[fr] = (org[:, 0], org[:, 1])
            continue
        waiting = T0 + TIMER_SPEED * min(n, nmax) < 0
        if not ICON_MODEL:
            out[fr] = (U[min(n, nmax) - 1], V[min(n, nmax) - 1])
            continue
        us = np.where(waiting, np.nan, U[min(n, nmax) - 1])
        vs = np.where(waiting, np.nan, V[min(n, nmax) - 1])
        gone = [g.origins[COLOURS[c]] for c in present if not np.any(waiting & (col == c))]
        if gone:
            us = np.concatenate([us, [o[0] for o in gone]])
            vs = np.concatenate([vs, [o[1] for o in gone]])
        out[fr] = (us, vs)
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


def fit_geometry(dv: DiveVideo, flat, g0: Geometry, frames, free_scale=True, origin_slack=12.0, f0_slack=8.0,
                 fast: bool = False, anchor: Geometry | None = None, state: int | None = None, counts=None):
    """Fit geometry (and the dive's frame phase) for a known dive (flat params). With `state` and
    `counts` (and all of dv's frames) the objective is the compiled loss, about 4x faster."""
    from scipy.optimize import minimize
    th0 = geometry_vector(g0)
    a = anchor or g0                     # bounds around the registered geometry, so refits can't drift
    ta = geometry_vector(a)
    B = [(a.sx * 0.85, a.sx * 1.15) if free_scale else (a.sx, a.sx),
         (a.sy * 0.8, a.sy * 1.2) if free_scale else (a.sy, a.sy),
         (a.f0 - f0_slack, a.f0 + f0_slack), (a.v100 - 25, a.v100 + 25),
         (a.goal[0] - 80, a.goal[0] + 80), (a.goal[1] - 60, a.goal[1] + 60)]
    B += [(x - origin_slack, x + origin_slack) for x in ta[6:]]
    th0 = [min(max(x, lo), hi) for x, (lo, hi) in zip(th0, B)]
    best = None
    starts = (0,)
    for df0 in starts:
        t = list(th0)
        t[2] = min(max(t[2] + df0, B[2][0]), B[2][1])
        if state is not None and counts is not None and list(frames) == sorted(dv.obs) and not ICON_MODEL:
            obj = OneStateLoss(dv, counts, state, g0)
            fun = lambda th: obj(geometry_from_vector(th))  # noqa: E731
        else:
            fun = lambda th: image_loss(dv, flat, geometry_from_vector(th), frames)  # noqa: E731
        r = minimize(fun, t, method="Powell",
                     bounds=B, options=dict(maxiter=1500 if fast else 3000, xtol=0.05 if fast else 0.02,
                                            ftol=1e-5 if fast else 1e-6))
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


# ---------------------------------------------------------------- end to end

def motion_onset(path: str, first: int, last: int, g: Geometry, colour: str, thr: float = 8.0):
    """First frame with clear motion around a colour's icon (the dive's first hop)."""
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    u, v = g.origins[colour]
    hw, hh = 45 * g.sx / 0.84, 32 * g.sy / 0.62
    prev = None
    quiet = 0
    for fr in range(first, last + 1):
        ok, f = cap.read()
        if not ok:
            break
        c = f[int(max(0, v - hh)):int(v + hh * 0.5), int(max(0, u - hw)):int(u + hw)].astype(np.float32)
        if prev is not None and prev.shape == c.shape:
            m = float(np.abs(c - prev).sum(2).mean())
            if m < 2.0:
                quiet += 1
            elif m > thr and quiet >= 2:
                return fr
            else:
                quiet = 0
        prev = c
    return None


ONSET_LAG = 2.3     # motion onset minus fitted f0 (calibrated on the reference video)


def dive_region(g: Geometry, counts):
    us = [g.origins[c][0] for c, k in zip(COLOURS, counts) if k]
    vs = [g.origins[c][1] for c, k in zip(COLOURS, counts) if k]
    padx, pady = 70 * g.sx / 0.84, 80 * g.sy / 0.62
    x0 = int(max(0, min(us) - padx))
    x1 = int(max(us) + padx)
    y0 = int(max(0, g.v100 - 70 * g.sy - 30))
    y1 = int(max(vs) + 30)
    return x0, y0, x1, y1


def window_states(end_state: int, span: int, skip: int = 0) -> np.ndarray:
    """Dive first states whose floor-1 layout seed is skip..skip+span-1 draws before `end_state`."""
    a, c = rng.jump(-1)
    out = []
    x = rng.prev_seed(end_state, 999 + skip)
    for _ in range(span):
        out.append(x)
        x = (a * x + c) & 0xFFFFFFFF
    return np.array(out, np.uint64)


def read_dive(path: str, visit, ch: int | None = None, reg=None, geometry: Geometry | None = None,
              keep: int = 4_000_000, mid: int = 400_000, final: int = 2000, first_pikmin: int = 6, log=print,
              window=None, save_top: int = 200, refit: int = 6, iterations: int = 2, f0_search: float = 20.0,
              final_exact: int = 300, probe=(), f0_offsets=(-3.0, -1.5, 0.0, 1.5, 3.0),
              f0_offsets_refit=(-1.5, 0.0, 1.5), rank_pool: int = 5000, threads: int = 6,
              setup_only: bool = False, skip_if_clear: bool = False, prune_coarse=(2, 2), rank_mid: int = 0, hook=None,
              use_closing: bool = True):
    """Recover the dive's first state for one menu visit (first, last). Returns a dict with the
    best candidates (state, image loss), the stage, the geometry used and timings. `probe` states
    (e.g. a known truth) are scored at the end with the final geometry and reported under "probes",
    with where they stood in each pruning stage."""
    import time
    t0 = time.time()
    first, last = visit
    cap = cv2.VideoCapture(path)
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    reg_frame = first + min(15, (last - first) // 4)
    # menu detection misses the darkened "Pick one!" frames, where the dive starts: look 30 earlier
    first, last = max(0, first - 30), min(n_frames - 1, last + 12)
    if reg is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, reg_frame)
        ok, f = cap.read()
        reg = register(f)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, visit[0] + 3))
        ok, f2 = cap.read()
        if ok:
            reg = refine_registration(f2, reg)
    if ch is None:
        ch, share = landing_stage(path, first, last, reg)
    counts = stage_counts(ch)
    g = geometry if geometry is not None else reference_geometry(ch, reg)
    lead = next(c for c, k in zip(COLOURS, counts) if k)
    onset = motion_onset(path, first, last, g, lead)
    if onset is None and window is None:
        return dict(ok=False, note="no dive motion found", ch=ch, reg=reg)
    # the lead colour's group starts 0.5/0.15 frames per colour after red
    lead_c = COLOURS.index(lead)
    lead_delay = lead_c * 0.5 / TIMER_SPEED
    f0_guess = (onset - ONSET_LAG - lead_delay) if onset is not None else first + 20 - lead_delay
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / TIMER_SPEED + 45)
    region = dive_region(g, counts)
    if window is not None:
        # the whole visit: the dive can start anywhere in it (menu detection may begin late)
        f0_lo, f0_hi = visit[0] - 45.0, visit[1] + 2.0
    else:
        f0_lo = f0_hi = f0_guess
    scale = float(np.sqrt(reg["sx"] * reg["sy"]))
    g = g.copy(f0=f0_guess)
    log(f"stage CH{ch} counts {counts} onset {onset} f0~{g.f0:.1f} region {region} reg {reg}")
    # The dive starts as the "Pick one!" window closes: 1-3 frames before a burst of whole-screen
    # motion (cmal04: bursts at 5889, 11815, 32009 for f0 5887.7, 11812.7, ~32007). The burst before
    # that one is the window opening; just before it the menu is clean and shows every tally icon,
    # which is also what a Pikmin waiting at its origin looks like: that is the background.
    all_bursts = motion_bursts(path, max(0, int(f0_lo) - 120), int(f0_hi) + 6)
    closes = [b for b in all_bursts if f0_lo <= b <= f0_hi + 4]

    def background_for(close):
        if not ICON_MODEL:
            return None
        prev = [b for b in all_bursts if b < close - 5]
        if not prev:
            return None
        o = prev[-1]
        return (max(0, o - 12), max(0, o - 2))

    if window is not None:
        st = window_states(*window)
        log(f"  window: {len(st)} states before roll state 0x{window[0]:08X} ({time.time() - t0:.0f}s)")
        sample = st[:: max(1, len(st) // 200_000)]

        def f0_score(dvx, f0):
            sc = rescore(dvx, counts, g.copy(f0=float(f0)), sample)
            # contrast, not level: frames full of non-Pikmin change raise every state's score alike
            return float(np.sort(sc)[-100:].mean() - np.median(sc))

        trials = []
        videos = {}
        ce = closing_end(path, max(0, int(f0_lo) - 30), min(n_frames - 1, int(f0_hi) + 12)) if use_closing else None
        if ce is not None:
            closes = [ce - CLOSING_LAG]
            log(f"  \"Pick one!\" window closed at {ce}")
        else:
            loc = burst_locality(path, closes, g, lead, lead_delay) if closes else {}
            if loc:
                top = max(loc.values())
                closes = [b for b in closes if loc.get(b, 0) >= 0.8 * top]
                log(f"  burst locality {[(b, round(v, 2)) for b, v in loc.items()]} -> {closes}")
        for b in closes or [int(f0_guess + 2)]:
            bgb = background_for(b)
            dvb = DiveVideo(path, max(0, b - 6), min(n_frames - 1, b + span), bgb, region, scale=scale)
            videos[b] = (dvb, bgb)
            for d in (-4.3, -3.3, -2.3, -1.3, -0.3):
                trials.append((f0_score(dvb, b + d), float(b + d), b))
        trials.sort(reverse=True)
        b0 = trials[0][2]
        dvb, bg = videos[b0]
        c0 = trials[0][1]
        trials += [(f0_score(dvb, f0), float(f0), b0) for f0 in (c0 - 0.5, c0 + 0.5)]
        trials.sort(reverse=True)
        log(f"  motion bursts at {all_bursts}; closing burst {b0}, background frames {bg}")
        g = g.copy(f0=trials[0][1])
        dv = DiveVideo(path, int(g.f0) + 2, min(n_frames - 1, int(g.f0) + span), bg, region, scale=scale)
        log(f"  f0 search: best {trials[0][1]:.1f} (guess {f0_guess:.1f}); top {[(round(f, 1), round(v, 2)) for v, f, _ in trials[:4]]}")
        if setup_only:      # stage, region, start frame and reference geometry only (for other scorers)
            return dict(ok=True, ch=ch, counts=counts, reg=reg, f0=g.f0, region=list(region), window=list(window),
                        dropped=dv.dropped, candidates=[dict(geometry=geometry_vector(g))])
    else:
        loc = burst_locality(path, closes, g, lead, lead_delay) if closes else {}
        if loc:
            g = g.copy(f0=max(loc, key=loc.get) - ONSET_LAG)
        near = min(all_bursts, key=lambda b: abs(b - (g.f0 + 2.3)), default=None)
        bg = background_for(near) if near is not None else None
        dv = DiveVideo(path, int(g.f0) + 2, min(n_frames - 1, int(g.f0) + span), bg, region, scale=scale)
        st, sc = search_all(dv, counts, g, first_pikmin=first_pikmin, keep=keep)
        log(f"  stage-1 search done {time.time() - t0:.0f}s")
    if hook is not None:                    # benchmarking: hand over the prepared dive and stop
        return hook(dv, counts, g, st)
    frames = sorted(dv.obs)
    flats = {}

    def prune(geom, offs):
        sc2 = rescore(dv, counts, geom, st)
        o = np.argsort(-sc2)[:mid]
        st2 = st[o]
        # the dive start (f0) is known to a frame or two; a look-alike at the wrong phase can beat the
        # truth at a fixed f0, so take each state's best over a few start offsets
        bl = np.min([batch_image_loss(dv, counts, geom.copy(f0=geom.f0 + d), st2, *prune_coarse) for d in offs], axis=0)
        o2 = np.argsort(bl)
        st3 = st2[o2[:20_000]]
        for x in probe_set:
            k1 = np.nonzero((st & 0x7FFFFFFF) == (x & 0x7FFFFFFF))[0]
            k2 = np.nonzero((st2[o2] & 0x7FFFFFFF) == (x & 0x7FFFFFFF))[0]
            r1 = int(np.nonzero(o == k1[0])[0][0]) if len(k1) and (o == k1[0]).any() else None
            log(f"  probe 0x{x:08X}: score rank {r1 if r1 is not None else '>' + str(mid)}"
                f"{'' if len(k1) else ' (not in stage 1)'}, coarse-loss rank {int(k2[0]) if len(k2) else None}")
        # the coarse loss (half resolution, every other frame) is noisy for dense dives: re-rank its
        # best at full resolution on every frame before the exact loss
        return st3

    def rank(geom, pool, offs):
        # exact loss (compiled, full resolution, every frame) on the pool's best by coarse loss, each
        # at its best start offset
        cand = pool[:rank_pool]
        if rank_mid and len(cand) > rank_mid:
            # half resolution, every other frame first (7x cheaper), the exact loss on its best only
            pre = fast_loss(dv, counts, geom, cand, 2, 2, f0_offsets=offs)
            cand = cand[np.argsort(pre)[:rank_mid]]
        bl = fast_loss(dv, counts, geom, cand, f0_offsets=offs)
        o = np.argsort(bl)[:final_exact]
        # ordered by the best offset's loss: the refits that follow fit f0, so a state that only lines up
        # at a shifted start must not be ranked by the unshifted loss
        for x in cand[o]:
            if int(x) not in flats:
                flats[int(x)] = flatten(dive_params(int(x), counts))
        return [(float(bl[k]), int(cand[k])) for k in o]

    def merge(a, b):
        # union keeping order (each pool is sorted by coarse loss; the newer one first)
        both = np.concatenate([b, a])
        _, first_at = np.unique(both & np.uint64(0x7FFFFFFF), return_index=True)
        return both[np.sort(first_at)]

    def fit(x, geom, fast):
        if x not in flats:
            flats[x] = flatten(dive_params(x, counts))
        return fit_geometry(dv, flats[x], geom, frames, fast=fast, anchor=g, state=x, counts=counts)

    from concurrent.futures import ThreadPoolExecutor
    _inputs(dv, 1, 1)                           # build the shared kernel inputs before any threads
    pool_ex = ThreadPoolExecutor(max_workers=max(1, threads))

    probe_set = [int(x) & 0xFFFFFFFF for x in probe]
    pool = prune(g, f0_offsets)
    log(f"  pruned {len(st)} -> {len(pool)} ({time.time() - t0:.0f}s)")
    probe = [int(x) & 0xFFFFFFFF for x in probe]
    probe_stage1 = {x: bool(np.isin(np.array([x, x ^ 0x80000000], st.dtype), st).any()) for x in probe}
    probe_pool = {x: bool(np.isin(np.array([x, x ^ 0x80000000], pool.dtype), pool).any()) for x in probe}
    res = rank(g, pool, f0_offsets)
    log(f"  ranked: leader 0x{res[0][1]:08X} {res[0][0]:.1f}, next {res[1][0]:.1f} ({time.time() - t0:.0f}s)")
    # alternate: refit the geometry on the leader, prune and re-rank with it (a look-alike's geometry is
    # nearly right, so this converges on the true state, which lines up exactly)
    geo = g
    if skip_if_clear and (res[1][0] - res[0][0]) / res[0][0] > 0.1:
        iterations = 0                          # already a clear leader (small anchored windows)
    for it in range(iterations):
        lead = res[0][1]
        geo, _ = fit(lead, geo, False)
        if window is not None:                 # pruning the window again is cheap
            pool = merge(pool, prune(geo, f0_offsets_refit))
        res = rank(geo, pool, f0_offsets_refit)
        log(f"  iteration {it + 1}: leader 0x{res[0][1]:08X} {res[0][0]:.1f}, next {res[1][0]:.1f} ({time.time() - t0:.0f}s)")
        if (res[1][0] - res[0][0]) / res[0][0] > 0.1:
            break                               # a clear leader: the geometry has converged
    refined = []
    fits = list(pool_ex.map(lambda ls: fit(ls[1], geo, True), res[:refit]))
    for (l, s), (g3, l3) in zip(res[:refit], fits):
        refined.append((min(l, l3), s, (g3 if l3 < l else geo).f0, l, geometry_vector(g3 if l3 < l else geo)))
    refined.sort()
    # a whole-dive shift by 4 draws hands every Pikmin its neighbour's values: nearly the same
    # picture (the frame phase absorbs the timing). The true start is a minimum against its shifts.
    best_s = refined[0][1]
    best_l = refined[0][0]
    for _ in range(4):                      # walk to the best shift (a shift can fit better)
        shifts = []
        ss = [rng.next_seed(best_s, k) & 0xFFFFFFFF for k in (-8, -4, 4, 8)]
        fx = list(pool_ex.map(lambda x: fit(x, geo, True), ss))
        plain = fast_loss(dv, counts, geo, ss)
        for k, s2, (g4, l4), l0 in zip((-8, -4, 4, 8), ss, fx, plain):
            shifts.append(dict(shift=k, state=s2, loss=min(l4, float(l0)), f0=g4.f0, geometry=geometry_vector(g4)))
        better = min(shifts, key=lambda x: x["loss"])
        if better["loss"] >= best_l:
            break
        log(f"  shift {better['shift']:+d} fits better ({better['loss']:.1f} < {best_l:.1f}): moving")
        refined.insert(0, (better["loss"], better["state"], better["f0"], better["loss"], better["geometry"]))
        best_s, best_l = better["state"], better["loss"]
    refined.sort()
    shift_margin = (min(x["loss"] for x in shifts) - refined[0][0]) / refined[0][0]
    log(f"  shifts: {[(x['shift'], round(x['loss'], 1)) for x in shifts]} (margin {shift_margin:+.3f})")
    probes = []
    for x in probe:
        gx, lx = fit(x, geo, True)
        lx = min(lx, float(fast_loss(dv, counts, geo, [x])[0]))
        log(f"  probe 0x{x:08X}: refit f0 {gx.f0:.2f} vs {geo.f0:.2f}, sx {gx.sx:.3f}/{geo.sx:.3f}, sy {gx.sy:.3f}/{geo.sy:.3f}")
        probes.append(dict(state=x, loss=lx, in_stage1=probe_stage1[x], in_pool=probe_pool[x],
                           rel=(lx - refined[0][0]) / refined[0][0]))
        log(f"  probe 0x{x:08X}: loss {lx:.1f} ({probes[-1]['rel']:+.3f} vs best), stage-1 {probe_stage1[x]}, "
            f"pool {probe_pool[x]}")
    pool_ex.shutdown()
    log(f"  done {time.time() - t0:.0f}s best {[(hex(s), round(l, 1)) for l, s, *_ in refined[:3]]}")
    return dict(ok=True, ch=ch, counts=counts, reg=reg, onset=onset, f0=g.f0, region=region,
                top=[dict(state=s, loss=l) for l, s in res[:save_top]], dropped=dv.dropped,
                candidates=[dict(state=s, loss=l, f0=f, loss_fixed=lf, geometry=gv, layout_seed=layout_seed(s))
                            for l, s, f, lf, gv in refined],
                margin=(refined[1][0] - refined[0][0]) / refined[0][0] if len(refined) > 1 else None,
                shifts=shifts, shift_margin=shift_margin, probes=probes,
                seconds=time.time() - t0)


# ---------------------------------------------------------------- compiled batch image loss

def _loss_kernel():
    import numba as nb

    @nb.njit(parallel=True, fastmath=True, cache=True)
    def batch_loss(states, A, C, base, idx, u0, v0, sx, sy, v100, gu, gv, f0, frames, O, T, tcx, tcy,
                   x0, y0, ds, out, col, corg, icon):
        P = A.shape[0]
        F = frames.shape[0]
        H, W = O.shape[1], O.shape[2]
        th, tw = T.shape
        nmax = int(frames[F - 1] - f0) + 2
        for k in nb.prange(states.shape[0]):
            s = states[k]
            U = np.full((F, P), np.nan, np.float32)
            V = np.full((F, P), np.nan, np.float32)
            T0s = np.empty(P, np.float32)
            for p in range(P):
                r = np.empty(4, np.float32)
                for d in range(4):
                    st = (A[p, d] * s + C[p, d]) & np.uint64(0xFFFFFFFF)
                    r[d] = np.float32((st >> np.uint64(16)) & np.uint64(0x7FFF)) / np.float32(32768.0)
                t = 0.1 * r[0] + base[p]
                T0s[p] = t
                dx = 30.0 * r[1]
                if r[2] > 0.5:
                    dx = -dx
                dy = 15.0 + 10.0 * r[3]
                calc = 0.0
                if idx[p] % 3 == 0:
                    calc = -8.0 * sx
                elif idx[p] % 3 == 1:
                    calc = 8.0 * sx
                state = 0
                u = u0[p]
                v = v0[p]
                ui = 0.0
                vi = 0.0
                q = 0
                for n in range(1, nmax + 1):
                    t += 0.15
                    st0 = state
                    if st0 == 0:
                        if t >= 0:
                            u = u0[p] - sx * dx * np.sin(t)
                            v = v0[p] - sy * abs(np.sin(2.0 * t) * dy)
                            if t > 1.5707963267948966:
                                state = 3
                    elif st0 == 3:
                        if v > v100:
                            v -= 12.0 * sy
                        else:
                            state = 4
                            ui = u
                            vi = v
                            t = 0.0
                    elif st0 == 4:
                        if t > 3.141592653589793:
                            state = 5
                            t = 3.141592653589793
                        u = ui + t * (gu - ui + calc) / 3.141592653589793
                        v = vi - 70.0 * sy * np.sin(t)
                    elif st0 == 5:
                        if v < gv - 40.0 * sy:
                            v += 12.0 * sy
                        else:
                            state = 6
                    # record at the frames whose update count is n
                    while q < F and int(np.floor(frames[q] - f0)) <= n:
                        # waiting Pikmin look like the icon: no difference, not drawn
                        if int(np.floor(frames[q] - f0)) == n and state != 6:
                            if state != 0 or t >= 0 or not icon:
                                U[q, p] = u
                                V[q, p] = v
                        elif int(np.floor(frames[q] - f0)) < 1 and not icon:
                            U[q, p] = u0[p]
                            V[q, p] = v0[p]
                        q += 1
            err = 0.0
            img = np.zeros((H, W), np.float32)
            Ux = np.empty(P + 5, np.float32)
            Vx = np.empty(P + 5, np.float32)
            for q in range(F):
                img[:, :] = 0.0
                nq = np.floor(frames[q] - f0)
                m = 0
                for p in range(P):
                    Ux[m] = U[q, p]
                    Vx[m] = V[q, p]
                    m += 1
                # a colour whose Pikmin have all launched leaves its icon missing
                for c in range(5 if icon else 0):
                    anyc = False
                    waiting = False
                    for p in range(P):
                        if col[p] == c:
                            anyc = True
                            if nq < 1 or T0s[p] + 0.15 * nq < 0:
                                waiting = True
                    if anyc and not waiting:
                        Ux[m] = corg[c, 0]
                        Vx[m] = corg[c, 1]
                        m += 1
                for p in range(m):
                    uu = Ux[p]
                    if uu != uu:
                        continue
                    xx = int(np.floor((uu - x0) / ds - tcx + 0.5))
                    yy = int(np.floor((Vx[p] - y0) / ds - tcy + 0.5))
                    for a in range(th):
                        yv = yy + a
                        if yv < 0 or yv >= H:
                            continue
                        for b in range(tw):
                            xv = xx + b
                            if xv < 0 or xv >= W:
                                continue
                            val = T[a, b]
                            if val > img[yv, xv]:
                                img[yv, xv] = val
                for yv in range(H):
                    for xv in range(W):
                        dd = img[yv, xv] - O[q, yv, xv]
                        err += dd * dd
            out[k] = err
    return batch_loss


_BATCH = None


def batch_image_loss(dv: DiveVideo, counts, g: Geometry, states, frame_step: int = 2, ds: int = 2):
    """Approximate image_loss for many states at once (half resolution, every other frame)."""
    global _BATCH
    if _BATCH is None:
        _BATCH = _loss_kernel()
    pk = [(c, i) for c in range(5) for i in range(min(counts[c], 50))]
    P = len(pk)
    A = np.zeros((P, 4), np.uint64)
    C = np.zeros((P, 4), np.uint64)
    base = np.zeros(P, np.float32)
    idx = np.zeros(P, np.int64)
    u0 = np.zeros(P, np.float32)
    v0 = np.zeros(P, np.float32)
    for p, (c, i) in enumerate(pk):
        for d in range(4):
            a, cc = rng.jump(200 * c + 4 * i + d)
            A[p, d], C[p, d] = a % (1 << 32), cc % (1 << 32)
        base[p] = -(0.1 * i + 0.5 * c)
        idx[p] = i
        u0[p], v0[p] = g.origins[COLOURS[c]]
    frames = np.array(sorted(dv.obs)[::frame_step], np.float64)
    O = np.stack([cv2.resize(dv.obs[int(f)], None, fx=1 / ds, fy=1 / ds, interpolation=cv2.INTER_AREA)
                  for f in frames]).astype(np.float32)
    T = cv2.resize(dv.renderer.bank[0, 0], None, fx=1 / ds, fy=1 / ds, interpolation=cv2.INTER_AREA).astype(np.float32)
    tcx, tcy = dv.renderer.cx / ds, dv.renderer.cy / ds
    states = np.ascontiguousarray(states, np.uint64)
    out = np.empty(len(states), np.float64)
    _BATCH(states, A, C, base, idx, u0, v0, np.float32(g.sx), np.float32(g.sy), np.float32(g.v100),
           np.float32(g.goal[0]), np.float32(g.goal[1]), np.float64(g.f0), frames, O, T,
           np.float32(tcx), np.float32(tcy), np.float32(dv.region[0]), np.float32(dv.region[1]),
           np.float32(ds), out, np.array([c for c, i in pk], np.int64),
           np.array([g.origins[c] for c in COLOURS], np.float32), ICON_MODEL)
    return out


# ---------------------------------------------------------------- compiled exact loss (sparse, sub-pixel)

def _sparse_kernel():
    import numba as nb

    @nb.njit(fastmath=True, cache=True, nogil=True)
    def one(s, A, C, base, idx, u0, v0, sx, sy, v100, gu, gv, f0, frames, O, O2, bank, sub, tcx, tcy,
            x0, y0, ds, img, touched, U, V):
        P = A.shape[0]
        F = frames.shape[0]
        H, W = O.shape[1], O.shape[2]
        th, tw = bank.shape[2], bank.shape[3]
        nmax = int(frames[F - 1] - f0) + 2
        for q in range(F):
            for p in range(P):
                U[q, p] = np.nan
        for p in range(P):
            r = np.empty(4, np.float32)
            for d in range(4):
                st = (A[p, d] * s + C[p, d]) & np.uint64(0xFFFFFFFF)
                r[d] = np.float32((st >> np.uint64(16)) & np.uint64(0x7FFF)) / np.float32(32768.0)
            t = 0.1 * r[0] + base[p]
            dx = 30.0 * r[1]
            if r[2] > 0.5:
                dx = -dx
            dy = 15.0 + 10.0 * r[3]
            calc = 0.0
            if idx[p] % 3 == 0:
                calc = -8.0 * sx
            elif idx[p] % 3 == 1:
                calc = 8.0 * sx
            state = 0
            u = u0[p]
            v = v0[p]
            ui = 0.0
            vi = 0.0
            q = 0
            while q < F and np.floor(frames[q] - f0) < 1:      # before the first update: at the origin
                U[q, p] = u0[p]
                V[q, p] = v0[p]
                q += 1
            for n in range(1, nmax + 1):
                if q >= F:
                    break
                t += 0.15
                st0 = state
                if st0 == 0:
                    if t >= 0:
                        u = u0[p] - sx * dx * np.sin(t)
                        v = v0[p] - sy * abs(np.sin(2.0 * t) * dy)
                        if t > 1.5707963267948966:
                            state = 3
                elif st0 == 3:
                    if v > v100:
                        v -= 12.0 * sy
                    else:
                        state = 4
                        ui = u
                        vi = v
                        t = 0.0
                elif st0 == 4:
                    if t > 3.141592653589793:
                        state = 5
                        t = 3.141592653589793
                    u = ui + t * (gu - ui + calc) / 3.141592653589793
                    v = vi - 70.0 * sy * np.sin(t)
                elif st0 == 5:
                    if v < gv - 40.0 * sy:
                        v += 12.0 * sy
                    else:
                        state = 6
                while q < F and int(np.floor(frames[q] - f0)) <= n:
                    if int(np.floor(frames[q] - f0)) == n and state != 6:
                        U[q, p] = u
                        V[q, p] = v
                    q += 1
        err = 0.0
        for q in range(F):
            m = 0
            for p in range(P):
                uu = U[q, p]
                if uu != uu:
                    continue
                x = (uu - x0) / ds - tcx
                y = (V[q, p] - y0) / ds - tcy
                ix = int(np.floor(x))
                iy = int(np.floor(y))
                a = min(sub - 1, int((x - ix) * sub))
                b = min(sub - 1, int((y - iy) * sub))
                for yy in range(th):
                    yv = iy + yy
                    if yv < 0 or yv >= H:
                        continue
                    for xx in range(tw):
                        xv = ix + xx
                        if xv < 0 or xv >= W:
                            continue
                        val = bank[a, b, yy, xx]
                        cur = img[yv, xv]
                        if val > cur:
                            if cur == 0.0:
                                touched[m] = yv * W + xv
                                m += 1
                            img[yv, xv] = val
            # sum over the frame of (img - O)^2 = sum O^2 + sum over drawn pixels of (img^2 - 2 img O)
            e = O2[q]
            for k in range(m):
                yv = touched[k] // W
                xv = touched[k] % W
                rv = img[yv, xv]
                e += rv * rv - 2.0 * rv * O[q, yv, xv]
                img[yv, xv] = 0.0
            err += e
        return err

    @nb.njit(parallel=True, fastmath=True, cache=True)
    def many(states, A, C, base, idx, u0, v0, sx, sy, v100, gu, gv, f0s, frames, O, O2, bank, sub, tcx, tcy,
             x0, y0, ds, out):
        P = A.shape[0]
        F = frames.shape[0]
        H, W = O.shape[1], O.shape[2]
        cap = P * bank.shape[2] * bank.shape[3] + 1
        for k in nb.prange(states.shape[0]):
            img = np.zeros((H, W), np.float32)
            touched = np.empty(cap, np.int64)
            U = np.empty((F, P), np.float32)
            V = np.empty((F, P), np.float32)
            best = np.inf
            for j in range(f0s.shape[0]):
                e = one(states[k], A, C, base, idx, u0, v0, sx, sy, v100, gu, gv, f0s[j], frames, O, O2, bank,
                        sub, tcx, tcy, x0, y0, ds, img, touched, U, V)
                if e < best:
                    best = e
            out[k] = best

    return one, many


_SPARSE = None


class _ScoreInputs:
    """Per (dive video, resolution) arrays for the sparse kernel, cached on the DiveVideo."""

    def __init__(self, dv: DiveVideo, frame_step: int, ds: int):
        rd = dv.renderer
        self.frames = np.array(sorted(dv.obs)[::frame_step], np.float64)

        def shrink(im):
            return im if ds == 1 else cv2.resize(im, None, fx=1 / ds, fy=1 / ds, interpolation=cv2.INTER_AREA)

        self.O = np.ascontiguousarray(np.stack([shrink(dv.obs[int(f)]) for f in self.frames]), np.float32)
        # bank[a, b]: the sprite shifted by (a/sub, b/sub) px, as Renderer.render indexes it
        self.bank = np.ascontiguousarray(
            np.stack([np.stack([shrink(rd.bank[a, b]) for b in range(rd.sub)]) for a in range(rd.sub)]), np.float32)
        self.O2 = (self.O.astype(np.float64) ** 2).sum(axis=(1, 2))
        self.sub = rd.sub
        self.tcx, self.tcy = rd.cx / ds, rd.cy / ds
        self.ds = ds
        self.x0, self.y0 = dv.region[0], dv.region[1]


def _inputs(dv: DiveVideo, frame_step: int, ds: int) -> _ScoreInputs:
    cache = dv.__dict__.setdefault("_score_inputs", {})
    if (frame_step, ds) not in cache:
        cache[frame_step, ds] = _ScoreInputs(dv, frame_step, ds)
    return cache[frame_step, ds]


def _pikmin_arrays(counts, g: Geometry):
    pk = [(c, i) for c in range(5) for i in range(min(counts[c], 50))]
    P = len(pk)
    A = np.zeros((P, 4), np.uint64)
    C = np.zeros((P, 4), np.uint64)
    base = np.zeros(P, np.float32)
    idx = np.zeros(P, np.int64)
    u0 = np.zeros(P, np.float32)
    v0 = np.zeros(P, np.float32)
    for p, (c, i) in enumerate(pk):
        for d in range(4):
            a, cc = rng.jump(200 * c + 4 * i + d)
            A[p, d], C[p, d] = a % (1 << 32), cc % (1 << 32)
        base[p] = -(0.1 * i + 0.5 * c)
        idx[p] = i
        u0[p], v0[p] = g.origins[COLOURS[c]]
    return A, C, base, idx, u0, v0


def fast_loss(dv: DiveVideo, counts, g: Geometry, states, frame_step: int = 1, ds: int = 1, f0_offsets=(0.0,)):
    """Compiled image loss of many dive first states, each its best over the f0 offsets. At
    frame_step=1, ds=1 it equals image_loss (sub-pixel sprites, every frame). Only the pixels a sprite
    covers are visited; the rest of each frame contributes its precomputed sum of O^2."""
    global _SPARSE
    if ICON_MODEL:
        raise NotImplementedError("fast_loss implements the median-background model only")
    if _SPARSE is None:
        _SPARSE = _sparse_kernel()
    si = _inputs(dv, frame_step, ds)
    A, C, base, idx, u0, v0 = _pikmin_arrays(counts, g)
    states = np.ascontiguousarray(np.atleast_1d(np.asarray(states, np.uint64)))
    out = np.empty(len(states), np.float64)
    f0s = np.array([g.f0 + d for d in f0_offsets], np.float64)
    _SPARSE[1](states, A, C, base, idx, u0, v0, np.float32(g.sx), np.float32(g.sy), np.float32(g.v100),
               np.float32(g.goal[0]), np.float32(g.goal[1]), f0s, si.frames, si.O, si.O2, si.bank, si.sub,
               np.float32(si.tcx), np.float32(si.tcy), np.float32(si.x0), np.float32(si.y0), np.float32(si.ds), out)
    return out


class OneStateLoss:
    """fast_loss of one state as a function of the geometry, for the optimiser (no thread start-up,
    scratch buffers reused)."""

    def __init__(self, dv: DiveVideo, counts, state: int, g: Geometry, frame_step: int = 1, ds: int = 1):
        global _SPARSE
        if _SPARSE is None:
            _SPARSE = _sparse_kernel()
        self.si = si = _inputs(dv, frame_step, ds)
        self.A, self.C, self.base, self.idx, _, _ = _pikmin_arrays(counts, g)
        self.pk = [(c, i) for c in range(5) for i in range(min(counts[c], 50))]
        self.col = np.array([c for c, i in self.pk], np.int64)
        self.state = np.uint64(int(state) & 0xFFFFFFFF)
        P = len(self.pk)
        H, W = si.O.shape[1], si.O.shape[2]
        self.img = np.zeros((H, W), np.float32)
        self.touched = np.empty(P * si.bank.shape[2] * si.bank.shape[3] + 1, np.int64)
        self.U = np.empty((len(si.frames), P), np.float32)
        self.V = np.empty((len(si.frames), P), np.float32)

    def __call__(self, g: Geometry) -> float:
        si = self.si
        org = np.array([g.origins[c] for c in COLOURS], np.float32)
        u0 = np.ascontiguousarray(org[self.col, 0])
        v0 = np.ascontiguousarray(org[self.col, 1])
        return float(_SPARSE[0](self.state, self.A, self.C, self.base, self.idx, u0, v0, np.float32(g.sx),
                                np.float32(g.sy), np.float32(g.v100), np.float32(g.goal[0]), np.float32(g.goal[1]),
                                np.float64(g.f0), si.frames, si.O, si.O2, si.bank, si.sub, np.float32(si.tcx),
                                np.float32(si.tcy), np.float32(si.x0), np.float32(si.y0), np.float32(si.ds),
                                self.img, self.touched, self.U, self.V))


def stage_draw_rates():
    import json
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "challenge_stage_draws.json")
    with open(p) as f:
        return {int(k): v for k, v in json.load(f)["stages"].items()}


def draw_window(ch: int, frames: float, slack: float = 0.35, fallback: int = 3_000_000):
    """(skip, span) draws before the next results roll where the floor-1 seed should lie, from the
    stage's draws per frame on CMAL runs and the frames between the dive and the results."""
    r = stage_draw_rates().get(ch)
    if r is None or frames <= 0:
        return 0, fallback
    lo = max(0, int(frames * r["min"] * (1 - slack)))
    hi = int(frames * r["max"] * (1 + slack)) + 5000
    return lo, hi - lo


def motion_bursts(path: str, first: int, last: int, min_gap: int = 3):
    """Frames where whole-screen motion starts after a quiet stretch (menu windows opening/closing,
    the dive starting). Threshold relative to the window's quiet level."""
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, first - 1))
    prev = None
    d = {}
    for fr in range(max(0, first - 1), last + 1):
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.float32)
        if prev is not None:
            d[fr] = float(np.abs(g - prev).mean())
        prev = g
    if not d:
        return []
    vals = np.array(list(d.values()))
    quiet = float(np.percentile(vals, 30))
    thr = max(2.5 * quiet, quiet + 2.0)
    out, calm = [], min_gap
    for fr in sorted(d):
        if d[fr] > thr:
            if calm >= min_gap:
                out.append(fr)
            calm = 0
        else:
            calm += 1
    return out


def burst_locality(path: str, bursts, g: Geometry, lead: str, lead_delay: float, length: int = 12):
    """For each burst: (motion near the lead colour's icon where its first hop is due, relative to the
    whole screen) over (the same just before the burst). The dive's own burst is followed by local
    motion (Pikmin hopping) and preceded by none; the "Pick one!" window opening or a fade moves the
    whole screen, and bursts later in the dive are preceded by Pikmin already moving."""
    cap = cv2.VideoCapture(path)
    u, v = g.origins[lead]
    hw, hh = 40 * g.sx / 0.84, 30 * g.sy / 0.62

    def rel(a, n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, a - 1))
        ok, prev = cap.read()
        if not ok:
            return None
        loc, glob = [], []
        for _ in range(n):
            ok, f = cap.read()
            if not ok:
                break
            d = np.abs(f.astype(np.float32) - prev.astype(np.float32)).sum(2)
            loc.append(float(d[int(max(0, v - hh)):int(v + hh * 0.6), int(max(0, u - hw)):int(u + hw)].mean()))
            glob.append(float(d.mean()))
            prev = f
        return float(np.mean(loc)) / (float(np.mean(glob)) + 1.0) if loc else None

    out = {}
    for b in bursts:
        after = rel(int(b + lead_delay) - 1, length)
        before = rel(max(0, b - 10), 9)
        if after is not None and before is not None:
            out[b] = after / (before + 0.5)
    return out


def closing_end(path: str, first: int, last: int):
    """Last frame of the "Pick one!" window closing: a run of whole-screen motion that drops to the
    quiet of the dive itself, with the picture back at full, steady brightness. The dive starts
    6-10 frames before it (median 8.7 over cmal04/08/13). Unlike a burst *start* this needs no quiet
    stretch before the window closes, so it also works when the stage is picked the instant the menu
    fades in. Returns the frame or None."""
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, first - 1))
    prev, fr_, d, br = None, [], [], []
    for fr in range(max(0, first - 1), last + 1):
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.float32)
        if prev is not None:
            fr_.append(fr)
            d.append(float(np.abs(g - prev).mean()))
            br.append(float(g.mean()))
        prev = g
    d, br = np.array(d), np.array(br)
    if len(d) < 24:
        return None
    full = 0.85 * float(np.percentile(br, 90))
    best = None
    for i in range(6, len(d) - 14):
        post, pre = d[i + 1:i + 11], d[i - 4:i + 1]
        b = br[i + 1:i + 11]
        if pre.mean() < 3 or b.std() > 2.5 or b.mean() < full or post.max() > max(2.5, 0.6 * pre.mean()):
            continue
        r = pre.mean() / (post.mean() + 0.3)
        if best is None or r > best[0]:
            best = (r, fr_[i])
    return best[1] if best else None


CLOSING_LAG = 6     # closing_end minus the burst-start frame the f0 trials are centred on


def refine_registration(frame, reg, min_score: float = 0.85, search: int = 22):
    """Sharpen a menu registration with the tally icons themselves: match each reference icon near
    its registered place and refit x and y scale/offset from the icons that match well (the colours
    in use can be highlighted and match poorly). Returns a new registration dict (or the input)."""
    ref = reference_menu()
    R = load_reference()
    G = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).astype(np.float32)
    T = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    x0r, y0r = REF_R0[0], REF_R0[1]
    pts = []
    for c, (u, v) in R["origins"].items():
        px, py = int(u - 12), int(v - 20)
        patch = cv2.resize(G[py:py + 30, px:px + 24], None, fx=reg["sx"], fy=reg["sy"])
        mx = reg["lx"] + (px - x0r) * reg["sx"]
        my = reg["ly"] + (py - y0r) * reg["sy"]
        ax, ay = int(mx - search), int(my - search)
        win = T[max(0, ay):ay + patch.shape[0] + 2 * search, max(0, ax):ax + patch.shape[1] + 2 * search]
        if win.shape[0] < patch.shape[0] or win.shape[1] < patch.shape[1]:
            continue
        m = cv2.matchTemplate(win, patch, cv2.TM_CCOEFF_NORMED)
        _, sc, _, loc = cv2.minMaxLoc(m)
        if sc >= min_score:
            pts.append((u, v, loc[0] + max(0, ax) - mx + reg["lx"] + (u - x0r) * reg["sx"],
                        loc[1] + max(0, ay) - my + reg["ly"] + (v - y0r) * reg["sy"]))
    if len(pts) < 3:
        return reg
    a = np.array(pts)
    out = dict(reg)
    for k, (src, dst, key_s, key_l, base) in enumerate(((0, 2, "sx", "lx", x0r), (1, 3, "sy", "ly", y0r))):
        xs, ys = a[:, src] - base, a[:, dst]
        if np.ptp(xs) < 20:                 # not enough spread: keep the scale, fit the offset
            out[key_l] = float(np.mean(ys - xs * reg[key_s]))
            continue
        s, l = np.polyfit(xs, ys, 1)
        out[key_s], out[key_l] = float(s), float(l)
    out["icons"] = len(pts)
    return out
