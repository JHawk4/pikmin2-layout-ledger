"""How the cave-name letters fall on a sublevel entry screen (from CaveGen's Letters.java).

Each character i of an n-character name (spaces included) draws one rand():
    v_i = rand * 5 / 32768                       (starting velocity, 0 <= v < 5)
and starts moving `delay_frames(i, n)` frames after the first one. Measured in
the game's 480-unit screen space, f frames after it starts its height is
    pos(f) = 200 + (v - 0.5) * f - f^2 / 2
i.e. each frame the velocity drops by 1 and the position moves by it. The
letter comes to rest at pos = 0 (its final place in the settled name); the top
of the screen is roughly pos = 164.

The seed CaveGen generates the layout from is the letter seed advanced once
per character (Manip.java: `next_seed(sd, num_chars)`).
"""

from __future__ import annotations

import numpy as np

from . import rng

START_POS = 200.0
FPS = 30


def delay_frames(i: int, n: int) -> int:
    """Frames before character i starts, replicating Letters.java's float32 loop."""
    t = np.float32(i) / np.float32(n)
    step = np.float32(1.0) / np.float32(FPS)
    frames = 0
    while t > 0:
        t = np.float32(t - step)
        frames += 1
    return frames


def pos(v, f):
    """Height above the resting line, f frames after the letter started."""
    f = np.asarray(f, dtype=np.float64)
    return START_POS + (np.asarray(v) - 0.5) * f - f * f / 2.0


def landing_frame(v: float) -> float:
    """Frames after starting at which pos reaches 0."""
    b = v - 0.5
    return b + np.sqrt(b * b + 2 * START_POS)


def layout_seed(letter_seed: int, num_chars: int) -> int:
    return rng.next_seed(letter_seed, num_chars) & rng.seed_mask()
