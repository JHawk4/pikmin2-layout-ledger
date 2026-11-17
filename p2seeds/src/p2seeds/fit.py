"""Fit each letter's starting velocity from its tracked fall.

In pixels, a letter's glyph top is   y = y_floor - s * pos(f)
with f = frame - F0 - delay_frames(i, n) and pos from letters_model. Three
values are shared by every letter: F0 (the frame letter 0 started, fractional
because the video samples the game at an unknown phase), s (pixels per game
unit) and y_floor (pixel row of pos = 0). Each letter adds its velocity v_i.
Everything is fitted together with a robust loss.

Only the free-fall part of each track is used: letters bounce when they hit
the floor, so a track is cut at the first frame where the fall suddenly slows.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from . import letters_model
from .track import Track


@dataclass
class FitResult:
    v: np.ndarray            # per character (nan for spaces / unusable letters)
    sigma: np.ndarray        # 1-sigma uncertainty of v
    n_points: np.ndarray     # free-fall frames used per character
    F0: float
    s: float
    y_floor: float
    rms_px: float            # residual RMS in pixels
    residuals: dict          # index -> (frames, residual px)


BOUNCE_PX = 25.0       # a fall starts well above the settled row; a bounce rises only ~10-20 px


def free_fall(track: Track, min_score: float = 0.55, segment: str = "longest") -> tuple[np.ndarray, np.ndarray]:
    """The letter's fall: the stretch of steadily accelerating downward motion that drops the
    furthest. A stretch ends where the letter stops, bounces, slows (it hit the floor) or jumps
    implausibly (a bad match). Taking the stretch that drops furthest, not the first, keeps
    spurious matches before the fall (something static the template half-matches) and the
    bounces after it from hiding the fall itself. segment="first" is the older rule instead
    (_first_fall), which works better on some captures."""
    if segment == "first":
        return _first_fall(track, min_score)
    ok = (track.score >= min_score) & (track.score < 0.995)
    fr, y = track.frames[ok], track.y[ok]
    segments: list[tuple[list, list]] = []
    keep_f, keep_y = [], []
    prev_dy = None
    for f, yy in zip(fr, y):
        if keep_f:
            gap = f - keep_f[-1]
            if gap <= 0:
                continue
            dy = (yy - keep_y[-1]) / gap
            if (dy <= 0.5                                         # stopped or bouncing
                    or (prev_dy is not None and dy < 0.8 * prev_dy)   # hit the floor during this frame
                    or (prev_dy is not None and dy > prev_dy + 4)):   # implausible jump (bad match)
                segments.append((keep_f, keep_y))
                keep_f, keep_y, prev_dy = [f], [yy], None
                continue
            prev_dy = dy
        keep_f.append(f)
        keep_y.append(yy)
    segments.append((keep_f, keep_y))
    best = max(segments, key=lambda s: (s[1][-1] - s[1][0]) if len(s[1]) > 1 else -1.0)
    if best[1] and best[1][0] > track.rest_y - BOUNCE_PX:
        # starts just above where the letter settles: a bounce, not the fall (whose start was
        # not tracked); leave the letter out rather than fit a bounce as a fall
        return np.array([], float), np.array([], float)
    return np.array(best[0], float), np.array(best[1], float)


def _first_fall(track: Track, min_score: float) -> tuple[np.ndarray, np.ndarray]:
    """The older rule: the track from its start until the letter stops, bounces or slows; a bad
    match restarts it. A letter whose track starts on something static so ends up with too few
    points and is left out of the fit, which keeps doubtful letters out."""
    ok = (track.score >= min_score) & (track.score < 0.995)
    fr, y = track.frames[ok], track.y[ok]
    keep_f, keep_y = [], []
    prev_dy = None
    for f, yy in zip(fr, y):
        if keep_f:
            gap = f - keep_f[-1]
            if gap <= 0:
                continue
            dy = (yy - keep_y[-1]) / gap
            if dy <= 0.5 or (prev_dy is not None and dy < 0.8 * prev_dy):
                break                                     # stopped, bouncing, or hit the floor
            if prev_dy is not None and dy > prev_dy + 4:
                keep_f, keep_y, prev_dy = [f], [yy], None     # implausible jump: restart here
                continue
            prev_dy = dy
        keep_f.append(f)
        keep_y.append(yy)
    return np.array(keep_f, float), np.array(keep_y, float)


PRUNE_RMS = 0.5        # a fit worse than this may drop a letter that is clearly mistracked
MAX_PRUNED = 2


def fit(tracks: list[Track], num_chars: int, s_guess: float, min_points: int = 4,
        min_score: float = 0.55, min_letters: int = 3, segment: str = "longest") -> FitResult:
    """_fit_once, then, while the fit is poor, without the letter that fits worst when it is far
    worse than the rest (a mistracked letter), keeping the refit only when it is better."""
    kw = dict(min_points=min_points, min_score=min_score, min_letters=min_letters, segment=segment)
    best = _fit_once(tracks, num_chars, s_guess, **kw)
    dropped: set[int] = set()
    while best.rms_px > PRUNE_RMS and len(dropped) < MAX_PRUNED:
        per = {i: float(np.sqrt(np.mean(r ** 2))) for i, (_, r) in best.residuals.items() if len(r)}
        if len(per) <= max(min_letters, 6):
            break
        worst = max(per, key=per.get)
        if per[worst] < max(1.0, 3 * float(np.median(list(per.values())))):
            break
        dropped.add(worst)
        try:
            f2 = _fit_once([t for t in tracks if t.index not in dropped], num_chars, s_guess, **kw)
        except ValueError:
            break
        if f2.rms_px >= best.rms_px:
            break
        best = f2
    return best


def _fit_once(tracks: list[Track], num_chars: int, s_guess: float, min_points: int = 4,
              min_score: float = 0.55, min_letters: int = 3, segment: str = "longest") -> FitResult:
    data = []
    for t in tracks:
        f, y = free_fall(t, min_score=min_score, segment=segment)
        if len(f) >= min_points:
            data.append((t.index, f - letters_model.delay_frames(t.index, num_chars), y))
    if len(data) < min_letters:
        raise ValueError("too few letters with a usable fall")
    idx = [d[0] for d in data]
    floor0 = max(t.rest_y for t in tracks)

    # initial F0: letter falls ~ (200 - pos)/s px from start; take the earliest point's
    # implied start using a mid velocity
    def resid(p):
        F0, s, yf = p[:3]
        out = []
        for k, (i, f_rel, y) in enumerate(data):
            f = f_rel - F0
            out.append(y - (yf - s * letters_model.pos(p[3 + k], f)))
        return np.concatenate(out)

    def jac(p):
        F0, s, yf = p[:3]
        rows = []
        for k, (i, f_rel, y) in enumerate(data):
            f = f_rel - F0
            v = p[3 + k]
            J = np.zeros((len(f), len(p)))
            J[:, 0] = -s * (v - 0.5 - f)           # d/dF0: pos' = v - 0.5 - f, and df/dF0 = -1
            J[:, 1] = letters_model.pos(v, f)       # d/ds
            J[:, 2] = -1.0                          # d/dy_floor
            J[:, 3 + k] = s * f                     # d/dv
            rows.append(J)
        return np.vstack(rows)

    # With s and y_floor fixed, each letter's v is linear least squares for a given
    # F0, so scan F0 cheaply first and start the full fit from the best value.
    def sse_at(F0):
        tot = 0.0
        for i, f_rel, y in data:
            f = f_rel - F0
            pos_meas = (floor0 - y) / s_guess
            target = pos_meas - letters_model.START_POS + f * (f + 1) / 2   # = v * f
            v = float(np.dot(f, target) / max(np.dot(f, f), 1e-9))
            tot += float(np.sum(np.minimum((target - v * f) ** 2, 25.0)))
        return tot

    # F0 comes before the earliest point seen (the letter had started) and not long before it
    # (letters fall into view within a few dozen frames). A fixed range missed captures with a
    # long blank lead-in, where the letters start late in the clip.
    first = min(float(f_rel.min()) for _, f_rel, _ in data)
    grid = np.arange(min(-40.0, first - 70), max(60.0, first + 5), 0.5)
    F0_start = grid[int(np.argmin([sse_at(F0) for F0 in grid]))]
    lo = np.r_[min(-60.0, first - 90), s_guess * 0.7, floor0 - 30, np.full(len(data), -0.5)]
    hi = np.r_[max(80.0, first + 20), s_guess * 1.3, floor0 + 30, np.full(len(data), 5.5)]
    best = None
    for F0 in (F0_start - 1, F0_start, F0_start + 1):
        p0 = np.r_[F0, s_guess, floor0, np.full(len(data), 2.5)]
        r = least_squares(resid, p0, jac=jac, bounds=(lo, hi), loss="soft_l1", f_scale=1.0)
        if best is None or r.cost < best.cost:
            best = r
    p = best.x
    res = resid(p)
    rms = float(np.sqrt(np.mean(np.minimum(res ** 2, 9.0))))

    v = np.full(num_chars, np.nan)
    sigma = np.full(num_chars, np.nan)
    npts = np.zeros(num_chars, int)
    residuals = {}
    off = 0
    F0, s = p[0], p[1]
    for k, (i, f_rel, y) in enumerate(data):
        n = len(f_rel)
        r_i = res[off: off + n]
        off += n
        f = f_rel - F0
        v[i] = p[3 + k]
        # dy/dv = -s * f, so sigma_v = sigma_px / (s * sqrt(sum f^2)); floor the px noise
        sig_px = max(0.6, rms, float(np.sqrt(np.mean(r_i ** 2))))
        sigma[i] = sig_px / (s * np.sqrt(np.sum(f ** 2)))
        npts[i] = n
        residuals[i] = (f_rel + 0, r_i)
    return FitResult(v, sigma, npts, float(F0), float(s), float(p[2]), rms, residuals)
