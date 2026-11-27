"""Render synthetic entry-screen letter falls from a known seed (for testing).

The letters use the real glyph templates and the game's fall model; frames
can be degraded with blur, noise, JPEG compression and a sub-frame time
offset, so the whole calibrate -> track -> fit -> search chain can be checked
against a known answer without real video.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import letters_model, templates
from .. import rng
from .calibrate import compose


def render_fall(
    name: str,
    seed: int,
    feed_h: int = 360,
    feed_w: int = 465,
    n_frames: int = 110,
    start: float = 12.3,          # frame (fractional) at which letter 0 starts
    blur: float = 0.8,
    noise: float = 3.0,
    jpeg: int | None = 60,
    rng_seed: int = 0,
) -> list[np.ndarray]:
    """Grayscale frames of the feed; the name settles with its glyph tops at ~0.27*feed_h."""
    n = len(name)
    v = rng.letter_velocities(seed, n).astype(float)
    s = feed_h / 480.0
    sy = s * 0.99
    sx = sy * min(1.0, 0.75 * feed_w / compose(name, sy, sy)[0].shape[1])
    img, pieces = compose(name, sx, sy)
    # draw with the raw (unthresholded) glyphs so frames look like the real screen
    pieces = [(i, ch, px, cv2.resize(templates.raw_glyph(ch).astype(np.float32) / 255.0, (g.shape[1], g.shape[0]),
                                     interpolation=cv2.INTER_AREA)) for i, ch, px, g in pieces]
    x_left = (feed_w - img.shape[1]) / 2
    y_floor = 0.27 * feed_h
    gen = np.random.default_rng(rng_seed)
    frames = []
    for k in range(n_frames):
        canvas = np.zeros((feed_h, feed_w), np.float32)
        for i, ch, px, g in pieces:
            f = k - start - letters_model.delay_frames(i, n)
            if f < 0:
                continue
            p = max(0.0, float(letters_model.pos(v[i], f)))
            y = y_floor - s * p
            M = np.float32([[1, 0, x_left + px], [0, 1, y]])
            canvas = np.maximum(canvas, cv2.warpAffine(g, M, (feed_w, feed_h), flags=cv2.INTER_LINEAR))
        gray = 16 + canvas * 230
        if blur:
            gray = cv2.GaussianBlur(gray, (0, 0), blur)
        if noise:
            gray = gray + gen.normal(0, noise, gray.shape)
        gray = np.clip(gray, 0, 255).astype(np.uint8)
        if jpeg:
            ok, buf = cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
            gray = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        frames.append(gray)
    return frames
