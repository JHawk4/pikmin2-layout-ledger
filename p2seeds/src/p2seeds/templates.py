"""Letter glyphs for the entry-screen font, taken from CaveGen's templates.

CaveGen stores them as files/templates/letters/<c>.png for lowercase and
<cc>.png for uppercase (case-insensitive filesystems). Spaces and apostrophes
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


def prep(gray: np.ndarray) -> np.ndarray:
    """Map to [0,1] emphasizing the bright glyph outlines over the grey background smoke."""
    return np.clip((gray.astype(np.float32) - 90.0) / 120.0, 0.0, 1.0)


@lru_cache(maxsize=None)
def glyph(ch: str, directory: str = str(DEFAULT_DIR)) -> np.ndarray:
    name = ch + ch if ch.isupper() else ch
    img = cv2.imread(str(Path(directory) / f"{name}.png"), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"no glyph template for {ch!r} in {directory}")
    return prep(img)


def advance_width(ch: str) -> float:
    """Unscaled horizontal advance of one character."""
    if ch == " ":
        return glyph("l").shape[1] * SPACE_MULT
    if ch == "'":
        return glyph("l").shape[1] * APOSTROPHE_MULT
    return glyph(ch).shape[1]


def has_glyph(ch: str) -> bool:
    return ch not in (" ", "'")
