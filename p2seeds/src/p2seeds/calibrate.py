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
        band = _find_name_band(p)
        if band is None:
            return None
    y0, y1 = band
    region = p[y0:y1]
    ext = _bright_extent(region)
    if ext is None:
        return None
    ex0, ex1, ey0, ey1 = ext
    text_w, text_h = ex1 - ex0 + 1, ey1 - ey0 + 1

    results = []
    for cave in caves or CAVES:
        best = None
        base_img, _ = compose(cave.name, 1.0, 1.0)
        # first guesses from the text's bright extent; refine around them
        sy0 = text_h / 34.0
        sx0 = text_w / max(1.0, base_img.shape[1] - 4)
        for sy in sy0 * np.linspace(0.85, 1.15, 13):
            for sx in sx0 * np.linspace(0.9, 1.1, 11):
                img, _ = compose(cave.name, sx, sy)
                if img.shape[0] >= region.shape[0] or img.shape[1] >= region.shape[1]:
                    continue
                res = cv2.matchTemplate(region, img, cv2.TM_CCOEFF_NORMED)
                _, score, _, loc = cv2.minMaxLoc(res)
                if best is None or score > best[0]:
                    best = (score, sx, sy, loc)
        if best:
            results.append((best, cave))
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


def _find_name_band(p: np.ndarray) -> tuple[int, int] | None:
    """Rows of the upper text line on an entry screen (name above 'Sublevel N')."""
    rows = (p > 0.5).mean(axis=1)
    on = rows > 0.01
    runs, y = [], 0
    while y < len(on):
        if on[y]:
            s = y
            while y < len(on) and on[y]:
                y += 1
            if y - s >= 4:
                runs.append((s, y))
        y += 1
    if not runs:
        return None
    s, e = runs[0]
    pad = max(6, (e - s) // 2)
    return max(0, s - pad), min(len(p), e + pad)
