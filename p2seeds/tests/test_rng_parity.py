"""rng.py (GC and Switch) against fixed sequences from CaveGen3, the source of truth for the game's RNG.

The sequences in data/cavegen3_rng.json come from CaveGen3's `Rng` (the pinned rev is recorded in the
file) through the small program in cavegen3_rng/. To refresh them after moving the pin:

    cargo run --release --manifest-path p2seeds/tests/cavegen3_rng/Cargo.toml > p2seeds/tests/data/cavegen3_rng.json

When that program has been built (data/build/cavegen3_rng/release/), the last test also runs it and checks
the committed file still matches what CaveGen3 produces.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from p2seeds import rng

HERE = Path(__file__).resolve().parent
VECTORS = json.loads((HERE / "data" / "cavegen3_rng.json").read_text(encoding="utf-8"))
CASES = VECTORS["cases"]
EXE = HERE.parents[1] / "data" / "build" / "cavegen3_rng" / "release" / "cavegen3-rng-vectors.exe"


def _id(c):
    return f"{c['generator']}-{c['seed']}"


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_states_and_outputs(case):
    seed = int(case["seed"], 16)
    states = [int(s, 16) for s in case["states"]]
    with rng.using(case["generator"]):
        assert [rng.next_seed(seed, k + 1) for k in range(len(states))] == states
        assert rng.forward_states(seed, len(states)).tolist() == states
        assert rng.advance(np.array([seed], np.uint64), len(states))[0] == states[-1]
        assert rng.prev_seed(states[-1], len(states)) == seed & rng.state_mask()
    if case["generator"] == "gc":
        assert rng.rands(seed, len(case["rand"])) == case["rand"]
    else:
        assert [s >> 33 for s in states] == case["rand"]


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_long_jumps(case):
    seed = int(case["seed"], 16)
    with rng.using(case["generator"]):
        for j in case["advance"]:
            assert rng.next_seed(seed, j["n"]) == int(j["state"], 16), j["n"]


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_letter_speeds(case):
    """Letter speeds are 5 * randFloat. On GC rng.py matches CaveGen3's f32 exactly. On Switch it divides
    rand() by 2^31 - 1 in float64 where CaveGen3 divides by 2^31 in f32: the same draw to ~1e-7."""
    seed = int(case["seed"], 16)
    want = 5 * np.array(case["rand_f32"], dtype=np.float64)
    with rng.using(case["generator"]):
        got = rng.letter_velocities(seed, len(want))
        speeds = rng.speed_of_state(rng.forward_states(seed, len(want)))
    if case["generator"] == "gc":
        assert got.tolist() == (5 * np.array(case["rand_f32"], dtype=np.float32)).tolist()
    np.testing.assert_allclose(got, want, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(speeds, want, rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_distance(case):
    seed = int(case["seed"], 16)
    with rng.using(case["generator"]):
        for j in case["advance"]:
            if j["n"] <= 1000:
                target = int(j["state"], 16) & rng.seed_mask()
                assert rng.distance(seed & rng.seed_mask(), target, limit=2000) == j["n"]


@pytest.mark.skipif(not EXE.exists(), reason="CaveGen3 vector program not built (see module docstring)")
def test_vectors_match_cavegen3():
    out = subprocess.run([str(EXE)], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == VECTORS
