"""Bridge to judge2 (judge2/crate): the refit Pay Off Debt judge, shown next to CaveGen's.

Built with
    cargo build --release --manifest-path judge2/crate/Cargo.toml --target-dir data/build/judge2

Each run's judge.json entries gain judge2_score, judge2_median (over 1000 evenly spaced
reference seeds of the sublevel, cached in data/build/judge2_ref.json), judge2_vs_median,
judge2_lo / judge2_hi (5th / 95th percentile minus the median) and judge2_skip (treasures
judge2 expects the runner to skip). Pay Off Debt only.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
EXE = ROOT / "data" / "build" / "judge2" / "release" / "judge2.exe"
REF_CACHE = ROOT / "data" / "build" / "judge2_ref.json"

_proc: subprocess.Popen | None = None
_ref: dict | None = None


def available() -> bool:
    return EXE.exists()


def _ask(req: dict) -> dict:
    global _proc
    if _proc is None or _proc.poll() is not None:
        _proc = subprocess.Popen([str(EXE)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    _proc.stdin.write(json.dumps(req) + "\n")
    _proc.stdin.flush()
    reply = json.loads(_proc.stdout.readline())
    if "error" in reply:
        raise ValueError(reply["error"])
    return reply


def reference(sub: str) -> np.ndarray:
    """judge2 scores of 1000 evenly spaced seeds of `sub` (e.g. "SH-6"), cached."""
    global _ref
    if _ref is None:
        _ref = json.loads(REF_CACHE.read_text(encoding="utf-8")) if REF_CACHE.exists() else {}
    if sub not in _ref:
        _ref[sub] = _ask({"sub": sub, "reference": 1000})["pod2"]
        REF_CACHE.parent.mkdir(parents=True, exist_ok=True)
        REF_CACHE.write_text(json.dumps(_ref), encoding="utf-8")
    return np.asarray(_ref[sub], dtype=float)


def add_to_run(out_dir: Path, force: bool = False) -> bool:
    """Add judge2 fields to a Pay Off Debt run's judge.json. Returns True if it changed."""
    path = Path(out_dir) / "judge.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("kind", "pod") != "pod" or not available():
        return False
    changed = False
    for e in data["entries"]:
        if not e.get("layout_seed") or not e.get("sublevel") or "judge_score" not in e:
            continue
        if "judge2_score" in e and not force:
            continue
        sub = f"{e['cave']}-{e['sublevel']}"
        try:
            r = _ask({"sub": sub, "seed": e["layout_seed"]})
            ref = reference(sub)
        except ValueError:
            continue
        med = float(np.median(ref))
        choice = max(r["pod2_parts"]["choices"], key=lambda c: c["p"]) if r.get("pod2_parts") else None
        e.update(judge2_score=r["pod2"], judge2_median=med, judge2_vs_median=r["pod2"] - med,
                 judge2_lo=float(np.percentile(ref, 5)) - med, judge2_hi=float(np.percentile(ref, 95)) - med,
                 judge2_fixed=float(ref.min()) == float(ref.max()),
                 # name a skip only when judge2 is fairly sure (near-ties are averaged, ~50/50)
                 judge2_skip=choice["skip"] if choice and choice["p"] >= 0.8 else [])
        changed = True
    if changed:
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return changed
