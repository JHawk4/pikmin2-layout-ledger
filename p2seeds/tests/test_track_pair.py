"""Blended captures whose two copies of a falling letter overlap: the pair tracker finds both."""

import cv2
import numpy as np

from p2seeds import luck, templates
from p2seeds.calibrate import LetterBox
from p2seeds.track import track_letter_pair


def _frames(ys, d, glyph, x=20, h=120, w=60):
    """Frames with the glyph drawn twice at half strength, the second copy d px lower."""
    out = []
    gh, gw = glyph.shape
    for y in ys:
        f = np.full((h, w), 40.0, np.float32)
        for yy in (y, y + d):
            f[yy:yy + gh, x:x + gw] += 0.5 * glyph
        out.append(np.clip(f, 0, 255).astype(np.uint8))
    return out


def test_pair_tracker_finds_overlapping_copies():
    raw = cv2.resize(templates.raw_glyph("S"), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA).astype(np.float32)
    gh = raw.shape[0]
    d = gh // 2                                   # the copies overlap by half the glyph
    ys = [5, 15, 25, 35]
    frames = _frames(ys, d, raw)
    box = LetterBox(index=0, ch="S", x=20, y=90, template=templates.prep(raw))
    tr = track_letter_pair(frames, box)
    assert list(tr.frames) == [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]
    tops, bots = tr.y[0::2], tr.y[1::2]
    assert np.allclose(tops, ys, atol=1.0)
    assert np.allclose(bots - tops, d, atol=1.0)


def test_luck_percentile_and_words():
    samples = np.arange(100.0) - 50          # -50 .. 49
    assert luck.percentile(-60, samples) == 100.0
    assert luck.percentile(0, samples) == 49.0
    assert luck.describe(100.0) == "luckier than 99.5% of random runs"
    assert luck.describe(49.0) == "luckier than 49% of random runs"
