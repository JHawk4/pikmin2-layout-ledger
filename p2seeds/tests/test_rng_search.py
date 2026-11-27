import json
from pathlib import Path

import numpy as np
import pytest

from p2seeds.story import letters_model
from p2seeds import rng
from p2seeds.story.search import search

REF = json.loads((Path(__file__).parent / "data" / "seed_ref.json").read_text())["cases"]


@pytest.mark.parametrize("case", REF[:50])
def test_matches_java(case):
    assert rng.next_seed(case["seed"]) == case["next1"]
    vels = rng.letter_velocities(case["seed"], case["n"])
    assert np.array_equal(vels, np.array(case["vels"], dtype=np.float32))


@pytest.mark.parametrize("case", REF[:50])
def test_jump_matches_java(case):
    # Java's next_seed(seed, n) works mod 2^31 (it goes through nth/nth_inv)
    assert rng.next_seed(case["seed"], case["jump"]) & rng.MASK31 == case["nextN"]


def test_jump_backwards_inverts_forwards():
    s = 0x1234ABCD
    for n in (1, 7, 1000, 123456):
        assert rng.next_seed(rng.next_seed(s, n), -n) == s


def test_delay_frames():
    # 19-character name: char i waits ceil(30*i/19) frames (float32 loop)
    assert [letters_model.delay_frames(i, 19) for i in range(5)] == [0, 2, 4, 5, 7]
    assert letters_model.delay_frames(0, 14) == 0


@pytest.mark.parametrize("seed", [0x31D70855, 0x2A2B3C4D])
def test_search_recovers_seed_from_noisy_velocities(seed):
    name = "White Flower Garden"
    true_v = rng.letter_velocities(seed, len(name)).astype(float)
    gen = np.random.default_rng(seed)
    sigma = np.full(len(name), 0.08)
    v = true_v + gen.normal(0, 0.08, len(name))
    for i, ch in enumerate(name):
        if ch == " ":
            v[i] = np.nan
    v[2] = np.nan   # an occluded letter
    v[0] = 4.9      # and one badly mismeasured letter
    sigma[0] = 0.5
    best = search(v, sigma, max_bias=0.15)
    assert best and best[0].letter_seed == seed & rng.MASK31
    assert len(best) == 1 or best[1].score > best[0].score + 20
