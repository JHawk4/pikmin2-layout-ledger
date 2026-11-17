"""Track each falling letter's height, frame by frame, with sub-pixel precision.

Each letter only moves vertically inside its own column, so its scaled glyph is
matched against a narrow strip of every frame (padded above the top edge so a
letter half off-screen still matches). The correlation peak is refined with a
parabola fit for sub-pixel accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import templates
from .calibrate import Calibration, LetterBox


@dataclass
class Track:
    index: int
    ch: str
    rest_y: float             # glyph top when settled (px)
    frames: np.ndarray        # frame numbers (relative to the clip)
    y: np.ndarray             # matched glyph top (px), may be negative (above the screen)
    score: np.ndarray         # match quality per frame


def _subpixel(vals: np.ndarray, k: int) -> float:
    if 0 < k < len(vals) - 1:
        a, b, c = vals[k - 1], vals[k], vals[k + 1]
        den = a - 2 * b + c
        if den < 0:
            return k + 0.5 * (a - c) / den
    return float(k)


MIN_BRIGHT = 25.0     # frames darker than this (black, or the very start of the fade) carry no glyphs


def track_letter(frames: list[np.ndarray], box: LetterBox, x_slack: int = 2, min_score: float = 0.5,
                 refs: list[float] | None = None, blended: bool = False) -> Track:
    """`blended`: frames that are a 50/50 blend of two consecutive game frames (interlaced captures
    blended on upload). A falling letter then shows twice in its column: the upper copy is the
    earlier game frame, the lower one the next. Both are kept, the lower one a frame later (its
    frame number is k + 0.5 here; the caller's clock maps k -> game time, see analyze)."""
    t = box.template
    h, w = t.shape
    x0 = max(0, int(round(box.x)) - x_slack)
    x1 = int(round(box.x)) + w + x_slack
    y_bot = int(round(box.y)) + h + 2      # nothing of interest below the settled glyph
    pad = h                                # allow the glyph to hang above the top edge
    fr, ys, sc = [], [], []
    for k, gray in enumerate(frames):
        ref = refs[k] if refs is not None else None
        if ref is not None and ref < MIN_BRIGHT:
            continue
        strip = templates.prep(gray[0:y_bot, x0:x1], ref)
        strip = np.vstack([np.zeros((pad, strip.shape[1]), np.float32), strip])
        if strip.std() < 1e-3:
            continue
        res = templates.match(strip, t)
        col = int(np.argmax(res.max(axis=0)))
        column = res[:, col]
        row = int(np.argmax(column))
        if blended:
            # a second copy of the letter further along its fall (lower), or before it (higher)
            sep = max(3, int(0.25 * h))
            masked = column.copy()
            masked[max(0, row - sep): row + sep + 1] = -1
            row2 = int(np.argmax(masked))
            if column[row] >= min_score and masked[row2] >= min_score and abs(row2 - row) <= 1.6 * h:
                top, bot = sorted((row, row2))
                fr += [k, k + 0.5]
                ys += [_subpixel(column, top) - pad, _subpixel(column, bot) - pad]
                sc += [float(column[top]), float(column[bot])]
                continue
        if column[row] < min_score:
            continue
        fr.append(k)
        ys.append(_subpixel(column, row) - pad)
        sc.append(float(column[row]))
    return Track(box.index, box.ch, float(box.y), np.array(fr), np.array(ys), np.array(sc))


def track_all(frames: list[np.ndarray], cal: Calibration, **kw) -> list[Track]:
    # each frame's own brightness: the screen fades in during the fall
    refs = [templates.bright_level(f) for f in frames]
    return [track_letter(frames, box, refs=refs, **kw) for box in cal.letters]
