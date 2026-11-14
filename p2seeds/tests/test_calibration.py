"""Cumulative-slope test and treasure panel merging."""

import numpy as np

from p2seeds import site, treasures


def test_kolmogorov_critical_values():
    assert abs(site.kolmogorov_p(1.36) - 0.05) < 0.005
    assert abs(site.kolmogorov_p(1.63) - 0.01) < 0.002
    assert site.kolmogorov_p(0) == 1.0


def _rows(x, y):
    return [{"x": float(a), "y": float(b), "k": i} for i, (a, b) in enumerate(zip(x, y))]


def test_constant_slope_shows_no_bend():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 5, 400)
    y = 0.8 * x + rng.normal(0, 3, 400)
    rows = _rows(x, y)
    slope = float(x @ y / (x @ x))
    c = site.cumulative(rows, slope, key=lambda r: abs(r["x"]))
    assert c["p"] > 0.01


def test_slope_change_shows_a_bend():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 5, 400)
    y = np.where(np.abs(x) > 5, 1.2, 0.2) * x + rng.normal(0, 1, 400)   # small swings barely count
    rows = _rows(x, y)
    slope = float(x @ y / (x @ x))
    c = site.cumulative(rows, slope, key=lambda r: abs(r["x"]))
    assert c["p"] < 0.001


def test_panel_hits_merge_into_one_panel():
    # one panel sampled every 8 frames for ~4 s, then a second treasure later
    hits = list(range(1000, 1130, 8)) + list(range(1300, 1420, 8))
    assert treasures.merge(hits) == [1000, 1300]
