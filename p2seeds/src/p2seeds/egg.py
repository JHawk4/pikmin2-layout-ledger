"""Pikmin 2 egg drop roll (Game::Egg::Obj::genItem, plugProjectMorimuraU/egg.cpp).

One global rand() is drawn the frame the egg's health reaches 0:
    r = rand() / 32768.0            # randFloat(), RAND_MAX = SHORT_FLOAT_MAX = 32768.0f
and compared against the cumulative parms from /enemy/parm/enemyParms.szs/egg/enemyparm.txt
(fp01..fp05 = 0.50, 0.35, 0.05, 0.05, 0.05).
"""

from __future__ import annotations

from .rng import rand_after

# Cumulative f32 thresholds, in rand() units (r < t * 32768).
OUTCOMES = [
    ("nectar", 0.50),
    ("double nectar", 0.85),
    ("mitites", 0.90),
    ("spicy", 0.95),
    ("bitter", 1.00),
]


def outcome_of_rand(r: int) -> str:
    """Drop type for a 15-bit rand() value (before the spray-unlock and full-pool fallbacks)."""
    f = r / 32768.0
    for name, t in OUTCOMES:
        if f < t:
            return name
    return "nectar"  # unreachable: thresholds sum to 1.0


def outcome_after(state: int) -> str:
    """Drop type if the egg's roll is the next draw from global RNG state `state`."""
    _, r = rand_after(state)
    return outcome_of_rand(r)


MITITE_RAND_RANGE = range(27853, 29492)  # 1639 of 32768 values = 5.002%

if __name__ == "__main__":
    assert all(outcome_of_rand(r) == "mitites" for r in MITITE_RAND_RANGE)
    assert outcome_of_rand(27852) == "double nectar" and outcome_of_rand(29492) == "spicy"
    print(len(MITITE_RAND_RANGE) / 32768)
