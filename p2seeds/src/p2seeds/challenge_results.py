"""Read the Challenge Mode results-screen score roll and recover the global RNG state.

After a challenge stage the results screen rolls four counters (pokos, Pikmin stock, time
bonus, total). Every game frame, for each counter in that order and each of its digits from
the ones digit up, a digit that is not locked yet shows `randInt(9) + 1` from the global RNG
(`TChallengeResultCounter::update`, plugProjectMorimuraU/challengeResult2D.cpp). Low digits
lock first, one at a time, every `_1C` frames after the counter's onyon arrives (2 frames in
every run looked at). So a clean frame shows up to ~14 consecutive draws, and following the
roll to its end pins the RNG position exactly.

Observed details the tracker models:
- The frame in which a counter's last digit locks still draws that digit, but its picture
  keeps the previous frame's digits; the final value shows from the next frame on.
- Lock timing is exact: once a counter's second lock is seen, the rest follow every L frames.
  This decides the end when the last random digit happens to equal the final one.
- Captures repeat frames (pixel-identical) and drop frames; a repeat is usually made up by a
  drop a frame or two later.
- 2-player runs show the odd extra RNG call between two frames (allowed, with a penalty).
- The Switch port (Pikmin 2 HD) does not follow this RNG: its digits read fine but no state
  explains them.

Pipeline (`read_results`):

1. One sequential pass over the video. Frames where a large part of the picture is the
   results screen's blue are buffered; each buffered run is registered against a reference
   panel (anisotropic scale + shift, so 4:3 GC, 16:9 Wii/Wii U and any capture crop work; the
   layout is the same in English and Japanese) and rejected if it does not match.
2. The panel is warped to canonical coordinates; each counter's digit slots (right-aligned,
   squeezed when there are more digits than the box holds, `og::Screen::CallBack_CounterRV`)
   are read by template matching against the 0-9 templates in data/challenge_digits.
3. An early frame's rolling digits (plus the next frames' when few digits still roll, e.g. a
   video that starts mid-roll) are solved by lattice enumeration (each digit bounds the
   15-bit rand to a 1/9 interval; `lattice.box_points`), and the solution is confirmed by the
   next frames.
4. From that anchor, a Viterbi search over (RNG position, locked digits and lock timers per
   counter) follows the roll frame by frame: rolled digits must match the RNG digit stream,
   locked ones the final values. The final RNG position of the best path is the end of the
   roll; `end_margin` is how much worse the best path ending anywhere else scores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from . import rng
from .lattice import box_points

DATA = Path(__file__).parent / "data" / "challenge_digits"
M = 1 << 31

# canonical panel: the 4:3 GC game picture of the reference frame (468 x 307 px at 360p)
CANON_W, CANON_H = 468, 307
K = 1                        # digits are read at K x the canonical scale
TW, TH = 22, 25              # template size (canonical K scale)
PAD_X, PAD_Y = 4, 3          # search slack around a slot

COUNTERS = ("pokos", "pikmin", "time", "total")   # draw order
# right-most digit centre (x, y) and digit pitch in canonical px; max digits
GEOM = {
    "pokos": dict(x=143.25, y=162.0, pitch=27.75, maxn=5),
    "pikmin": dict(x=267.25, y=162.0, pitch=27.0, maxn=4),
    "time": dict(x=402.5, y=162.0, pitch=27.5, maxn=5),
    "total": dict(x=292.75, y=108.5, pitch=28.0, maxn=5),
}
SQUEEZE = (1.0, 0.92, 0.85, 0.78, 0.72)

MIN_DIGIT_SCORE = 0.55       # below this a slot is treated as unreadable
REG_MIN = 0.80               # registration NCC needed to call it a results screen


# --------------------------------------------------------------------------- RNG digits

def digit_of_state(s: int) -> int:
    return ((s >> 16) & 0x7FFF) * 9 // 32768 + 1


def digit_stream(s0: int, n: int) -> np.ndarray:
    """Digits of the draws whose states are s0, next(s0), next^2(s0), ... (n of them)."""
    st = np.empty(n, np.uint64)
    st[0] = s0 & rng.MASK32
    if n > 1:
        st[1:] = rng.forward_states(s0, n - 1)
    return (((st >> np.uint64(16)) & np.uint64(0x7FFF)) * np.uint64(9) // np.uint64(32768) + np.uint64(1)).astype(np.int8)


def _state_box(d: int) -> tuple[int, int]:
    lo_r = -(-(d - 1) * 32768 // 9)
    hi_r = -(-d * 32768 // 9) - 1
    return lo_r << 16, (hi_r << 16) | 0xFFFF


def solve_digits(obs: list[tuple[int, int]], max_nodes: int = 400_000) -> list[int] | None:
    """States s0 (mod 2^31) such that draw i (state next_seed(s0, i)) shows digit d for every
    (i, d) in obs. None if the enumeration is too large (too few digits)."""
    obs = sorted(obs)
    i0 = obs[0][0]
    lo, hi = [], []
    a_row = []
    for i, d in obs:
        a, c = rng.jump(i - i0)
        L, H = _state_box(d)
        a_row.append(a % M)
        lo.append(L - c % M)
        hi.append(H - c % M)
    lo[0], hi[0] = _state_box(obs[0][1])
    n = len(obs)
    gens = [a_row] + [[M if j == t else 0 for j in range(n)] for t in range(1, n)]
    pts = box_points(gens, lo, hi, max_nodes)
    if pts is None:
        return None
    out = set()
    for p in pts:
        x = p[0] % M
        s0 = rng.prev_seed(x, i0) & (M - 1)
        out.add(s0)
    return sorted(out)


# --------------------------------------------------------------------------- templates

@lru_cache(maxsize=1)
def panel_reference() -> np.ndarray:
    ref = cv2.imread(str(DATA / "panel.png"), cv2.IMREAD_GRAYSCALE)
    if ref is None:
        raise FileNotFoundError(DATA / "panel.png")
    return _prep_reg(ref)


@lru_cache(maxsize=1)
def digit_templates() -> list[tuple[int, np.ndarray]]:
    out = []
    for p in sorted(DATA.glob("d*_*.png")):
        d = int(p.stem[1])
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE).astype(np.float32)
        out.append((d, img))
    if not out:
        raise FileNotFoundError(f"no digit templates in {DATA}")
    return out


# --------------------------------------------------------------------------- registration

def _prep_reg(g: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(g.astype(np.float32), (0, 0), 1.5)


@dataclass
class Placement:
    score: float
    sx: float      # video px per canonical px
    sy: float
    x: float       # video position of the canonical panel's top-left corner
    y: float

    def matrix(self) -> np.ndarray:
        return np.array([[self.sx / K, 0, self.x], [0, self.sy / K, self.y]], np.float32)


def _match_at(G: np.ndarray, R: np.ndarray, sx: float, sy: float, region=None):
    w = int(round(R.shape[1] * sx))
    h = int(round(R.shape[0] * sy))
    if region is None:
        xa, ya, sub = 0, 0, G
    else:
        xa, ya, xb, yb = region
        xa, ya = max(0, xa), max(0, ya)
        sub = G[ya:yb + h, xa:xb + w]
    if sub.shape[0] < h or sub.shape[1] < w or w < 8 or h < 8:
        return -1.0, 0, 0
    T = cv2.resize(R, (w, h), interpolation=cv2.INTER_AREA)
    r = cv2.matchTemplate(sub, T, cv2.TM_CCOEFF_NORMED)
    _, mv, _, ml = cv2.minMaxLoc(r)
    return float(mv), xa + ml[0], ya + ml[1]


def register(gray: np.ndarray, hint: Placement | None = None) -> Placement:
    """Find the results panel in a gray frame (coarse grid search unless `hint`, then refine)."""
    R = panel_reference()
    G = _prep_reg(gray)
    if hint is None:
        ds = 0.5
        Gs = cv2.resize(G, None, fx=ds, fy=ds, interpolation=cv2.INTER_AREA)
        Rs = cv2.resize(R, None, fx=ds, fy=ds, interpolation=cv2.INTER_AREA)
        best = (-1.0, 1.0, 1.0, 0, 0)
        for sy in np.arange(0.5, 1.6, 0.025):
            for ar in np.arange(0.8, 1.5, 0.025):
                sx = sy * ar
                mv, x, y = _match_at(Gs, Rs, sx, sy)
                if mv > best[0]:
                    best = (mv, sx, sy, x / ds, y / ds)
        _, sx0, sy0, x0, y0 = best
        span, step = 0.03, 0.006
    else:
        sx0, sy0, x0, y0 = hint.sx, hint.sy, hint.x, hint.y
        span, step = 0.012, 0.006
    best = Placement(-1.0, sx0, sy0, x0, y0)
    for sy in np.arange(sy0 - span, sy0 + span + 1e-9, step):
        for sx in np.arange(sx0 - span, sx0 + span + 1e-9, step):
            reg = (int(x0) - 8, int(y0) - 8, int(x0) + 8, int(y0) + 8)
            mv, x, y = _match_at(G, R, sx, sy, reg)
            if mv > best.score:
                w = int(round(R.shape[1] * sx))
                h = int(round(R.shape[0] * sy))
                best = Placement(mv, w / R.shape[1], h / R.shape[0], float(x), float(y))
    return best


def rectify(gray: np.ndarray, pl: Placement) -> np.ndarray:
    return cv2.warpAffine(gray, pl.matrix(), (CANON_W * K, CANON_H * K),
                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP).astype(np.float32)


# --------------------------------------------------------------------------- digit reading

def slot_center(counter: str, i: int, squeeze: float) -> tuple[float, float]:
    g = GEOM[counter]
    return g["x"] - i * g["pitch"] * squeeze, g["y"]


def slot_crop(canon: np.ndarray, counter: str, i: int, squeeze: float, pad: bool = True) -> np.ndarray:
    cx, cy = slot_center(counter, i, squeeze)
    px, py = (PAD_X, PAD_Y) if pad else (0, 0)
    hw = (TW / 2 + px) * squeeze
    x0, x1 = int(round(cx - hw)), int(round(cx + hw))
    y0, y1 = int(round(cy - TH / 2 - py)), int(round(cy + TH / 2 + py))
    x0c, x1c = max(0, x0), min(canon.shape[1], x1)
    crop = canon[y0:y1, x0c:x1c]
    if x0c != x0 or x1c != x1:
        crop = cv2.copyMakeBorder(crop, 0, 0, x0c - x0, x1 - x1c, cv2.BORDER_REPLICATE)
    return cv2.resize(crop, (TW + 2 * px, TH + 2 * py), interpolation=cv2.INTER_AREA)


@lru_cache(maxsize=1)
def _template_matrix():
    tpls = digit_templates()
    mat = np.stack([_unit(t.ravel()) for _, t in tpls], axis=1)        # (TH*TW, nT)
    labels = np.array([d for d, _ in tpls])
    return mat, labels


def _unit(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.float32) - v.mean()
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def _slot_scores(crops: list[np.ndarray]) -> np.ndarray:
    """Best NCC of each digit 0-9 in each padded crop (same as matchTemplate CCOEFF_NORMED)."""
    mat, labels = _template_matrix()
    wins = np.stack([np.lib.stride_tricks.sliding_window_view(c, (TH, TW)).reshape(-1, TH * TW) for c in crops])
    wins = wins - wins.mean(axis=2, keepdims=True)
    wins /= np.maximum(np.linalg.norm(wins, axis=2, keepdims=True), 1e-6)
    sc = (wins @ mat).max(axis=1)                                     # (n_crops, nT)
    out = np.full((len(crops), 10), -1.0, np.float32)
    for d in range(10):
        m = labels == d
        if m.any():
            out[:, d] = sc[:, m].max(axis=1)
    return out


def read_slots(canon: np.ndarray, slots: list[tuple[str, int, float]]) -> list[tuple[int, float, float]]:
    """(best digit, its NCC, best NCC of any other digit) for each (counter, index, squeeze)."""
    sc = _slot_scores([slot_crop(canon, c, i, sq) for c, i, sq in slots])
    out = []
    for row in sc:
        o = np.argsort(-row)
        out.append((int(o[0]), float(row[o[0]]), float(row[o[1]])))
    return out


def read_slot(canon: np.ndarray, counter: str, i: int, squeeze: float) -> tuple[int, float, float]:
    return read_slots(canon, [(counter, i, squeeze)])[0]


@dataclass
class Layout:
    n: dict           # counter -> number of digits
    squeeze: dict     # counter -> squeeze factor

    @property
    def total_digits(self) -> int:
        return sum(self.n.values())


def choose_layout(canons: list[np.ndarray]) -> Layout:
    """Number of digits and squeeze of each counter, by template fit over several frames."""
    n_out, sq_out = {}, {}
    for c in COUNTERS:
        g = GEOM[c]
        best = None
        for sq in SQUEEZE:
            slots = [(c, i, sq) for i in range(g["maxn"])]
            sc = np.zeros(g["maxn"])
            for cv in canons:
                sc += np.array([v for _, v, _ in read_slots(cv, slots)]) - 0.5
            cum = np.cumsum(sc) / len(canons)
            for n in range(1, g["maxn"] + 1):
                # squeeze only happens once the digits overflow the box
                if sq < 1.0 and n < 4:
                    continue
                val = cum[n - 1]
                if best is None or val > best[0] + 1e-9:
                    best = (val, n, sq)
        n_out[c], sq_out[c] = best[1], best[2]
    return Layout(n_out, sq_out)


def read_frame(canon: np.ndarray, lay: Layout) -> dict:
    """Per counter, list of (digit, score, margin) from the ones digit up."""
    slots = [(c, i, lay.squeeze[c]) for c in COUNTERS for i in range(lay.n[c])]
    res = read_slots(canon, slots)
    out = {c: [] for c in COUNTERS}
    for (c, _, _), (d, v, v2) in zip(slots, res):
        out[c].append((d, v, v - v2))
    return out


# --------------------------------------------------------------------------- blended captures
#
# Some Wii (New Play Control!) captures blend the two fields of an interlaced signal, and the
# game's 30 Hz frames straddle field pairs, so every video frame is a 50/50 overlay of game
# frames g and g+1 (the next video frame shows g+1 and g+2). Whether a results screen is blended
# depends on the field phase, which changes between screens in the same video. A 60 fps upload
# of such a capture shows each blended picture twice; it does not undo the blend.

BLEND_GAIN = 0.04            # pair templates must beat single digits by this much (mean NCC)
BLEND_MAX_MISMATCH = 0.30    # blended tracks run at 16-25% mismatched digits; far above is a lost track


@lru_cache(maxsize=1)
def _pair_matrix():
    """Centred single templates, and for every blend of two of them (same template set) the
    indices and the norm of the sum: NCC(w, ta + tb) = (w.ta + w.tb) / |ta + tb| for a
    normalised window w, so blends are scored from the single-template dot products."""
    tpls = digit_templates()
    cent = [t.ravel().astype(np.float32) - t.mean() for _, t in tpls]
    by_shape: dict = {}
    for j, (d, t) in enumerate(tpls):
        by_shape.setdefault(t.shape, {}).setdefault(d, []).append(j)
    ia, ib, norms, labels = [], [], [], []
    for group in by_shape.values():
        for a in range(10):
            for b in range(a, 10):
                for ja in group.get(a, []):
                    for jb in group.get(b, []):
                        ia.append(ja)
                        ib.append(jb)
                        norms.append(max(float(np.linalg.norm(cent[ja] + cent[jb])), 1e-6))
                        labels.append((a, b))
    return (np.stack(cent, axis=1), np.array(ia), np.array(ib), np.array(norms, np.float32), labels)


def read_pairs(canon: np.ndarray, lay: Layout) -> dict:
    """Per counter, [((lo, hi), score)] from the ones digit up: each slot as a 50/50 blend."""
    cent, ia, ib, norms, labels = _pair_matrix()
    slots = [(c, i, lay.squeeze[c]) for c in COUNTERS for i in range(lay.n[c])]
    crops = [slot_crop(canon, c, i, sq) for c, i, sq in slots]
    wins = np.stack([np.lib.stride_tricks.sliding_window_view(c, (TH, TW)).reshape(-1, TH * TW) for c in crops])
    wins = wins - wins.mean(axis=2, keepdims=True)
    wins /= np.maximum(np.linalg.norm(wins, axis=2, keepdims=True), 1e-6)
    dots = wins @ cent                                              # (slots, windows, templates)
    sc = ((dots[:, :, ia] + dots[:, :, ib]) / norms).max(axis=1)    # (slots, pairs)
    best = sc.argmax(axis=1)
    out = {c: [] for c in COUNTERS}
    for (c, _, _), b, row in zip(slots, best, sc):
        out[c].append((labels[int(b)], float(row[b])))
    return out


def blend_gain(frames: list[Frame], canons: list[np.ndarray], lay: Layout, n: int = 8) -> float:
    """How much better pair templates fit than single digits over the first rolling frames
    (near 0 for a clean capture, about 0.08 for a blended one)."""
    idx = [i for i, f in enumerate(frames) if not f.dup][:n]
    gains = []
    for i in idx:
        single = [v for c in COUNTERS for _, v, _ in frames[i].reading[c]]
        pair = [v for c in COUNTERS for _, v in read_pairs(canons[i], lay)[c]]
        gains.append(np.mean(pair) - np.mean(single))
    return float(np.median(gains)) if gains else 0.0


_blend_kernel = None


def _get_blend_kernel():
    global _blend_kernel
    if _blend_kernel is not None:
        return _blend_kernel
    import numba as nb

    @nb.njit(parallel=True, cache=True)
    def kernel(lo_, hi_, aN, cN, maxbad):
        # lo_, hi_: (frames, N) digit pairs; video frame m shows draws [mN, mN+N) and the next N
        nf, Nn = lo_.shape
        out = np.zeros(64, np.int64)
        cnt = np.zeros(1, np.int64)
        a1 = np.uint64(0x41C64E6D)
        c1 = np.uint64(0x3039)
        msk = np.uint64(0xFFFFFFFF)
        for top in nb.prange(1 << 15):
            d0 = top * 9 // 32768 + 1
            if d0 != lo_[0, 0] and d0 != hi_[0, 0]:
                continue
            for low in range(1 << 16):
                s0 = np.uint64((top << 16) | low)
                bad = 0
                s = s0
                ok = True
                for m in range(nf):
                    for q in range(Nn):
                        sn = (aN * s + cN) & msk
                        d1 = ((s >> np.uint64(16)) & np.uint64(0x7FFF)) * np.uint64(9) // np.uint64(32768) + np.uint64(1)
                        d2 = ((sn >> np.uint64(16)) & np.uint64(0x7FFF)) * np.uint64(9) // np.uint64(32768) + np.uint64(1)
                        if min(d1, d2) != lo_[m, q] or max(d1, d2) != hi_[m, q]:
                            bad += 1
                            if bad > maxbad or (m == 0 and q < 3):   # first 3 slots: exact (speed)
                                ok = False
                                break
                        s = (a1 * s + c1) & msk
                    if not ok:
                        break
                if ok:
                    k = cnt[0]
                    cnt[0] += 1
                    if k < 64:
                        out[k] = s0
        return out[:min(cnt[0], 64)]

    _blend_kernel = kernel
    return kernel


def solve_blended(pairs_frames: list[dict], lay: Layout, maxbad: int = 6) -> list[int]:
    """All states s0 (mod 2^31) for which consecutive blended frames (every digit rolling, the
    first frame's game frame g drawing from s0) show these digit pairs, up to maxbad misreads
    (the first frame's first 3 slots must be read right). Brute force over 2^31 states (numba),
    pruned by the first slot."""
    N = lay.total_digits
    lo = np.array([[p[0][0] for c in COUNTERS for p in pf[c]] for pf in pairs_frames], np.uint64)
    hi = np.array([[p[0][1] for c in COUNTERS for p in pf[c]] for pf in pairs_frames], np.uint64)
    aN, cN = rng.jump(N)
    sols = _get_blend_kernel()(lo, hi, np.uint64(aN), np.uint64(cN), maxbad)
    return sorted({int(s) & (M - 1) for s in sols})


def _pair_hits(pf: dict, stream: np.ndarray, p: int, N: int) -> int:
    flat = [x for c in COUNTERS for x in pf[c]]
    return sum((min(stream[p + q], stream[p + N + q]), max(stream[p + q], stream[p + N + q])) == ab
               for q, (ab, _) in enumerate(flat))


def find_anchor_blend(frames: list[Frame], lay: Layout, max_tries: int = 6, maxbad: int = 6):
    """Anchor for a blended screen: two successive non-repeated frames early in the roll, every
    digit rolling, solved by brute force and confirmed by the next frames' pairs (allowing the
    capture's repeated and dropped frames)."""
    N = lay.total_digits
    nondup = [i for i, f in enumerate(frames) if not f.dup]
    tried = 0
    for pos in range(max(0, len(nondup) - 8)):
        if tried >= max_tries:
            break
        fi, fj = nondup[pos], nondup[pos + 1]
        # a repeat that is not pixel-identical: the same pairs again, no new game frame
        same = sum(a == b for c in COUNTERS for (a, _), (b, _) in zip(frames[fi].pairs[c], frames[fj].pairs[c]))
        if same >= 0.7 * N:
            continue
        tried += 1
        for s0 in solve_blended([frames[fi].pairs, frames[fj].pairs], lay, maxbad):
            stream = digit_stream(s0, N * 20)
            p, ok = N, 0
            for m in range(2, 8):
                hit = None
                for q in (p + N, p + 2 * N, p):
                    if _pair_hits(frames[nondup[pos + m]].pairs, stream, q, N) >= 0.6 * N:
                        hit = q
                        break
                if hit is None:
                    break
                ok += hit != p
                p = hit
            if ok >= 3:
                return fi, s0, tuple(0 for _ in COUNTERS)
    return None


def draw_order(reading: dict) -> list[tuple[int, float, float]]:
    return [x for c in COUNTERS for x in reading[c]]


def reading_str(reading: dict) -> str:
    """Displayed numbers (most significant digit first), '?' for unreadable slots."""
    parts = []
    for c in COUNTERS:
        parts.append("".join(str(d) if v >= MIN_DIGIT_SCORE else "?" for d, v, _ in reversed(reading[c])))
    return " ".join(parts)


# --------------------------------------------------------------------------- roll tracking

MATCH = math.log(9.0)        # rolled digit predicted correctly
MISMATCH = -3.5              # rolled/locked digit contradicts the hypothesis
LOCK_OK = 0.6                # locked digit equals the final value (weak: finals are not random)
SKIP = -4.0                  # a game frame with no video frame (dropped)
SKIP_AFTER_REPEAT = -0.5     # ... right after a repeated video frame (the usual capture glitch)
EXTRA = -4.0                 # per RNG call between frames that is not a digit
REPEAT = -2.0                # a video frame repeating the previous game frame, pixels not identical
MAX_STREAM = 6000


@dataclass
class Frame:
    index: int
    reading: dict
    dup: bool = False          # same picture as the previous video frame
    pairs: dict | None = None  # blended capture: counter -> [((lo, hi) digit pair, score)]


def _blend_emission(fr: Frame, k: tuple, k2: tuple, p: int, stream: np.ndarray, lay: Layout,
                    finals: dict) -> tuple[float, int, int]:
    """Score of a blended video frame: game frame g (first draw at p, locks k) overlaid 50/50
    with game frame g+1 (first draw right after g's draws, locks k2). Each slot is read as an
    unordered digit pair. The lock frame's display quirk is ignored."""
    score, good, bad = 0.0, 0, 0
    p2 = p + _draws(k, lay)
    off1, off2 = p, p2
    for ci, c in enumerate(COUNTERS):
        n = lay.n[c]
        fin = finals.get(c) or [None] * n
        for j in range(n):
            (lo, hi), v = fr.pairs[c][j]
            d1 = fin[j] if j < k[ci] else stream[off1 + j - k[ci]] if off1 + j - k[ci] < len(stream) else None
            d2 = fin[j] if j < k2[ci] else stream[off2 + j - k2[ci]] if off2 + j - k2[ci] < len(stream) else None
            if v < MIN_DIGIT_SCORE or d1 is None or d2 is None:
                continue
            ok = (min(d1, d2), max(d1, d2)) == (lo, hi)
            rolled = j >= k[ci] or j >= k2[ci]
            if ok:
                score += MATCH if rolled else LOCK_OK
                good += rolled
            else:
                score += MISMATCH
                bad += 1
        off1 += max(0, n - k[ci])
        off2 += max(0, n - k2[ci])
    return score, good, bad


def _emission(fr: Frame, k: tuple, finishing: tuple, p: int, stream: np.ndarray, lay: Layout, finals: dict) -> tuple[float, int, int]:
    """Score of a frame given locked counts k (at frame start), which counters complete this
    frame, and RNG position p of its first draw. Returns (score, matches, mismatches)."""
    score, good, bad = 0.0, 0, 0
    off = p
    for ci, c in enumerate(COUNTERS):
        n = lay.n[c]
        row = fr.reading[c]
        kc = k[ci]
        for j in range(n):
            d, v, _ = row[j]
            if v < MIN_DIGIT_SCORE:
                continue
            if finishing[ci] and j >= kc:
                # the frame where a counter's last digit locks still draws, but its picture
                # keeps the previous frame's digits (the final value shows one frame later)
                continue
            if j < kc or kc >= n:
                f = finals[c][j] if finals.get(c) else None
                if f is None:
                    continue
                if d == f:
                    score += LOCK_OK
                else:
                    score += MISMATCH
                    bad += 1
            else:
                q = off + (j - kc)
                if q >= len(stream):
                    return -1e9, 0, 0
                if d == stream[q]:
                    score += MATCH
                    good += 1
                else:
                    score += MISMATCH
                    bad += 1
        if kc < n:
            off += n - kc
    return score, good, bad


def _draws(k: tuple, lay: Layout) -> int:
    return sum(max(0, lay.n[c] - k[ci]) for ci, c in enumerate(COUNTERS))


L_DISAGREE = -3.0            # a counter's lock period differs from another counter's


def _counter_moves(k: int, t: int, L, n: int):
    """Possible (lock, new_t, new_L, penalty) after one drawn frame of a counter.

    t counts the frames drawn since the last lock; L is the lock period (`_1C`), known
    once two locks have been seen. Locks then come exactly every L frames."""
    if k >= n:
        return [(0, t, L)]
    t1 = t + 1
    if k == 0 or t < 0:
        return [(0, 0, L), (1, 0, L)]          # first lock: any time (onyon arrival)
    if L is None:
        return [(0, t1, None), (1, 0, t1)]
    return [(1, 0, L)] if t1 >= L else [(0, t1, L)]


@lru_cache(maxsize=200_000)
def _transitions(k: tuple, t: tuple, L: tuple, ncs: tuple):
    """[(k after, t after, L after, penalty, finishing flags)] for one drawn frame."""
    opts = [_counter_moves(k[i], t[i], L[i], ncs[i]) for i in range(len(k))]
    out = [((), (), ())]
    for o in opts:
        out = [(d + (m[0],), tt + (m[1],), ll + (m[2],)) for d, tt, ll in out for m in o]
    res = []
    for d, tt, ll in out:
        pen = 0.0
        for i in range(len(k)):
            if L[i] is None and ll[i] is not None and any(x != ll[i] for j, x in enumerate(ll) if j != i and x is not None):
                pen += L_DISAGREE
        k2 = tuple(a + b for a, b in zip(k, d))
        fin = tuple(int(k[i] == ncs[i] - 1 and d[i] == 1) for i in range(len(k)))
        res.append((k2, tt, ll, pen, fin))
    return res


@lru_cache(maxsize=10_000)
def _ndraws(k: tuple, ncs: tuple) -> int:
    return sum(max(0, n - kk) for kk, n in zip(k, ncs))


def track(frames: list[Frame], start: int, s0: int, lay: Layout, finals: dict, k0: tuple | None = None,
          beam: int = 32):
    """Viterbi over (RNG position, locked digits, lock timers) from frames[start], whose first
    draw has state s0 and where every digit still rolls. Returns the beam's entries
    (score, state, path) best first; path is a linked list of per-frame tuples
    (frame list index, position, locked, finishing, matches, mismatches)."""
    stream = digit_stream(s0, MAX_STREAM)
    ncs = tuple(lay.n[c] for c in COUNTERS)
    nc = len(COUNTERS)
    zero = tuple(0 for _ in COUNTERS)
    none = tuple(None for _ in COUNTERS)
    # entry: score, (p, k, t, L, repeated), path, last emitted config (pp, kk, fin)
    k_init = tuple(k0) if k0 is not None else zero
    # a counter caught part-way through its locks has an unknown timer phase (t = -1)
    t_init = tuple(-1 if 0 < k_init[i] < ncs[i] else 0 for i in range(nc))
    entries = [(0.0, (0, k_init, t_init, none, 0), None, None)]
    emis_cache: dict = {}

    def emis(fi, pp, kk, fin, k2):
        blended = frames[fi].pairs is not None
        ek = (fi, pp, kk, k2 if blended else fin)
        if ek not in emis_cache:
            emis_cache[ek] = (_blend_emission(frames[fi], kk, k2, pp, stream, lay, finals) if blended
                              else _emission(frames[fi], kk, fin, pp, stream, lay, finals))
        return emis_cache[ek]

    for fi in range(start, len(frames)):
        fr = frames[fi]
        new: dict = {}

        def put(tot, st, path, last):
            if st not in new or new[st][0] < tot:
                new[st] = (tot, st, path, last)

        for score, (p, k, t, L, rep), path, last in entries:
            if fr.dup:
                # identical picture: the capture repeated a frame (and usually drops one later)
                put(score, (p, k, t, L, min(rep + 1, 2)), path, last)
                continue
            if last is not None:
                # same game frame shown again (repeat that is not pixel-identical)
                e, g, b = emis(fi, *last)
                put(score + REPEAT + MISMATCH * b, (p, k, t, L, min(rep + 1, 2)), (path, (fi,) + last[:3] + (0, b)), last)
            nd0 = _ndraws(k, ncs)
            starts = [(p, k, t, L, score, rep)]
            if nd0:
                # up to two dropped game frames before this one: no picture, locks follow the
                # timers. rep counts repeated frames not yet made up by a dropped one (capture
                # jitter), which makes the drop cheap.
                frontier = starts
                for depth in range(2):
                    nxt = []
                    for pp, kk, tk, Lk, sc0, r in frontier:
                        nd = _ndraws(kk, ncs)
                        if not nd:
                            continue
                        sk = SKIP_AFTER_REPEAT if r else SKIP
                        trs = _transitions(kk, tk, Lk, ncs)
                        for k2, tt, ll, pen, _ in (trs if r and depth == 0 else trs[:1]):   # trs[0]: no optional lock
                            nxt.append((pp + nd, k2, tt, ll, sc0 + sk + pen, max(r - 1, 0)))
                    starts = starts + nxt
                    frontier = nxt
                # the odd extra RNG call between two frames (seen in 2-player runs)
                starts += [(pp + 1, kk, tk, Lk, base + EXTRA, r) for pp, kk, tk, Lk, base, r in starts]
            for pp, kk, tk, Lk, base, r in starts:
                nd = _ndraws(kk, ncs)
                for k2, tt, ll, pen, fin in _transitions(kk, tk, Lk, ncs):
                    e, g, b = emis(fi, pp, kk, fin, k2)
                    put(base + e + pen, (pp + nd, k2, tt, ll, r), (path, (fi, pp, kk, fin, g, b)), (pp, kk, fin, k2))
        entries = sorted(new.values(), key=lambda x: -x[0])[:beam]
    return entries


def path_list(path) -> list:
    out = []
    while path is not None:
        path, item = path
        out.append(item)
    return out[::-1]


# --------------------------------------------------------------------------- per screen

@dataclass
class Screen:
    first_frame: int
    last_frame: int
    placement: Placement
    frames: list = field(default_factory=list)   # list[Frame]
    canons: list = field(default_factory=list)


def _rolling_obs(fr: Frame, k: tuple, lay: Layout) -> list[tuple[int, int]]:
    """(draw index within the frame, digit) of the readable rolling digits, given locked counts."""
    out, off = [], 0
    for ci, c in enumerate(COUNTERS):
        n = lay.n[c]
        for j in range(k[ci], n):
            d, v, _ = fr.reading[c][j]
            if v >= MIN_DIGIT_SCORE:
                out.append((off + j - k[ci], d))
        off += max(0, n - k[ci])
    return out


def _locked_at(frames: list[Frame], idx: list[int], lay: Layout) -> tuple:
    """Locked digits per counter: the low slots that keep their value over the frames idx
    (a rolling digit repeats with probability 1/9)."""
    k = []
    for c in COUNTERS:
        kc = 0
        for j in range(lay.n[c]):
            vals = [frames[i].reading[c][j][0] for i in idx]
            top = max(set(vals), key=vals.count)
            if vals.count(top) >= 0.75 * len(vals):
                kc += 1
            else:
                break
        k.append(kc)
    return tuple(k)


def find_anchor(frames: list[Frame], lay: Layout, max_tries: int = 12):
    """An early frame whose rolling digits (with the next frames' if it has few) solve to a
    state confirmed by the following frames. Returns (frame list index, s0, locked counts)."""
    ncs = tuple(lay.n[c] for c in COUNTERS)
    nondup = [i for i, f in enumerate(frames) if not f.dup]
    tried = 0
    for pos, fi in enumerate(nondup):
        window = nondup[pos:pos + 6]
        if len(window) < 3:
            break
        k0 = _locked_at(frames, window, lay)
        N = _ndraws(k0, ncs)
        if N == 0:
            continue
        m = max(1, -(-11 // N))          # frames needed for ~11 digits (35 bits)
        if m > len(window) - 1:
            continue
        obs = []
        for q in range(m):
            obs += [(q * N + i, d) for i, d in _rolling_obs(frames[window[q]], k0, lay)]
        if len(obs) < 9:
            continue
        tried += 1
        if tried > max_tries:
            break
        for s0 in _solve_robust(obs, leave_one_out=tried <= 3):
            if _confirm(frames, window[m - 1], s0, lay, k0, (m - 1) * N, N):
                return fi, s0, k0
    return None


def _solve_robust(obs: list[tuple[int, int]], leave_one_out: bool = True) -> list[int]:
    """Candidate states from the digits, tolerating one misread digit."""
    cands = []
    sol = solve_digits(obs[:12], max_nodes=100_000)
    if sol and len(sol) <= 50:
        cands += sol
    if not cands and leave_one_out:
        # leave out one of the digits (misread) using the others
        for drop in range(min(len(obs), 13)):
            sub = [o for t, o in enumerate(obs[:13]) if t != drop]
            sol = solve_digits(sub[:12], max_nodes=100_000)
            if sol and len(sol) <= 50:
                cands += sol
    out = []
    for s0 in set(cands):
        st = digit_stream(s0, obs[-1][0] + 1)
        bad = sum(1 for i, d in obs if st[i] != d)
        if bad <= 1:
            out.append((bad, s0))
    return [s for _, s in sorted(out)]


def _confirm(frames, fi, s0, lay, k0, p_last, N, need: int = 2) -> bool:
    """The next non-duplicate frames must continue the stream (same locked digits)."""
    stream = digit_stream(s0, p_last + N * 14)
    ok = 0
    p = p_last + N
    for fr in frames[fi + 1:fi + 9]:
        if fr.dup:
            continue
        obs = _rolling_obs(fr, k0, lay)
        if len(obs) < min(4, N):
            return False
        hit = None
        for q in (p, p + N, p - N):
            bad = sum(1 for i, d in obs if stream[q + i] != d)
            if bad <= max(1, len(obs) // 6) if len(obs) >= 6 else bad == 0:
                hit = q
                break
        if hit is None:
            return ok >= 1 and N < 6     # few rolling digits: a lock may already have happened
        if hit == p - N:
            continue          # repeated picture: no new evidence
        ok += 1
        p = hit + N
        if ok >= need:
            return True
    return ok >= 1


def decode_screen(sc: Screen) -> dict:
    frames = sc.frames
    # layout from frames spread over the first half (all digits present)
    sample = sc.canons[: max(3, len(sc.canons) // 2)]
    picks = sample[:: max(1, len(sample) // 8)][:8]
    lay = choose_layout(picks)
    for fr, cv in zip(frames, sc.canons):
        fr.reading = read_frame(cv, lay)
    # final values: majority over the last frames
    finals = {}
    tail = [fr for fr in frames[-25:]]
    for c in COUNTERS:
        digs = []
        for j in range(lay.n[c]):
            vals = [fr.reading[c][j][0] for fr in tail if fr.reading[c][j][1] >= MIN_DIGIT_SCORE]
            digs.append(max(set(vals), key=vals.count) if vals else None)
        finals[c] = digs
    res = dict(first_frame=sc.first_frame, last_frame=sc.last_frame,
               placement=dict(score=round(sc.placement.score, 3), sx=round(sc.placement.sx, 4),
                              sy=round(sc.placement.sy, 4), x=round(sc.placement.x, 1), y=round(sc.placement.y, 1)),
               layout=dict(n=lay.n, squeeze=lay.squeeze),
               final_display=" ".join("".join("?" if d is None else str(d) for d in reversed(finals[c])) for c in COUNTERS))
    gain = blend_gain(frames, sc.canons, lay)
    blended = gain > BLEND_GAIN
    res["blend_gain"] = round(gain, 3)
    res["blended"] = blended
    anc = None
    if blended:
        for fr, cv in zip(frames, sc.canons):
            fr.pairs = read_pairs(cv, lay)
        anc = find_anchor_blend(frames, lay)
        if anc is None:           # misjudged: try as a clean capture
            for fr in frames:
                fr.pairs = None
            res["blended"] = blended = False
    if anc is None:
        anc = find_anchor(frames, lay)
    if anc is None:
        res.update(decoded=False, note="no frame solved to a state confirmed by the next frames")
        return res
    fi, s0, k0 = anc
    entries = track(frames, fi, s0, lay, finals, k0)
    best = entries[0]
    hist = path_list(best[2])

    # the state's position is the RNG position after every draw so far (dropped frames included)
    last_draw_end = best[1][0]
    # best competing path that ends the roll somewhere else
    margin = None
    for ent in entries[1:]:
        if ent[1][0] != last_draw_end:
            margin = best[0] - ent[0]
            break
    per_frame = []
    tot_good = tot_bad = 0
    prev_p = None
    for (fj, p, k, fin, g, b) in hist:
        tot_good += g
        tot_bad += b
        per_frame.append(dict(frame=frames[fj].index, pos=p, state=f"0x{rng.next_seed(s0, p) & (M - 1):08X}",
                              draws=_draws(k, lay), locked=list(k), finishing=list(fin), match=g, mismatch=b,
                              repeat=p == prev_p and _draws(k, lay) > 0))
        prev_p = p
    # first rolling frame: extend backwards with every digit rolling
    first_idx, pos = fi, 0
    N = _ndraws(k0, tuple(lay.n[c] for c in COUNTERS))
    j = fi - 1
    while j >= 0:
        fr = frames[j]
        j -= 1
        if fr.dup:
            continue
        if fr.pairs is not None:
            st = digit_stream(rng.next_seed(s0, (pos - N) % M), 2 * N)
            if _pair_hits(fr.pairs, st, 0, N) >= 0.6 * N:
                pos -= N
                first_idx = j + 1
                continue
            break
        obs = _rolling_obs(fr, k0, lay)
        st = digit_stream(rng.next_seed(s0, (pos - N) % M), N)
        bad = sum(1 for i, d in obs if st[i] != d)
        if len(obs) >= 6 and bad <= max(1, len(obs) // 6):
            pos -= N
            first_idx = j + 1
        else:
            break
    # roll cut off before it ended (screen left early, capture froze): finish it with the timers
    p_end, k_end, t_end, L_end, _ = best[1]
    ncs = tuple(lay.n[c] for c in COUNTERS)
    extrapolated = None
    if _ndraws(k_end, ncs):
        known = [x for x in L_end if x is not None]
        if all(k_end[i] >= 1 or k_end[i] >= ncs[i] for i in range(len(ncs))) and known:
            Lc = [L_end[i] if L_end[i] is not None else max(set(known), key=known.count) for i in range(len(ncs))]
            k, t, pos_x = list(k_end), list(t_end), p_end
            while sum(max(0, n - kk) for kk, n in zip(k, ncs)):
                pos_x += sum(max(0, n - kk) for kk, n in zip(k, ncs))
                for i in range(len(ncs)):
                    if k[i] < ncs[i]:
                        t[i] += 1
                        if t[i] >= Lc[i]:
                            k[i] += 1
                            t[i] = 0
            extrapolated = pos_x
    end_state = rng.next_seed(s0, last_draw_end - 1) & (M - 1)
    res.update(
        decoded=True,
        anchor_frame=frames[fi].index,
        anchor_state=f"0x{s0:08X}",
        anchor_locked=list(k0),
        first_roll_frame=frames[first_idx].index,
        first_roll_state=f"0x{rng.next_seed(s0, pos % M) & (M - 1):08X}",
        first_roll_offset=pos,
        roll_end_index=last_draw_end - 1,
        state_after_last_draw=f"0x{end_state:08X}",
        draws_from_first_roll_frame=last_draw_end - pos,
        frames_tracked=len(hist),
        digits_matched=tot_good,
        digits_mismatched=tot_bad,
        path_score=round(best[0], 1),
        end_margin=None if margin is None else round(margin, 1),
        per_frame=per_frame,
    )
    if _ndraws(k_end, ncs):
        res["roll_complete"] = False
        if extrapolated is not None:
            res["roll_end_index_extrapolated"] = extrapolated - 1
            res["state_after_last_draw_extrapolated"] = f"0x{rng.next_seed(s0, extrapolated - 1) & (M - 1):08X}"
    else:
        res["roll_complete"] = True
    res["note"] = _consistency_note(res, hist, lay)
    rate = tot_bad / max(1, tot_good + tot_bad)
    if blended and rate > BLEND_MAX_MISMATCH:
        res["decoded"] = False
        res["note"] = f"blended track lost ({rate:.0%} of digits mismatched); " + res["note"]
    res["_debug"] = dict(hist=hist, layout=lay, s0=s0, finals=finals)
    return res


def _consistency_note(res, hist, lay) -> str:
    notes = []
    if res["digits_mismatched"] > 0.05 * max(1, res["digits_matched"]):
        notes.append(f"{res['digits_mismatched']} digit mismatches vs {res['digits_matched']} matches")
    if res["end_margin"] is not None and res["end_margin"] < 3.0:
        notes.append(f"roll end ambiguous (a path ending elsewhere scores within {res['end_margin']})")
    if not res.get("roll_complete", True):
        if "roll_end_index_extrapolated" in res:
            notes.append("roll cut off before its end; end extrapolated from the lock timers")
        else:
            notes.append("roll cut off before its end; end unknown")
    return "; ".join(notes) if notes else "ok"


# --------------------------------------------------------------------------- video scan

def blue_fraction(bgr_small: np.ndarray) -> float:
    s = bgr_small.astype(np.int16)
    b, r = s[..., 0], s[..., 2]
    return float(((b - r > 35) & (b > 140)).mean())


def iter_screens(video_path: str, blue_min: float = 0.25, idle_step: int = 3, gap: int = 20,
                 max_len: int = 900, progress=None, start: int = 0, end: int | None = None):
    """Yield (first_frame, gray_frames list[(index, gray)]) for each blue run."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise OSError(f"cannot open {video_path}")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    i = 0
    if start:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        i = start
    buf: list = []
    trailing = 0
    while end is None or i < end:
        if not cap.grab():
            break
        active = bool(buf)
        if active or i % idle_step == 0:
            ok, f = cap.retrieve()
            if ok:
                if f.shape[0] > 540:      # 720p+: the reader works at <= 480p scale
                    f = cv2.resize(f, (640, 360), interpolation=cv2.INTER_AREA)
                small = cv2.resize(f, (160, 90), interpolation=cv2.INTER_AREA)
                if blue_fraction(small) >= blue_min:
                    trailing = 0
                    buf.append((i, cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)))
                elif active:
                    trailing += 1
                    buf.append((i, cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)))
                if buf and (trailing > gap or len(buf) >= max_len):
                    yield buf[: len(buf) - trailing]
                    buf, trailing = [], 0
        if progress and i % 10000 == 0:
            progress(i, n)
        i += 1
    if buf:
        yield buf[: len(buf) - trailing]
    cap.release()


def _is_dup(a: np.ndarray, b: np.ndarray) -> bool:
    """Same picture (capture repeated a frame): no 6x6-px block of the panel changed."""
    d = cv2.resize(np.abs(a - b), (a.shape[1] // 6, a.shape[0] // 6), interpolation=cv2.INTER_AREA)
    return float(d.max()) < 15.0


def process_run(buf, cache: dict) -> Screen | None:
    if len(buf) < 15:
        return None
    mid = buf[len(buf) // 2][1]
    pl = None
    if cache.get("placement") is not None:
        pl = register(mid, cache["placement"])
        if pl.score < REG_MIN:
            pl = None
    if pl is None:
        # the middle frame alone can fall just short (CH27 WR: 0.79 there, 0.85-0.94 elsewhere),
        # so try a few frames across the run and keep the best registration
        for q in (2, 3, 5, 4, 6):
            cand = register(buf[len(buf) * q // 8][1])
            if pl is None or cand.score > pl.score:
                pl = cand
            if pl.score >= REG_MIN:
                break
        if pl.score < REG_MIN:
            return None
        cache["placement"] = pl
    sc = Screen(buf[0][0], buf[-1][0], pl)
    prev = None
    for idx, g in buf:
        cv = rectify(g, pl)
        dup = prev is not None and _is_dup(cv, prev)
        prev = cv
        sc.frames.append(Frame(idx, {}, dup))
        sc.canons.append(cv)
    return sc


def read_results(video_path: str, progress=None, keep_frames: bool = True, start: int = 0,
                 end: int | None = None) -> list[dict]:
    """Every results screen in the video (or in frames [start, end)), with the RNG states read
    from its score roll."""
    out = []
    cache: dict = {}
    for buf in iter_screens(video_path, progress=progress, start=start, end=end):
        sc = process_run(buf, cache)
        if sc is None:
            continue
        res = decode_screen(sc)
        res.pop("_debug", None)
        if not keep_frames:
            res.pop("per_frame", None)
        out.append(res)
    return out
