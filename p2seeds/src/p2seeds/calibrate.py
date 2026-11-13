"""Identify the cave name on a settled entry screen and locate every letter.

The name is laid out like CaveGen's continuous.py does it: glyphs side by side
at their template widths, spaces as a multiple of 'l'. Long names are squeezed
horizontally to fit, so horizontal and vertical scale are fitted separately.
For each candidate cave and scale, the composed name image is slid over the
frame with normalized cross-correlation; the best match gives the cave, the
scales and the position, and from those each letter's box.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from . import templates
from .caves import CAVES, Cave


@dataclass
class LetterBox:
    index: int          # character index in the name (spaces count)
    ch: str
    x: float            # left edge in the frame (px)
    y: float            # top edge when settled (px)
    template: np.ndarray  # scaled glyph, prepped


@dataclass
class Calibration:
    cave: Cave
    score: float
    sx: float           # horizontal scale applied to templates
    sy: float           # vertical scale
    x: int              # top-left of the composed name in the frame
    y: int
    letters: list[LetterBox] = field(default_factory=list)
    runner_up: tuple[str, float] | None = None

    @property
    def glyph_height(self) -> float:
        return 40 * self.sy


def compose(name: str, sx: float, sy: float) -> tuple[np.ndarray, list[tuple[int, str, int, np.ndarray]]]:
    """Render `name` at scale (sx, sy). Returns the image and (index, ch, x, glyph) per drawn letter."""
    h = max(1, int(round(40 * sy)))
    pieces = []
    x = 0.0
    for i, ch in enumerate(name):
        w_adv = templates.advance_width(ch) * sx
        if templates.has_glyph(ch):
            g = templates.glyph(ch)
            gw = max(1, int(round(g.shape[1] * sx)))
            gs = cv2.resize(g, (gw, max(1, int(round(g.shape[0] * sy)))), interpolation=cv2.INTER_AREA)
            pieces.append((i, ch, int(round(x)), gs[:h]))
        x += w_adv
    img = np.zeros((h, int(round(x)) + 2), np.float32)
    for _, _, px, gs in pieces:
        img[: gs.shape[0], px: px + gs.shape[1]] = np.maximum(img[: gs.shape[0], px: px + gs.shape[1]], gs)
    return img, pieces


def _bright_extent(p: np.ndarray, thr: float = 0.35) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(p > thr)
    if len(xs) < 20:
        return None
    return int(np.percentile(xs, 0.5)), int(np.percentile(xs, 99.5)), int(np.percentile(ys, 2)), int(np.percentile(ys, 98))


def calibrate(
    settled_gray: np.ndarray,
    band: tuple[int, int] | None = None,
    caves: list[Cave] | None = None,
) -> Calibration | None:
    """`settled_gray`: the game feed (grayscale) once the letters have landed.
    `band`: optional (y0, y1) rows containing the name; found automatically otherwise."""
    p = templates.prep(settled_gray)
    H, W = p.shape
    if band is None:
        # the name line always sits in the same part of the screen
        band = (int(0.14 * H), int(0.48 * H))
    y0, y1 = band
    region = p[y0:y1]
    ext = _bright_extent(region)
    if ext is None:
        return None
    ex0, ex1, ey0, ey1 = ext
    text_w, text_h = ex1 - ex0 + 1, ey1 - ey0 + 1

    # Glyphs are a fixed fraction of the screen height (~0.99 * H/480), so the
    # vertical scale is searched near that. The horizontal scale also absorbs the
    # squeeze applied to long names; its guess comes from the text width, which
    # background swirls can inflate, so it is searched widely. A coarse pass ranks
    # every cave; only the two best get the fine grid.
    sy0 = 0.99 * H / 480.0

    def best_fit(cave: Cave, sys, sx_factors, extra_ratios) -> tuple | None:
        base_w = compose(cave.name, 1.0, 1.0)[0].shape[1]
        sx0 = min(sy0, text_w / max(1.0, base_w - 4))
        best = None
        for sy in sys:
            for sx in np.unique(np.r_[sx0 * sx_factors, sy * extra_ratios]):
                img, _ = compose(cave.name, sx, sy)
                if img.shape[0] >= region.shape[0] or img.shape[1] >= region.shape[1]:
                    continue
                _, score, _, loc = cv2.minMaxLoc(templates.match(region, img))
                if best is None or score > best[0]:
                    best = (score, sx, sy, loc)
        return best

    coarse = []
    for cave in caves or CAVES:
        b = best_fit(cave, [sy0], np.linspace(0.85, 1.1, 6), np.array([0.8, 0.9, 1.0]))
        if b:
            coarse.append((b, cave))
    coarse.sort(key=lambda r: -r[0][0])
    results = []
    for b, cave in coarse[:2]:
        fine = best_fit(cave, sy0 * np.linspace(0.92, 1.08, 9), np.linspace(0.85, 1.1, 11), np.linspace(0.8, 1.0, 5))
        results.append((max(b, fine, key=lambda x: x[0]) if fine else b, cave))
    # the runner-up's score is only used for the margin; give the rest their coarse scores
    results += coarse[2:]
    if not results:
        return None
    results.sort(key=lambda r: -r[0][0])
    (score, sx, sy, (lx, ly)), cave = results[0]
    _, pieces = compose(cave.name, sx, sy)
    cal = Calibration(cave, float(score), float(sx), float(sy), lx, y0 + ly)
    cal.letters = [LetterBox(i, ch, lx + px, y0 + ly, g) for i, ch, px, g in pieces]
    if len(results) > 1:
        cal.runner_up = (results[1][1].name, float(results[1][0][0]))
    return cal
