"""End to end on synthetic letter falls with a known seed (no real video needed)."""

import numpy as np
import pytest

from p2seeds import letters_model
from p2seeds.calibrate import calibrate
from p2seeds.fit import fit
from p2seeds.search import search
from p2seeds.synth import render_fall
from p2seeds.track import track_all


@pytest.mark.parametrize("name, seed, feed_h", [
    ("Snagret Hole", 0x01234567, 360),
    ("Citadel of Spiders", 0x0BADF00D, 480),
])
def test_recovers_seed(name, seed, feed_h):
    frames = render_fall(name, seed, feed_h=feed_h, feed_w=int(feed_h * 1.29))
    cal = calibrate(frames[-1])
    assert cal is not None and cal.cave.name == name
    margin = cal.score - cal.runner_up[1]
    assert margin > 0.12

    result = fit(track_all(frames, cal), cal.cave.num_chars, s_guess=feed_h / 480)
    assert np.sum(np.isfinite(result.v)) >= 8

    best = search(result.v, result.sigma, max_bias=0.15)
    assert best and best[0].letter_seed == seed
    assert letters_model.layout_seed(best[0].letter_seed, len(name)) == letters_model.layout_seed(seed, len(name))
