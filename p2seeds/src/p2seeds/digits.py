"""Read the sublevel number from the "Sublevel N" line.

Reference digits (0-9) live in data/digits as
prepped grayscale PNGs cropped from real entry screens. A crop is compared to
each reference after resizing both to a common size.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

DATA = Path(__file__).parent / "data" / "digits"
SIZE = (24, 32)   # (w, h) used for comparison
MIN_SCORE = 0.6
MIN_MARGIN = 0.08


@lru_cache(maxsize=1)
def references() -> dict[int, list[np.ndarray]]:
    refs: dict[int, list[np.ndarray]] = {}
    for p in sorted(DATA.glob("*.png")):
        value = int(p.stem.split("_")[0])
        if not 0 <= value <= 9:
            continue
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
        refs.setdefault(value, []).append(_norm(img))
    return refs


def _norm(img: np.ndarray) -> np.ndarray:
    a = cv2.resize(img, SIZE, interpolation=cv2.INTER_AREA).ravel()
    a = a - a.mean()
    n = np.linalg.norm(a)
    return a / n if n > 0 else a


def read(crop: np.ndarray | None) -> tuple[int | None, float]:
    """(value, score); value is None when no reference matches clearly."""
    if crop is None or crop.size == 0 or not references():
        return None, 0.0
    c = _norm(crop.astype(np.float32))
    scored = sorted(((max(float(c @ r) for r in rs), v) for v, rs in references().items()), reverse=True)
    best, value = scored[0]
    second = scored[1][0] if len(scored) > 1 else -1.0
    if best < MIN_SCORE or best - second < MIN_MARGIN:
        return None, best
    return value, best


def save_reference(value: int, crop: np.ndarray, tag: str) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / f"{value}_{tag}.png"
    cv2.imwrite(str(path), np.clip(crop * 255, 0, 255).astype(np.uint8))
    return path


def read_number(parts: list[np.ndarray]) -> int | None:
    """A one- or two-digit number from its digit crops (see analyze.split_digits)."""
    if not 1 <= len(parts) <= 2:
        return None
    values = [read(p)[0] for p in parts]
    if any(v is None for v in values):
        return None
    number = int("".join(str(v) for v in values))
    return number if number >= 1 else None
