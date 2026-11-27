"""game_times: repeated and skipped capture frames."""

import numpy as np

from p2seeds.story.analyze import game_times


def _video(game_frames, noise_on=()):
    """One synthetic frame per video frame, showing the given game frame.

    A sliding ramp makes the mean difference proportional to how far the game
    advanced; frames listed in `noise_on` get re-encoding style noise."""
    rng = np.random.default_rng(0)
    out = []
    for j, g in enumerate(game_frames):
        x = np.arange(200)
        img = np.tile(np.clip(x - 5 * g, 0, 255), (40, 1)).astype(np.uint8)
        if j in noise_on:
            img = np.clip(img.astype(int) + rng.integers(-1, 2, img.shape), 0, 255).astype(np.uint8)
        out.append(img)
    return out


def test_exact_repeat_is_dropped():
    kept, t = game_times(_video([0, 1, 2, 3, 3, 4, 5, 6, 7]))
    assert len(kept) == 8
    assert t.tolist() == [0, 1, 2, 3, 4, 5, 6, 7]


def test_noisy_repeat_is_dropped():
    kept, t = game_times(_video([0, 1, 2, 3, 3, 4, 5, 6, 7], noise_on={4}))
    assert t.tolist() == [0, 1, 2, 3, 4, 5, 6, 7]


def test_repeat_then_skip_keeps_time():
    # uneven pacing: game frame 3 shown twice, 4 never shown
    kept, t = game_times(_video([0, 1, 2, 3, 3, 5, 6, 7, 8]))
    assert t.tolist() == [0, 1, 2, 3, 5, 6, 7, 8]


def test_steady_video_unchanged():
    kept, t = game_times(_video(list(range(12))))
    assert t.tolist() == list(range(12))
