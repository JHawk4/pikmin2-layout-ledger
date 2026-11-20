"""Layout luck: how a run's layouts compare with random layouts of the same sublevels.

judge2 (the refit Pay Off Debt judge) is the site's judge; CaveGen's judge is only a fallback
for runs judge2 can't score (other categories). Every number is in seconds against the median
random layout of the sublevel, negative = faster, as on splits.
"""

from __future__ import annotations

import numpy as np

from . import cavegen, judge2

SIMS = 20000          # random runs drawn for a run's luck distribution


def key(r: dict) -> str:
    return "judge2" if r.get("judge2_score") is not None else "judge"


def judged(r: dict) -> bool:
    """A layout with a luck number: judged, and not a fixed floor (every seed the same)."""
    return (r.get("judge2_score") is not None or r.get("judge_score") is not None) and not r.get("judge_fixed") \
        and not r.get("judge2_fixed")


def delta(r: dict) -> float:
    """This layout's score minus the median random layout's (negative = faster)."""
    if key(r) == "judge2":
        return float(r["judge2_vs_median"])
    return float(r.get("judge_vs_median") or 0.0)


def reference(r: dict, kind: str = "pod") -> np.ndarray | None:
    """The sublevel's 1000 random layouts, as seconds against their median."""
    if key(r) == "judge2":
        ref = judge2.reference(f"{r['cave']}-{r['sublevel']}")
        return ref - r["judge2_median"]
    ref = cavegen.reference_scores(r["cave"], r["sublevel"], kind)
    return None if ref is None else np.asarray(ref, dtype=float) - r["judge_median"]


def faster_than(r: dict, kind: str = "pod") -> float:
    """% of random layouts this one beats (ties count half)."""
    ref = reference(r, kind)
    if ref is None or not len(ref):
        return 100.0 - r.get("judge_rank", 50.0)
    d = delta(r)
    return float(100.0 * (np.sum(ref > d + 1e-9) + 0.5 * np.sum(np.abs(ref - d) <= 1e-9)) / len(ref))


def simulate(rows: list[dict], kind: str = "pod", sims: int = SIMS, seed: int = 1) -> np.ndarray:
    """Totals of `sims` random runs over the same sublevels as `rows` (one random layout each)."""
    rng = np.random.default_rng(seed)
    total = np.zeros(sims)
    for r in rows:
        ref = reference(r, kind)
        if ref is not None and len(ref):
            total += rng.choice(ref, sims)
    return total


def percentile(total: float, samples: np.ndarray) -> float:
    """% of random runs this total beats (lower = faster)."""
    return float(100.0 * np.mean(samples > total))


def describe(p: float) -> str:
    """'luckier than 83% of random runs'."""
    if p >= 99.5:
        return "luckier than 99.5% of random runs"
    if p <= 0.5:
        return "unluckier than 99.5% of random runs"
    return f"luckier than {p:.0f}% of random runs"
