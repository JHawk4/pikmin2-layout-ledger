"""CaveGen3 bridge: judge scores and treasure lists from the Rust tool in p2seeds/cg3.

CaveGen3 (Desktop/Claude/cavegen3) reproduces CaveGen's generator and judges and runs far
faster than starting Java per layout. The tool is built once with

    cargo build --release --manifest-path p2seeds/cg3/Cargo.toml --target-dir data/build/cg3

and kept running as one process that answers a JSON request per line. If it is not built,
callers fall back to Java CaveGen. CaveGen3 has only the US caveinfo, so Japanese-region
runs also use Java.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXE = ROOT / "data" / "build" / "cg3" / "release" / "p2seeds-cg3.exe"

_proc: subprocess.Popen | None = None


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


def layout(cave_id: str, sublevel: int, seed: int, kind: str = "pod") -> dict:
    """{"score": judge score, "items": [{"name", "value", "carried_by"}]} for one layout."""
    return _ask({"sub": f"{cave_id}-{sublevel}", "seed": f"0x{seed & 0xFFFFFFFF:08X}", "judge": kind})


def rank(score: float, breakpoints) -> float:
    """CaveGen's scoreToRank: percentile (0 = best) of `score` among the rank file's 1000 breakpoints."""
    b = list(breakpoints)
    score = round(100.0 * score) / 100.0
    if score < b[0]:
        return 0.0
    if score > b[-1]:
        return 100.0
    low, hi = 0, len(b) - 1
    while low + 1 < hi:
        mid = (hi + low) // 2
        if score <= b[mid]:
            hi = mid
        else:
            low = mid
    if b[hi] == score:
        low = hi
    dupes = 0
    for x in b[low + 1:]:
        if x != score:
            break
        dupes += 1
    low += dupes // 2
    return low / 10.0
