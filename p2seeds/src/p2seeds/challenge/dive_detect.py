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

from . import dive as cd
from . import dive_rgb as dr
from .. import rng


def template(sp: dict, colour: str, sx: float, sy: float, blur: float = 0.6, parts=("body", "flower")):
    """(BGR image 0..255, alpha mask, ox, oy): the sprite and its top-left offset from the anchor."""
    p, ox, oy = dr.colour_patch(sp, colour, sx, sy, blur, parts=parts)
    a = p[..., 3]
    rgb = np.where(a[..., None] > 1e-3, p[..., :3] / np.maximum(a[..., None], 1e-3), 0)
    return rgb.astype(np.float32), a.astype(np.float32), ox, oy


class Detector:
    def __init__(self, sp: dict, colours, sx: float, sy: float, scales=(0.92, 1.0, 1.08), blur: float = 0.6,
                 mask_thr: float = 0.5, parts=("body", "flower")):
        self.t = {}
        for c in colours:
            self.t[c] = []
            for k in scales:
                rgb, a, ox, oy = template(sp, c, sx * k, sy * k, blur, parts)
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


def anchor_mean(img: np.ndarray, m: np.ndarray, ox: float, oy: float) -> np.ndarray:
    """Mean of img under mask m placed at each anchor (same layout as Detector.maps)."""
    H, W = img.shape
    th, tw = m.shape
    ip = np.pad(img.astype(np.float32), ((th, th), (tw, tw)))
    r = cv2.matchTemplate(ip, m.astype(np.float32), cv2.TM_CCORR) / max(float(m.sum()), 1.0)
    ys, xs = np.mgrid[0:H, 0:W]
    ty, tx = (ys + oy + th).astype(int), (xs + ox + tw).astype(int)
    ok = (ty >= 0) & (tx >= 0) & (ty < r.shape[0]) & (tx < r.shape[1])
    out = np.zeros((H, W), np.float32)
    out[ok] = r[ty[ok], tx[ok]]
    return out


# body colours of the sprites (normalised r, g, b), from data/game/dive_sprites.npz medians
BODY_CHROMA = {"red": (0.646, 0.177, 0.177), "yellow": (0.489, 0.443, 0.068), "blue": (0.112, 0.112, 0.776)}


def peaks(resp: np.ndarray, thr: float = 0.35, radius: int = 4, max_n: int = 60):
    """Local maxima above thr: list of (x, y, value), strongest first."""
    k = 2 * radius + 1
    dil = cv2.dilate(resp, np.ones((k, k), np.uint8))
    ys, xs = np.nonzero((resp >= dil) & (resp > thr))
    v = resp[ys, xs]
    o = np.argsort(-v)[:max_n]
    return [(int(xs[i]), int(ys[i]), float(v[i])) for i in o]


# ---------------------------------------------------------------- scoring states against detections

def _det_kernel(parallel: bool = True):
    import numba as nb

    @nb.njit(parallel=parallel, fastmath=True, cache=True)
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


def _det_kernel2(parallel: bool = True):
    """As _det_kernel, plus a reverse term: every detection (sprite centre, group) earns
    v * exp(-d^2 / 2 sigma^2), d = distance to the nearest predicted Pikmin of its group in that frame."""
    import numba as nb

    @nb.njit(parallel=parallel, fastmath=True, cache=True)
    def score(states, A, C, base, csl, idx3, u0, v0, sx, sy, v100, gu, gv, nslot, O,
              grp, offx, offy, D, nD, back_w, inv2s2, late_w, out):
        P = A.shape[0]
        N = nslot.shape[0]
        H, W = O.shape[2], O.shape[3]
        F = D.shape[0]
        for k in nb.prange(states.shape[0]):
            s = states[k]
            tot = 0.0
            pu = np.full((P, F), np.nan, np.float32)
            pv = np.full((P, F), np.nan, np.float32)
            pw = np.ones((P, F), np.float32)
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
                    pu[p, sl] = u + offx[c]
                    pv[p, sl] = v + offy[c]
                    w = late_w if state >= 4 else 1.0
                    pw[p, sl] = w
                    xi = int(u + 0.5)
                    yi = int(v + 0.5)
                    if xi >= 0 and yi >= 0 and xi < W and yi < H:
                        tot += w * O[c, sl, yi, xi]
            back = 0.0
            for f in range(F):
                for j in range(nD[f]):
                    x = D[f, j, 0]
                    y = D[f, j, 1]
                    g = int(D[f, j, 3])                # bitmask of the groups this detection may be
                    best = 1e30
                    bw = 1.0
                    for p in range(P):
                        if ((g >> grp[csl[p]]) & 1) == 0:
                            continue
                        a = pu[p, f]
                        if a != a:
                            continue
                        dd = (a - x) * (a - x) + (pv[p, f] - y) * (pv[p, f] - y)
                        if dd < best:
                            best = dd
                            bw = pw[p, f]
                    if best < 1e29:
                        back += bw * D[f, j, 2] * np.exp(-best * inv2s2)
            out[k] = tot + back_w * back
    return score


_DET = {}


class DetScorer:
    """Detection maps of one dive and a compiled scorer of states against them."""

    def __init__(self, rd, counts, sp: dict, sx: float, sy: float, blur: float = 1.2, parts=("body", "flower"),
                 back_w: float = 0.0, sigma: float = 3.0, det_thr: float = 0.3, colour_body: bool = False,
                 colour_floor: float = 0.3, tau: float = 0.15, fade_thr: float = 0.45):
        self.rd, self.counts = rd, counts
        self._blur = blur
        self.colours = [c for k, c in enumerate(cd.COLOURS) if counts[k]]
        self.det = Detector(sp, self.colours, sx, sy, parts=parts)
        self.frames = list(rd.frames)
        maps = [self.det.maps(rd.raw[f], rd.bg) for f in self.frames]
        self.O = np.stack([np.stack([cv2.GaussianBlur(np.maximum(m[c], 0), (0, 0), blur) for m in maps])
                           for c in self.colours]).astype(np.float32)
        self.raw_maps = maps
        # fades (most of the crop changed at once) carry no Pikmin positions, only false detections
        self.fade = np.array([float((np.abs(rd.raw[f] - rd.bg).sum(2) > 45).mean()) > fade_thr for f in self.frames])
        self.O[:, self.fade] = 0
        self.parts = tuple(parts)
        self.back_w, self.sigma = back_w, sigma
        self.B = None
        ryb = [c for c in self.colours if c in BODY_CHROMA]
        if colour_body and self.parts == ("flower",) and len(ryb) >= 2:
            self._body_colour(sp, sx, sy, ryb, blur, colour_floor, tau)
        self.set_detections(det_thr)

    def _body_colour(self, sp, sx, sy, ryb, blur, floor, tau):
        """Red, yellow and blue share a flower: weight each one's flower map by how well the pixels
        under its body (at that anchor) match its body colour, counting only pixels that differ from
        the background. B[colour][frame] in 0..1."""
        self.B = {c: [] for c in ryb}
        tm = {}
        for c in ryb:
            rgb, a, ox, oy = template(sp, c, sx, sy, 0.6, parts=("body",))
            tm[c] = ((a > 0.5).astype(np.float32), ox, oy)
        for f in self.frames:
            fr = self.rd.raw[f]
            ch = fr[..., ::-1] / np.maximum(fr.sum(2, keepdims=True), 1.0)      # BGR -> normalised RGB
            changed = (np.abs(fr - self.rd.bg).sum(2) > 45).astype(np.float32)
            for c in ryb:
                sim = np.exp(-((ch - np.array(BODY_CHROMA[c], np.float32)) ** 2).sum(2) / tau ** 2) * changed
                m, ox, oy = tm[c]
                self.B[c].append(anchor_mean(sim, m, ox, oy))
        for k, c in enumerate(self.colours):
            if c in self.B:
                w = floor + (1 - floor) * np.clip(np.stack(self.B[c]) * 2.0, 0, 1)
                raw = np.stack([np.maximum(m[c], 0) for m in self.raw_maps]) * w
                self.O[k] = np.stack([cv2.GaussianBlur(x, (0, 0), self._blur) for x in raw])
                self.O[k, self.fade] = 0

    def set_detections(self, thr: float = 0.3, groups=None):
        """Detections as (centre x, centre y, value, group) per frame. Centre = the sprite centre at
        scale 1 (anchor + off[colour slot]). `groups` maps colour -> group key; by default, with
        flower-only templates, red, yellow and blue look the same and form one group, detected once
        (from the first of them)."""
        flower_only = self.parts == ("flower",)
        if groups is None:
            groups = {c: ("ryb" if flower_only and c in ("red", "yellow", "blue") else c) for c in self.colours}
        gid, self.grp = {}, np.zeros(len(self.colours), np.int64)
        for k, c in enumerate(self.colours):
            self.grp[k] = gid.setdefault(groups[c], len(gid))
        self.offx = np.zeros(len(self.colours), np.float32)
        self.offy = np.zeros(len(self.colours), np.float32)
        for k, c in enumerate(self.colours):
            rgb, m, ox, oy, sc = min(self.det.t[c], key=lambda x: abs(x[4] - 1.0))
            self.offx[k], self.offy[k] = ox + m.shape[1] / 2, oy + m.shape[0] / 2
        if self.B is not None:               # body colour known: every colour its own group
            self.grp = np.arange(len(self.colours), dtype=np.int64)
        first = {}
        for k in range(len(self.colours)):
            first.setdefault(int(self.grp[k]), k)
        ryb_k = [k for k, c in enumerate(self.colours) if self.B is not None and c in self.B]
        dets = []
        for fi, m in enumerate(self.raw_maps):
            fr = []
            if self.fade[fi]:
                dets.append(fr)
                continue
            for g, k in first.items():
                if ryb_k and k in ryb_k and k != ryb_k[0]:
                    continue                  # one detection pass for the shared flower
                for x, y, v in peaks(m[self.colours[k]], thr, radius=3, max_n=120):
                    cx, cy = x + self.offx[k], y + self.offy[k]
                    mask = 1 << g
                    if ryb_k and k in ryb_k:  # which of red/yellow/blue the body under it matches
                        ev = []
                        for kk in ryb_k:
                            ax, ay = int(round(cx - self.offx[kk])), int(round(cy - self.offy[kk]))
                            b = self.B[self.colours[kk]][fi]
                            ev.append(b[ay, ax] if 0 <= ay < b.shape[0] and 0 <= ax < b.shape[1] else 0.0)
                        top = max(ev)
                        mask = 0
                        for kk, e in zip(ryb_k, ev):
                            if top < 0.15 or e >= top - 0.1:
                                mask |= 1 << int(self.grp[kk])
                    fr.append((cx, cy, v, mask))
            dets.append(fr)
        K = max(1, max(len(f) for f in dets))
        self.D = np.zeros((len(dets), K, 4), np.float32)
        self.nD = np.zeros(len(dets), np.int64)
        for f, fr in enumerate(dets):
            self.nD[f] = len(fr)
            if fr:
                self.D[f, :len(fr)] = np.array(fr, np.float32)

    def inputs(self, g, pikmin=None):
        order = [(c, i) for c in range(5) for i in range(min(self.counts[c], 50))]
        pk = order if pikmin is None else pikmin
        P = len(pk)
        key = tuple(pk)
        if getattr(self, "_fixed_key", None) != key:    # RNG jumps etc. do not depend on the geometry
            A = np.zeros((P, 4), np.uint64)
            C = np.zeros((P, 4), np.uint64)
            base = np.zeros(P, np.float32)
            csl = np.zeros(P, np.int64)
            idx3 = np.zeros(P, np.int64)
            for p, (c, i) in enumerate(pk):
                for d in range(4):
                    a, cc = rng.jump(200 * c + 4 * i + d)
                    A[p, d], C[p, d] = a % (1 << 32), cc % (1 << 32)
                base[p] = -(0.1 * i + 0.5 * c)
                csl[p] = self.colours.index(cd.COLOURS[c])
                idx3[p] = i % 3
            self._fixed_key, self._fixed = key, (A, C, base, csl, idx3)
        A, C, base, csl, idx3 = self._fixed
        x0, y0 = self.rd.region[:2]
        u0 = np.array([g.origins[cd.COLOURS[c]][0] - x0 for c, i in pk], np.float32)
        v0 = np.array([g.origins[cd.COLOURS[c]][1] - y0 for c, i in pk], np.float32)
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
        states = np.ascontiguousarray(np.asarray(states, np.uint64))
        par = len(states) > 64              # one state (geometry fits): no thread start-up
        out = np.empty(len(states), np.float32)
        if self.back_w > 0 or getattr(self, "late_w", 1.0) != 1.0:
            key = ("back", par)
            if key not in _DET:
                _DET[key] = _det_kernel2(par)
            _DET[key](states, *self.inputs(g, pikmin), self.O, self.grp, self.offx, self.offy, self.D, self.nD,
                      np.float32(self.back_w), np.float32(1.0 / (2 * self.sigma ** 2)),
                      np.float32(getattr(self, "late_w", 1.0)), out)
            return out
        if par not in _DET:
            _DET[par] = _det_kernel(par)
        _DET[par](states, *self.inputs(g, pikmin), self.O, out)
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

    def shift_family(self, g, state: int, span: int = 3, step: float = 0.05, half: float = 0.8):
        """Score state and its shifts (state -+ 4j draws) with the geometry held fixed except f0.

        A shift by 4j draws hands Pikmin i the draws of Pikmin i+j, leaving 0.1j timer units
        (0.667j frames) earlier; with f0 moved to compensate, most of the dive is identical and the
        scores differ only by what tells them apart (each colour's first and last Pikmin, the i%3
        landing offset). Refitting every member separately adds fit noise of the same size, so here
        only f0 is searched, on a grid around the expected value. Returns [(score, state, f0)] for
        j = -span..span."""
        from .. import rng as _rng
        out = []
        for j in range(-span, span + 1):
            m = _rng.next_seed(state, 4 * j) if j >= 0 else _rng.prev_seed(state, -4 * j)
            st = np.array([m], np.uint64)
            c0 = g.f0 + 0.1 * j / 0.15
            best = (-1e30, c0)
            for f0 in np.arange(c0 - half, c0 + half + 1e-9, step):
                v = float(self.score(g.copy(f0=float(f0)), st)[0])
                if v > best[0]:
                    best = (v, float(f0))
            out.append((best[0], m, best[1]))
        return out

    def resolve_family(self, g, state: int, span: int = 3, iters: int = 4, log=None):
        """Pick the best of state -+ 4j draws (j <= span). A geometry fitted to a shifted member is
        biased towards that member, so: fit the geometry to the current pick, score the whole family
        under every geometry fitted so far (f0 searched per member), take each member's best, and
        refit at the new pick until it stops changing. Returns (state, geometry, {state: score})."""
        from .. import rng as _rng
        members = [_rng.next_seed(state, 4 * j) if j >= 0 else _rng.prev_seed(state, -4 * j)
                   for j in range(-span, span + 1)]
        geoms = {}
        cur = state
        best = {}
        for it in range(iters):
            if cur in geoms:
                break
            geoms[cur], _ = self.fit(g if not geoms else geoms[max(geoms, key=lambda s: best.get(s, -1e30))], cur)
            for m in members:
                st = np.array([m], np.uint64)
                k = members.index(m) - members.index(cur)
                gc = geoms[cur]
                for f0 in gc.f0 + np.arange(-3, 3.01, 0.1):   # the score steps where f0 crosses a frame time
                    v = float(self.score(gc.copy(f0=float(f0)), st)[0])
                    if v > best.get(m, -1e30):
                        best[m] = v
            cur = max(members, key=lambda s: best[s])
            if log:
                log(f"    family iter {it}: pick {members.index(cur) * 4 - 4 * span:+d} {cur:08X} "
                    + " ".join(f"{best[s]:.1f}" for s in members))
        gbest = geoms.get(cur) or self.fit(g, cur)[0]
        return cur, gbest, best

    def resolve_shift(self, g, state: int, span: int = 3, lead: int = 3, log=None):
        """Choose among state and its one-Pikmin shifts (state -+ 4j draws, j <= span).

        A shift by 4 draws gives Pikmin i the draws of Pikmin i-1 and delays it by 0.1 timer units,
        which a start-frame fit absorbs: the dives look almost the same. What differs is mainly each
        colour's first Pikmin (it leaves first and is drawn on top). Each member is refit with the
        full score, then judged by the forward score of the first `lead` Pikmin of each colour.
        Returns (best state, its geometry, [(lead score, full score, state)])."""
        from .. import rng as _rng
        used = [cd.COLOURS.index(c) for c in self.colours]
        pk = [(c, i) for c in used for i in range(min(lead, self.counts[c]))]
        res = []
        for j in range(-span, span + 1):
            m = _rng.next_seed(state, 4 * j) if j >= 0 else _rng.prev_seed(state, -4 * j)
            gm, v = self.fit(g, m)
            bw = self.back_w
            self.back_w = 0.0
            lv = float(self.score(gm, np.array([m], np.uint64), pikmin=pk)[0])
            self.back_w = bw
            res.append((lv, v, m, gm))
            if log:
                log(f"    shift {4 * j:+d}: {m:08X} lead {lv:.2f} full {v:.1f}")
        best = max(res, key=lambda x: x[0])
        return best[2], best[3], [(lv, v, m) for lv, v, m, gm in res]

    def fit(self, g, state: int, slack: float = 6.0, f0_slack: float = 3.0, rounds: int = 3,
            f0_scan: bool = False):
        """Maximise the score of one state over the geometry (Powell).

        The video shows the dive after floor(frame - f0) updates, so the score is a step function of
        f0 and Powell can stall on it. With f0_scan, f0 is scanned in 0.1-frame steps over the slack
        and alternated with Powell over the other parameters: each state reaches a higher score, but
        so do wrong states, and on cmal04 blind reads fell from 7 to 4 of 13 correct, so it is off
        by default."""
        if not f0_scan:
            return self._fit_powell(g, state, slack, f0_slack)
        from scipy.optimize import minimize
        t0 = np.array(cd.geometry_vector(g), float)
        used = [cd.COLOURS.index(c) for c in self.colours]
        act = [i for i in [0, 1, 3, 4, 5] + [6 + 2 * c + k for c in used for k in (0, 1)]
               if i not in getattr(self, "fixed", ())]     # e.g. (0, 1, 3): scale and v100 known per video
        lo, hi = t0.copy(), t0.copy()
        lo[:2] *= 0.9; hi[:2] *= 1.1
        lo[2] -= f0_slack; hi[2] += f0_slack
        lo[3:] -= slack; hi[3:] += slack
        st = np.array([state], np.uint64)
        cur = t0.copy()

        def sc(th):
            return float(self.score(cd.geometry_from_vector(np.clip(th, lo, hi)), st)[0])

        f0s = t0[2] + np.arange(-f0_slack, f0_slack + 1e-9, 0.1)   # frame times are fractional
        best = -1e30
        for rnd in range(rounds):
            prev = cur[2]
            vals = []
            for f in f0s:
                th = cur.copy()
                th[2] = f
                vals.append(sc(th))
            cur[2] = f0s[int(np.argmax(vals))]

            def fun(x, base=cur.copy()):
                th = base.copy()
                th[act] = x
                return -sc(th)

            r = minimize(fun, cur[act], method="Powell", options=dict(maxfev=3000, xtol=0.05, ftol=1e-6))
            cur[act] = r.x
            cur = np.clip(cur, lo, hi)
            v = -float(r.fun)
            if rnd > 0 and cur[2] == prev and v <= best + 1e-6:
                best = max(best, v)
                break
            best = max(best, v)
        return cd.geometry_from_vector(cur), sc(cur)

    def _fit_powell(self, g, state: int, slack: float = 6.0, f0_slack: float = 3.0):
        from scipy.optimize import minimize
        t0 = np.array(cd.geometry_vector(g), float)
        used = [cd.COLOURS.index(c) for c in self.colours]
        act = [i for i in [0, 1, 2, 3, 4, 5] + [6 + 2 * c + k for c in used for k in (0, 1)]
               if i not in getattr(self, "fixed", ())]
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
