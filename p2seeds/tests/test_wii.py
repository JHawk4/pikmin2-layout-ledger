"""Wii / Wii U VC captures: the 4:3 picture stretched to 16:9, and a title that fades soon after landing."""

import cv2
import numpy as np

from p2seeds import templates
from p2seeds.calibrate import calibrate
from p2seeds.events import is_wide, normalize
from p2seeds.feed import Feed
from p2seeds.synth import render_fall


def _wide(frame: np.ndarray) -> np.ndarray:
    h = frame.shape[0]
    return cv2.resize(frame, (h * 16 // 9, h), interpolation=cv2.INTER_AREA)


def test_is_wide():
    assert is_wide(Feed(0, 0, 640, 360))
    assert not is_wide(Feed(0, 0, 480, 360))


def test_calibrates_a_stretched_name():
    frames = render_fall("White Flower Garden", 0x34759EF6, feed_h=360, feed_w=480)
    cal = calibrate(_wide(frames[-1]))
    assert cal is not None and cal.cave.name == "White Flower Garden"
    assert cal.sx > 1.15 * cal.sy          # the stretch is found, glyphs included
    assert cal.score - cal.runner_up[1] > 0.1


def test_normalize_restores_a_fading_title():
    frame = render_fall("Snagret Hole", 0x01234567, feed_h=360, feed_w=480)[-1]
    dim = (frame.astype(np.float32) * 0.6).astype(np.uint8)
    back = normalize(dim)
    assert abs(templates.bright_level(back) - templates.FULL_BRIGHT) < 0.05 * templates.FULL_BRIGHT
    assert normalize(np.zeros_like(frame)) is not None      # black stays black
