"""Letter glyphs for the entry-screen font, taken from CaveGen's templates.

CaveGen stores them as files/templates/letters/<c>.png for lowercase and
<cc>.png for uppercase (case-insensitive filesystems), and Japanese characters
as u<code point>.png. Spaces and apostrophes
have no glyph; like continuous.py they take a fraction of the width of 'l'.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

SPACE_MULT = 1.34
APOSTROPHE_MULT = 0.6875

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "vendor" / "CaveGen" / "files" / "templates" / "letters"


def match(image: np.ndarray, template: np.ndarray) -> np.ndarray:
    """cv2 TM_CCOEFF_NORMED, with the meaningless scores on flat patches zeroed.

    Prepped frames are mostly exactly 0; a patch with no variance makes the
    normalization divide by zero, which OpenCV reports as ~1.0 or inf.
    """
    res = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    th, tw = template.shape
    k = (tw, th)
    m1 = cv2.boxFilter(image, -1, k, anchor=(0, 0), normalize=True, borderType=cv2.BORDER_CONSTANT)
    m2 = cv2.boxFilter(image * image, -1, k, anchor=(0, 0), normalize=True, borderType=cv2.BORDER_CONSTANT)
    var = (m2 - m1 * m1)[: res.shape[0], : res.shape[1]]
    res[~np.isfinite(res) | (var < 1e-4)] = 0.0
    return res


def prep(gray: np.ndarray) -> np.ndarray:
    """Map to [0,1] emphasizing the bright glyph outlines over the grey background smoke."""
    return np.clip((gray.astype(np.float32) - 90.0) / 120.0, 0.0, 1.0)


@lru_cache(maxsize=None)
def raw_glyph(ch: str, directory: str = str(DEFAULT_DIR)) -> np.ndarray:
    """The template as stored (grayscale 0-255)."""
    if not ch.isascii():
        name = f"u{ord(ch):04x}"          # Japanese: CaveGen names these by code point
    else:
        name = ch + ch if ch.isupper() else ch
    img = cv2.imread(str(Path(directory) / f"{name}.png"), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"no glyph template for {ch!r} in {directory}")
    return img


@lru_cache(maxsize=None)
def glyph(ch: str, directory: str = str(DEFAULT_DIR)) -> np.ndarray:
    return prep(raw_glyph(ch, directory))


def advance_width(ch: str) -> float:
    """Unscaled horizontal advance of one character."""
    if ch == " ":
        return glyph("l").shape[1] * SPACE_MULT
    if ch == "'":
        return glyph("l").shape[1] * APOSTROPHE_MULT
    return glyph(ch).shape[1]


def has_glyph(ch: str) -> bool:
    return ch not in (" ", "'")
