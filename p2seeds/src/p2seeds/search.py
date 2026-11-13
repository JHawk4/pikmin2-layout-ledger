"""Find the seed whose rand() outputs best match measured letter velocities.

Brute force over the 2^31 relevant states, made cheap by pruning:

1. Pick the best-measured character as the pivot. Its rand is known to within
   a tolerance, which fixes state bits 16..30 to a narrow range; the low 16 bits
   are free. That is (range width) x 65536 candidate states instead of 2^31.
2. Jump each candidate forward/backward to the other characters (the RNG step
   is affine, so a jump of k steps is one multiply-add) and drop candidates
   whose output falls outside that character's tolerance, best-measured first.
3. Score the survivors on every measured character with a robust (capped)
   chi-square so a single bad measurement can't sink the true seed.

Unlike CaveGen's lattice search this has no "first four letters must be
readable" requirement; any characters can be missing.

Measured velocities can carry a small constant bias (the fitted timing and
scale trade off against a shared velocity offset), so pruning compares each
character relative to the pivot, and scoring removes the best constant bias
(up to `max_bias`) before computing the chi-square.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import rng

V_PER_RAND = 5.0 / 32768.0


@dataclass
class Candidate:
    letter_seed: int        # state before the first character's rand()
    score: float            # robust chi-square over measured characters, after removing the bias
    bias: float             # fitted constant (v_seed - v_measured)
    residuals: np.ndarray   # (v_seed - v_measured - bias) per character (nan where unmeasured)


def search(
    v: np.ndarray,
    sigma: np.ndarray,
    n_prune: int = 6,
    k_prune: float = 4.0,
    max_bias: float = 0.25,
    cap: float = 16.0,
    chunk: int = 1 << 23,
    top: int = 5,
) -> list[Candidate]:
    """`v[i]`/`sigma[i]` are the measured velocity and its 1-sigma error for character i
    (nan for spaces/unmeasured). Returns the best candidates, lowest score first."""
    v = np.asarray(v, dtype=np.float64)
    sigma = np.asarray(sigma, dtype=np.float64)
    measured = [i for i in range(len(v)) if np.isfinite(v[i]) and np.isfinite(sigma[i])]
    if len(measured) < 3:
        raise ValueError("need at least 3 measured characters")
    order = sorted(measured, key=lambda i: sigma[i])
    pivot, prune = order[0], order[1:1 + n_prune]

    # rand range for the pivot (widened by the allowed bias)
    span = k_prune * sigma[pivot] + max_bias
    lo = max(0, int(np.floor((v[pivot] - span) / V_PER_RAND)))
    hi = min(0x7FFF, int(np.ceil((v[pivot] + span) / V_PER_RAND)))

    # jumps from the pivot's state (state after its rand) to each character's state
    jumps = {i: rng.jump(i - pivot) for i in measured}
    # differences to the pivot cancel the bias; their errors add in quadrature
    tol = {i: k_prune * np.hypot(sigma[i], sigma[pivot]) for i in measured}

    low16 = np.arange(1 << 16, dtype=np.uint64)
    per_chunk = max(1, chunk >> 16)
    best: list[Candidate] = []
    for r0 in range(lo, hi + 1, per_chunk):
        rs = np.arange(r0, min(hi + 1, r0 + per_chunk), dtype=np.uint64)
        states = ((rs[:, None] << np.uint64(16)) | low16[None, :]).ravel()
        vp = rng.rand_of_state(states).astype(np.float64) * V_PER_RAND - v[pivot]  # pivot's offset
        for i in prune:
            a, c = jumps[i]
            s_i = (states * np.uint64(a) + np.uint64(c)) & np.uint64(rng.MASK32)
            di = rng.rand_of_state(s_i).astype(np.float64) * V_PER_RAND - v[i]
            keep = np.abs(di - vp) <= tol[i]
            states, vp = states[keep], vp[keep]
            if states.size == 0:
                break
        if states.size == 0:
            continue
        best.extend(_score(states, v, sigma, measured, jumps, pivot, cap, max_bias))
        best.sort(key=lambda c: c.score)
        del best[top:]
    return best


def _score(states, v, sigma, measured, jumps, pivot, cap, max_bias):
    d = np.full((states.size, len(v)), np.nan)
    for i in measured:
        a, c = jumps[i]
        s_i = (states * np.uint64(a) + np.uint64(c)) & np.uint64(rng.MASK32)
        d[:, i] = rng.rand_of_state(s_i).astype(np.float64) * V_PER_RAND - v[i]
    m = np.array(measured)
    dm = d[:, m]
    w = 1.0 / sigma[m] ** 2
    # robust bias: median, then clipped to the allowed range
    bias = np.clip(np.median(dm, axis=1), -max_bias, max_bias)
    res = dm - bias[:, None]
    total = np.minimum(res ** 2 * w, cap).sum(axis=1)
    keep = np.argsort(total)[:10]
    a0, c0 = rng.jump(-(pivot + 1))  # pivot's state is after pivot+1 advances from the seed
    out = []
    for k in keep:
        seed = (int(states[k]) * a0 + c0) & rng.MASK31
        r = np.full(len(v), np.nan)
        r[m] = res[k]
        out.append(Candidate(seed, float(total[k]), float(bias[k]), r))
    return out
