"""The Switch generator (musl's 64-bit LCG): stepping, distances, letter speeds, seed search."""
import numpy as np
import pytest

from p2seeds import lattice, letters_model, rng
from p2seeds.search import search_near

A64, MASK = 6364136223846793005, (1 << 64) - 1


@pytest.fixture(autouse=True)
def switch():
    with rng.using("switch"):
        yield
    assert rng.active() == "gc"


def _musl_speeds(seed, n):
    out, s = [], seed
    for _ in range(n):
        s = (s * A64 + 1) & MASK
        out.append(5 * (s >> 33) / ((1 << 31) - 1))
    return np.array(out)


def test_steps_and_speeds_match_musl():
    seed = 0x0123456789ABCDEF
    assert rng.next_seed(seed) == (seed * A64 + 1) & MASK
    assert rng.next_seed(rng.next_seed(seed, 1000), -1000) == seed
    np.testing.assert_allclose(rng.letter_velocities(seed, 20), _musl_speeds(seed, 20), atol=1e-6)
    st = rng.forward_states(seed, 50)
    assert int(st[49]) == rng.next_seed(seed, 50)


def test_distance_is_exact_and_respects_limit():
    rs = np.random.default_rng(1)
    for _ in range(20):
        s = int(rs.integers(0, 1 << 63)) * 2 + int(rs.integers(0, 2))
        n = int(rs.integers(1, 10**9))
        assert rng.distance(s, rng.next_seed(s, n), limit=1 << 40) == n
        assert rng.distance(s, rng.next_seed(s, n), limit=n - 1) is None


def test_lattice_finds_seed_from_noisy_letters():
    rs = np.random.default_rng(7)
    for trial in range(5):
        seed = int(rs.integers(0, 1 << 63)) << 1 | int(rs.integers(0, 2))
        v = rng.letter_velocities(seed, 14).astype(float) - float(rs.uniform(-0.2, 0.2)) + rs.normal(0, 0.015, 14)
        v[9] = np.nan                                     # a space
        s = np.where(np.isnan(v), np.nan, 0.015)
        c = lattice.search(v, s)
        assert c and c[0].letter_seed == seed, trial


def test_search_near_reaches_a_short_name_from_its_neighbour():
    seed_a = 0x1D2C3B4A59687706
    target = rng.next_seed(seed_a, 54_321)
    v = rng.letter_velocities(target, 5).astype(float) + 0.05
    s = np.full(5, 0.015)
    c = search_near(v, s, seed_a, 200_000)
    assert c[0].letter_seed == target and c[0].distance == 54_321


def test_layout_seed_keeps_all_64_bits():
    seed = 0xFEDCBA9876543210
    assert letters_model.layout_seed(seed, 13) == rng.next_seed(seed, 13)


# Two real entries from a Switch run (tcbtrio, USA): Emergence Cave 1 and 2. Their seeds come from
# the letters alone and lie 16,424 draws apart, as consecutive sublevels must (docs/switch-rng.md).
EC1 = ([1.0396, 1.3043, 3.6543, 4.578, 0.6658, 2.4096, 3.282, 3.3495, 0.495, None, 0.4458, 4.8133, 1.8767, 0.8149],
       [0.0175, 0.0175, 0.0148, 0.0144, 0.0172, 0.0165, 0.016, 0.0156, 0.0187, None, 0.0187, 0.014, 0.0165, 0.0175])
EC2 = ([0.872, 0.0331, 3.7353, 3.0966, 3.9416, 3.7342, 1.4785, 4.6278, -0.0495, None, 1.9459, 1.7237, 3.842, 1.2074],
       [0.0182, 0.0189, 0.0149, 0.0162, 0.0149, 0.0149, 0.0167, 0.0141, 0.0189, None, 0.0167, 0.0163, 0.0149, 0.0177])


def _arr(x):
    return np.array([np.nan if y is None else y for y in x])


def test_real_switch_entries_give_chaining_seeds():
    seeds = []
    for v, s in (EC1, EC2):
        c = lattice.search(_arr(v), _arr(s))
        assert c and c[0].score < 30
        seeds.append(c[0].letter_seed)
    assert seeds[0] == rng.next_seed(0x306306F66F0443C4, -1)
    assert rng.distance(seeds[0], seeds[1], limit=1 << 24) == 16_424
