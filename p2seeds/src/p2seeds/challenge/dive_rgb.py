"""Colour model of the challenge-select dive: the game's own sprites, drawn in the game's order.

The sprites (body + flower per colour) and their offsets come from the disc
(docs/challenge_dive/extract_sprites.py -> data/game/dive_sprites.npz). TChallengePiki::draw draws,
for colours red, yellow, blue, white, purple in turn, Pikmin 49 down to 0, each as body then flower;
later draws cover earlier ones (alpha blending).

Positions: challenge_dive.trajectory gives a video point per Pikmin that moves like the game's
mCurrentPos; here that point is the pane0 anchor (the icon's top-left in game units), mapped to
video px with the geometry's (sx, sy). The reference geometry's origins were fitted to the old grey
blob's centre, so `anchor_shift` converts between the two.
"""

from __future__ import annotations

import math
import os

import cv2
import numpy as np

from . import dive as cd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
SPRITES = os.environ.get("P2SEEDS_DIVE_SPRITES") or os.path.join(ROOT, "data", "game", "dive_sprites.npz")


def load_sprites(path: str = SPRITES) -> dict:
    z = np.load(path)
    return {k: z[k] for k in z.files}


def colour_patch(sp: dict, colour: str, sx: float, sy: float, blur: float = 0.0, sub: tuple = (0.0, 0.0),
                 parts=("body", "flower")):
    """Premultiplied RGBA patch (float32, RGB in 0..255 BGR order) of one Pikmin of `colour` drawn at
    video scale (sx, sy) with its anchor at sub-pixel offset `sub`. Returns (patch, ox, oy): the patch's
    top-left pixel relative to the anchor's integer pixel."""
    parts = [(sp[f"{colour}_{k}"], sp[f"{colour}_{k}_rect"]) for k in parts]
    x0 = min(r[0] for _, r in parts) * sx + sub[0]
    y0 = min(r[1] for _, r in parts) * sy + sub[1]
    x1 = max(r[2] for _, r in parts) * sx + sub[0]
    y1 = max(r[3] for _, r in parts) * sy + sub[1]
    pad = int(math.ceil(2 * blur)) + 1
    ox, oy = math.floor(x0) - pad, math.floor(y0) - pad
    W, H = math.ceil(x1) - ox + pad, math.ceil(y1) - oy + pad
    acc = np.zeros((H, W, 4), np.float32)          # premultiplied, composited body then flower
    for img, r in parts:
        h, w = img.shape[:2]
        # map texture -> destination rect (bilinear, as GX does)
        ax, ay = (r[2] - r[0]) * sx / w, (r[3] - r[1]) * sy / h
        bx, by = r[0] * sx + sub[0] - ox, r[1] * sy + sub[1] - oy
        M = np.float32([[ax, 0, bx + 0.5 * ax - 0.5], [0, ay, by + 0.5 * ay - 0.5]])
        pm = img.copy()
        pm[..., :3] *= pm[..., 3:4]
        pm = pm[..., [2, 1, 0, 3]]                 # RGB -> BGR (OpenCV frames)
        warped = cv2.warpAffine(pm, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        a = warped[..., 3:4]
        acc = warped + acc * (1 - a)
    if blur > 0:
        acc = cv2.GaussianBlur(acc, (0, 0), blur)
    acc[..., :3] *= 255.0
    return acc, ox, oy


class SpriteBank:
    """Sub-pixel banks of colour patches at one video scale."""

    def __init__(self, sp: dict, sx: float, sy: float, blur: float = 0.6, sub: int = 4, colour_mat=None):
        self.sub = sub
        self.bank = {}
        for c in cd.COLOURS:
            for a in range(sub):
                for b in range(sub):
                    p, ox, oy = colour_patch(sp, c, sx, sy, blur, (a / sub, b / sub))
                    if colour_mat is not None:
                        # affine colour response of the capture: rgb' = M rgb + t * alpha
                        M, t = colour_mat
                        rgb = p[..., :3].reshape(-1, 3) @ np.asarray(M, np.float32).T
                        p[..., :3] = rgb.reshape(p.shape[:2] + (3,)) + np.asarray(t, np.float32) * p[..., 3:4]
                    self.bank[c, a, b] = (p, ox, oy)

    def patch(self, colour: str, u: float, v: float):
        iu, iv = math.floor(u), math.floor(v)
        a = min(self.sub - 1, int((u - iu) * self.sub))
        b = min(self.sub - 1, int((v - iv) * self.sub))
        p, ox, oy = self.bank[colour, a, b]
        return p, iu + ox, iv + oy


def anchor_shift(sp: dict, colour: str, sx: float, sy: float):
    """Video offset from the anchor to the alpha-weighted centre of the sprite (the old blob centre)."""
    p, ox, oy = colour_patch(sp, colour, sx, sy)
    a = p[..., 3]
    ys, xs = np.mgrid[:a.shape[0], :a.shape[1]]
    return float((xs * a).sum() / a.sum() + ox), float((ys * a).sum() / a.sum() + oy)


def draw_order(flat) -> np.ndarray:
    """Indices into flat in the game's draw order: colour order, then index 49 .. 0."""
    col, idx = flat[:, 3].astype(int), flat[:, 4].astype(int)
    return np.lexsort((-idx, col))


def render(bg: np.ndarray, region, bank: SpriteBank, flat, us, vs) -> np.ndarray:
    """Composite the Pikmin over `bg` (the dive region, BGR float32)."""
    img = bg.copy()
    H, W = img.shape[:2]
    x0, y0 = region[0], region[1]
    for k in draw_order(flat):
        u, v = us[k], vs[k]
        if u != u:
            continue
        p, px, py = bank.patch(cd.COLOURS[int(flat[k, 3])], u - x0, v - y0)
        h, w = p.shape[:2]
        xa, ya, xb, yb = max(px, 0), max(py, 0), min(px + w, W), min(py + h, H)
        if xa >= xb or ya >= yb:
            continue
        s = p[ya - py:yb - py, xa - px:xb - px]
        dst = img[ya:yb, xa:xb]
        dst *= 1 - s[..., 3:4]
        dst += s[..., :3]
    return img


def shifted_geometry(g, sp: dict):
    """Geometry whose origins are pane0 anchors, from one whose origins are blob centres."""
    o, sh = {}, []
    for c, (u, v) in g.origins.items():
        du, dv = anchor_shift(sp, c, g.sx, g.sy)
        o[c] = (u - du, v - dv)
        sh.append((du, dv))
    mu, mv = np.mean(sh, axis=0)
    # the game's goal and climb height apply to the anchor too; shift them by the mean offset
    return g.copy(origins=o, goal=(g.goal[0] - mu, g.goal[1] - mv), v100=g.v100 - mv)


class RGBDive:
    """Colour frames of one dive and the loss of a state's rendering against them."""

    def __init__(self, path: str, first: int, last: int, region, drop=(), sp: dict | None = None, mass_drop: float = 3.0):
        self.region = region
        x0, y0, x1, y1 = region
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)
        raw = {}
        for fr in range(first, last + 1):
            ok, f = cap.read()
            if not ok:
                break
            raw[fr] = f[y0:y1, x0:x1].astype(np.float32)
        frames = [f for f in raw if f not in set(drop)]
        self.bg = np.median(np.stack([raw[f] for f in frames]), axis=0)
        # drop fades and other whole-region changes
        m = {f: float(np.abs(raw[f] - self.bg).sum()) for f in frames}
        med = float(np.median(list(m.values())))
        self.frames = [f for f in frames if m[f] <= mass_drop * med + 1e5]
        self.raw = {f: raw[f] for f in self.frames}
        self.base = {f: float(((self.bg - raw[f]) ** 2).sum()) for f in self.frames}
        self.sp = sp or load_sprites()
        self._banks = {}

    def bank(self, sx, sy, blur=0.7, colour_mat=None):
        key = (round(sx, 3), round(sy, 3), round(blur, 2), None if colour_mat is None else id(colour_mat))
        if key not in self._banks:
            if len(self._banks) > 64:
                self._banks.clear()
            self._banks[key] = SpriteBank(self.sp, key[0], key[1], blur, colour_mat=colour_mat)
        return self._banks[key]

    def loss(self, flat, g, blur=0.7, colour_mat=None, frames=None) -> float:
        """Sum over frames of squared colour error, relative to showing the background alone."""
        frames = frames or self.frames
        bank = self.bank(g.sx, g.sy, blur, colour_mat)
        pf = cd.predicted_frames(flat, g, frames)
        e = 0.0
        for f in frames:
            im = render(self.bg, self.region, bank, flat, *pf[f])
            e += float(((im - self.raw[f]) ** 2).sum()) - self.base[f]
        return e

    def fit(self, flat, g, iters: int = 2, f0_slack: float = 4.0, origin_slack: float = 12.0):
        """Powell fit of the geometry vector (anchor geometry) under the colour loss."""
        from scipy.optimize import minimize
        t0 = np.array(cd.geometry_vector(g), float)
        lo = t0.copy(); hi = t0.copy()
        lo[:2] *= 0.85; hi[:2] *= 1.15
        lo[2] -= f0_slack; hi[2] += f0_slack
        lo[3:] -= origin_slack; hi[3:] += origin_slack
        used = sorted(set(flat[:, 3].astype(int).tolist()))
        act = [0, 1, 2, 3, 4, 5] + [6 + 2 * c + k for c in used for k in (0, 1)]

        def full(x):
            th = t0.copy()
            th[act] = x
            return np.clip(th, lo, hi)

        fun = lambda x: self.loss(flat, cd.geometry_from_vector(full(x)))  # noqa: E731
        x = t0[act]
        for _ in range(iters):
            r = minimize(fun, x, method="Powell", options=dict(maxfev=800, xtol=0.02, ftol=1e-6))
            x = r.x
        return cd.geometry_from_vector(full(x)), float(fun(x))
