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


def free_fall(track: Track, min_score: float = 0.55) -> tuple[np.ndarray, np.ndarray]:
    ok = (track.score >= min_score) & (track.score < 0.995)
    fr, y = track.frames[ok], track.y[ok]
    keep_f, keep_y = [], []
    prev_dy = None
    for f, yy in zip(fr, y):
        if keep_f:
            gap = f - keep_f[-1]
            dy = (yy - keep_y[-1]) / gap
            if dy <= 0.5:                      # stopped or bouncing
                break
            if prev_dy is not None and dy < 0.8 * prev_dy:
                break                          # hit the floor during this frame
            if prev_dy is not None and dy > prev_dy + 4:
                # implausible jump (bad match); restart from here
                keep_f, keep_y, prev_dy = [f], [yy], None
                continue
            prev_dy = dy
        keep_f.append(f)
        keep_y.append(yy)
    return np.array(keep_f, float), np.array(keep_y, float)


def fit(tracks: list[Track], num_chars: int, s_guess: float, min_points: int = 4) -> FitResult:
    data = []
    for t in tracks:
        f, y = free_fall(t)
        if len(f) >= min_points:
            data.append((t.index, f - letters_model.delay_frames(t.index, num_chars), y))
    if len(data) < 3:
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

    best = None
    for F0 in np.arange(-30, 40, 2.0):
        p0 = np.r_[F0, s_guess, floor0, np.full(len(data), 2.5)]
        lo = np.r_[-60, s_guess * 0.7, floor0 - 30, np.full(len(data), -0.5)]
        hi = np.r_[80, s_guess * 1.3, floor0 + 30, np.full(len(data), 5.5)]
        r = least_squares(resid, p0, bounds=(lo, hi), loss="soft_l1", f_scale=1.0)
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
