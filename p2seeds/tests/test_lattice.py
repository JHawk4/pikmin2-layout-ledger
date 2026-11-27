"""Lattice seed search: finds the true seed from any subset of noisy letter velocities."""
import numpy as np

from p2seeds.story import lattice
from p2seeds import rng
from p2seeds.story.search import V_PER_RAND


def _measure(seed, n, sigma, bias, keep, rs):
    v = rng.letter_velocities(seed, n).astype(float)
    v = v - bias + rs.normal(0, sigma, n)
    v[[i for i in range(n) if i not in keep]] = np.nan
    s = np.full(n, sigma)
    s[np.isnan(v)] = np.nan
    return v, s


def test_finds_seed_from_scattered_letters():
    rs = np.random.default_rng(3)
    for trial in range(10):
        seed = int(rs.integers(0, 1 << 31))
        keep = sorted(rs.choice(14, size=7, replace=False).tolist())   # any letters, not the first four
        v, s = _measure(seed, 14, 0.01, float(rs.uniform(-0.3, 0.3)), keep, rs)
        c = lattice.search(v, s)
        assert c and c[0].letter_seed == seed & rng.MASK31, trial


def test_leave_out_steps_around_a_bad_letter():
    rs = np.random.default_rng(5)
    seed = int(rs.integers(0, 1 << 31))
    v, s = _measure(seed, 12, 0.01, 0.1, list(range(12)), rs)
    v[4] += 400 * V_PER_RAND * 10          # one mistracked letter, far outside its tolerance
    c = lattice.search(v, s, leave_out=[4])
    assert c and c[0].letter_seed == seed & rng.MASK31


def test_lll_keeps_the_lattice():
    b = [[1, 12345], [0, 1 << 31]]
    r = lattice.lll(b)
    det = abs(r[0][0] * r[1][1] - r[0][1] * r[1][0])
    assert det == 1 << 31
