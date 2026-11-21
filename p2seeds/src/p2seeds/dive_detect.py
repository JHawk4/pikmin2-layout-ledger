"""Detect dive Pikmin in the video, per colour and frame, with the game's own sprites as templates.

For each frame and each colour present, a response map: masked normalised cross-correlation
(TM_CCOEFF_NORMED over the sprite's opaque pixels) of the colour frame with that colour's sprite, at a
few scales around the geometry's, so brightness, contrast and small tint or stretch differences of a
capture do not matter; multiplied by how much of the sprite's area differs from the background, so
static menu art that happens to correlate is suppressed. Peaks of the map are the detections.

Map coordinates are anchor positions (the pane0 point dive_rgb uses), in video px.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from . import challenge_dive as cd
from . import dive_rgb as dr
from . import rng


def template(sp: dict, colour: str, sx: float, sy: float, blur: float = 0.6):
    """(BGR image 0..255, alpha mask, ox, oy): the sprite and its top-left offset from the anchor."""
    p, ox, oy = dr.colour_patch(sp, colour, sx, sy, blur)
    a = p[..., 3]
    rgb = np.where(a[..., None] > 1e-3, p[..., :3] / np.maximum(a[..., None], 1e-3), 0)
    return rgb.astype(np.float32), a.astype(np.float32), ox, oy


class Detector:
    def __init__(self, sp: dict, colours, sx: float, sy: float, scales=(0.92, 1.0, 1.08), blur: float = 0.6,
                 mask_thr: float = 0.5):
        self.t = {}
        for c in colours:
            self.t[c] = []
            for k in scales:
                rgb, a, ox, oy = template(sp, c, sx * k, sy * k, blur)
                m = (a > mask_thr).astype(np.float32)
                self.t[c].append((rgb, m, ox, oy, k))

    def maps(self, frame: np.ndarray, bg: np.ndarray):
        """{colour: response map} over anchor positions (map[y, x] = anchor at region px (x, y))."""
        H, W = frame.shape[:2]
        changed = (np.abs(frame - bg).sum(2) > 45).astype(np.float32)
        out = {}
        for c, ts in self.t.items():
            best = np.full((H, W), -1.0, np.float32)
            for rgb, m, ox, oy, k in ts:
                th, tw = m.shape
                pad = ((th, th), (tw, tw), (0, 0))
                fp = np.pad(frame, pad, mode="edge")
                r = cv2.matchTemplate(fp, rgb, cv2.TM_CCOEFF_NORMED, mask=np.repeat(m[..., None], 3, 2))
                r = np.nan_to_num(r, nan=-1.0, posinf=-1.0, neginf=-1.0)
                cp = np.pad(changed, pad[:2])
                frac = cv2.matchTemplate(cp, m, cv2.TM_CCORR) / max(m.sum(), 1.0)
                r = r * np.clip(frac, 0, 1)
                # r[y, x] has the template's top-left at padded (x, y) = region (x - tw, y - th);
                # the anchor is the top-left minus (ox, oy)
                ys, xs = np.mgrid[0:H, 0:W]
                ty, tx = ys + oy + th, xs + ox + tw
                ok = (ty >= 0) & (tx >= 0) & (ty < r.shape[0]) & (tx < r.shape[1])
                v = np.full((H, W), -1.0, np.float32)
                v[ok] = r[ty[ok], tx[ok]]
                best = np.maximum(best, v)
            out[c] = best
        return out


def peaks(resp: np.ndarray, thr: float = 0.35, radius: int = 4, max_n: int = 60):
    """Local maxima above thr: list of (x, y, value), strongest first."""
    k = 2 * radius + 1
    dil = cv2.dilate(resp, np.ones((k, k), np.uint8))
    ys, xs = np.nonzero((resp >= dil) & (resp > thr))
    v = resp[ys, xs]
    o = np.argsort(-v)[:max_n]
    return [(int(xs[i]), int(ys[i]), float(v[i])) for i in o]


# ---------------------------------------------------------------- scoring states against detections

def _det_kernel():
    import numba as nb

    @nb.njit(parallel=True, fastmath=True, cache=True)
    def score(states, A, C, base, csl, idx3, u0, v0, sx, sy, v100, gu, gv, nslot, O, out):
        # A, C: (P, 4) jumps to each Pikmin's 4 draws; base: -(0.1 i + 0.5 c); csl: colour slot in O;
        # idx3: i % 3; u0, v0: anchor start in map px; nslot[n]: frame slot after n updates (-1 none),
        # n = 0 is "not started"; O: (colours, frames, H, W) response maps
        P = A.shape[0]
        N = nslot.shape[0]
        H, W = O.shape[2], O.shape[3]
        for k in nb.prange(states.shape[0]):
            s = states[k]
            tot = 0.0
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
                if idx3[p] == 0:
                    calc = -8.0 * sx
                elif idx3[p] == 1:
                    calc = 8.0 * sx
                u = u0[p]
                v = v0[p]
                ui = 0.0
                vi = 0.0
                state = 0
                c = csl[p]
                for n in range(N):
                    if n > 0:
                        t += 0.15
                        if state == 0:
                            if t >= 0.0:
                                if t > 1.5707963:
                                    state = 3
                                u = u0[p] - sx * dx * np.sin(t)
                                v = v0[p] - sy * abs(np.sin(2.0 * t) * dy)
                        elif state == 3:
                            if v > v100:
                                v -= 12.0 * sy
                            else:
                                state = 4
                                ui = u
                                vi = v
                                t = 0.0
                        elif state == 4:
                            if t > 3.14159265:
                                state = 5
                                t = 3.14159265
                            u = ui + t * (gu - ui + calc) / 3.14159265
                            v = vi - 70.0 * sy * np.sin(t)
                        elif state == 5:
                            if v < gv - 40.0 * sy:
                                v += 12.0 * sy
                            else:
                                state = 6
                    if state == 6:
                        break
                    sl = nslot[n]
                    if sl < 0:
                        continue
                    xi = int(u + 0.5)
                    yi = int(v + 0.5)
                    if xi >= 0 and yi >= 0 and xi < W and yi < H:
                        tot += O[c, sl, yi, xi]
            out[k] = tot
    return score


_DET = None


class DetScorer:
    """Detection maps of one dive and a compiled scorer of states against them."""

    def __init__(self, rd, counts, sp: dict, sx: float, sy: float, blur: float = 1.2):
        self.rd, self.counts = rd, counts
        self.colours = [c for k, c in enumerate(cd.COLOURS) if counts[k]]
        self.det = Detector(sp, self.colours, sx, sy)
        self.frames = list(rd.frames)
        maps = [self.det.maps(rd.raw[f], rd.bg) for f in self.frames]
        self.O = np.stack([np.stack([cv2.GaussianBlur(np.maximum(m[c], 0), (0, 0), blur) for m in maps])
                           for c in self.colours]).astype(np.float32)
        self.raw_maps = maps

    def inputs(self, g, pikmin=None):
        order = [(c, i) for c in range(5) for i in range(min(self.counts[c], 50))]
        pk = order if pikmin is None else pikmin
        P = len(pk)
        A = np.zeros((P, 4), np.uint64)
        C = np.zeros((P, 4), np.uint64)
        base = np.zeros(P, np.float32)
        csl = np.zeros(P, np.int64)
        idx3 = np.zeros(P, np.int64)
        u0 = np.zeros(P, np.float32)
        v0 = np.zeros(P, np.float32)
        x0, y0 = self.rd.region[:2]
        for p, (c, i) in enumerate(pk):
            for d in range(4):
                a, cc = rng.jump(200 * c + 4 * i + d)
                A[p, d], C[p, d] = a % (1 << 32), cc % (1 << 32)
            base[p] = -(0.1 * i + 0.5 * c)
            csl[p] = self.colours.index(cd.COLOURS[c])
            idx3[p] = i % 3
            u0[p], v0[p] = g.origins[cd.COLOURS[c]][0] - x0, g.origins[cd.COLOURS[c]][1] - y0
        # frame shown after n updates: floor(fr - f0) = n
        N = int(max(self.frames) - g.f0) + 2
        nslot = -np.ones(max(N, 1), np.int64)
        for k, fr in enumerate(self.frames):
            n = math.floor(fr - g.f0)
            if 0 <= n < N:
                nslot[n] = k
        return (A, C, base, csl, idx3, u0, v0, np.float32(g.sx), np.float32(g.sy), np.float32(g.v100 - y0),
                np.float32(g.goal[0] - x0), np.float32(g.goal[1] - y0), nslot)

    def score(self, g, states, pikmin=None) -> np.ndarray:
        global _DET
        if _DET is None:
            _DET = _det_kernel()
        states = np.ascontiguousarray(np.asarray(states, np.uint64))
        out = np.empty(len(states), np.float32)
        _DET(states, *self.inputs(g, pikmin), self.O, out)
        return out

    def origin_correction(self, g, n_frames: int = 6):
        """(du, dv): detected minus predicted anchor of each colour's waiting stack, in the first frames."""
        x0, y0 = self.rd.region[:2]
        d = []
        for k, c in enumerate(self.colours):
            m = self.O[k, :n_frames].mean(0)
            u, v = g.origins[c][0] - x0, g.origins[c][1] - y0
            r = 16
            ya, xa = max(0, int(v) - r), max(0, int(u) - r)
            sub = m[ya:int(v) + r + 1, xa:int(u) + r + 1]
            yy, xx = np.unravel_index(np.argmax(sub), sub.shape)
            d.append((xa + xx - u, ya + yy - v))
        return tuple(np.median(np.array(d), axis=0))

    def fit(self, g, state: int, slack: float = 6.0, f0_slack: float = 3.0):
        """Maximise the score of one state over the geometry (Powell)."""
        from scipy.optimize import minimize
        t0 = np.array(cd.geometry_vector(g), float)
        used = [cd.COLOURS.index(c) for c in self.colours]
        act = [0, 1, 2, 3, 4, 5] + [6 + 2 * c + k for c in used for k in (0, 1)]
        lo, hi = t0.copy(), t0.copy()
        lo[:2] *= 0.9; hi[:2] *= 1.1
        lo[2] -= f0_slack; hi[2] += f0_slack
        lo[3:] -= slack; hi[3:] += slack

        def full(x):
            th = t0.copy()
            th[act] = x
            return np.clip(th, lo, hi)

        st = np.array([state], np.uint64)
        fun = lambda x: -float(self.score(cd.geometry_from_vector(full(x)), st)[0])  # noqa: E731
        r = minimize(fun, t0[act], method="Powell", options=dict(maxfev=3000, xtol=0.05, ftol=1e-6))
        return cd.geometry_from_vector(full(r.x)), -float(r.fun)
