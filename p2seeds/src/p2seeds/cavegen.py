"""Render layouts with the vendored CaveGen (compiled on first use)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CAVEGEN = ROOT / "vendor" / "CaveGen"
BUILD = ROOT / "data" / "build" / "cavegen"
REGION = "us"     # CaveGen -region: "jpn" for Japanese runs (its own caveinfo files)


def _region_args() -> list[str]:
    return [] if REGION == "us" else ["-region", REGION]


def set_region_for(entries) -> None:
    """Pick the region from a run's entries (seeds.json rows or results with `lang`)."""
    global REGION
    langs = {(e.get("lang") if isinstance(e, dict) else getattr(e, "lang", None)) or "en" for e in entries}
    REGION = "jpn" if langs == {"ja"} else "us"


def ensure_built() -> Path:
    if not (BUILD / "CaveGen.class").exists():
        if not CAVEGEN.exists():
            raise FileNotFoundError(f"CaveGen not found at {CAVEGEN}; run scripts/setup_vendor")
        BUILD.mkdir(parents=True, exist_ok=True)
        sources = [str(p) for p in CAVEGEN.glob("*.java")]
        subprocess.run(["javac", "-nowarn", "-encoding", "UTF-8", "--release", "8", "-d", str(BUILD), *sources],
                       check=True, capture_output=True)
    return BUILD


def render(cave_id: str, sublevel: int, seed: int, dest: str | Path, extra_args: tuple[str, ...] = ()) -> Path:
    """Generate `cave_id`-`sublevel` from `seed` and copy the image to `dest`."""
    build = ensure_built()
    seed_hex = f"{seed & 0xFFFFFFFF:08X}"
    cmd = ["java", "-cp", str(build), "CaveGen", "cave", cave_id, str(sublevel), "-seed", f"0x{seed_hex}",
           "-noprints", "-nostats", *_region_args(), *extra_args]
    subprocess.run(cmd, cwd=CAVEGEN, check=True, capture_output=True, timeout=120)
    out = CAVEGEN / "output" / f"{cave_id}-{sublevel}" / f"{seed_hex}.png"
    if not out.exists():
        raise FileNotFoundError(f"CaveGen produced no image at {out}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, dest)
    return dest


@dataclass
class Judgement:
    kind: str           # CaveGen judge type, e.g. "pod"
    score: float        # CaveGen's estimate; for "pod" and "at", seconds to clear the sublevel (lower is better)
    rank: float         # percent of the 1000 reference layouts in rank_file.txt that score lower
    median: float | None  # median score of those reference layouts
    fixed: bool = False   # every reference layout scores the same (boss or fixed floor): no luck involved

    @property
    def vs_median(self) -> float | None:
        return None if self.median is None else self.score - self.median


_JUDGE_LINE = re.compile(r"Judge: (\S+) ([0-9A-Fa-f]{8}) -> (-?[0-9.]+) \(([0-9.]+)%")


def judge(cave_id: str, sublevel: int, seed: int, kind: str = "pod") -> Judgement | None:
    """Score one layout with CaveGen's judge. None if CaveGen has no judge for this sublevel."""
    build = ensure_built()
    cmd = ["java", "-cp", str(build), "CaveGen", "cave", cave_id, str(sublevel),
           "-seed", f"0x{seed & 0xFFFFFFFF:08X}", "-noimages", "-judge", kind, *_region_args()]
    out = subprocess.run(cmd, cwd=CAVEGEN, capture_output=True, text=True, timeout=120).stdout
    m = _JUDGE_LINE.search(out)
    if not m:
        return None
    ref = reference_scores(cave_id, sublevel, kind)
    median = float(np.median(ref)) if ref is not None else None
    fixed = ref is not None and float(ref.min()) == float(ref.max())
    return Judgement(kind, float(m.group(3)), float(m.group(4)), median, fixed)


def reference_scores(cave_id: str, sublevel: int, kind: str = "pod") -> np.ndarray | None:
    """The 1000 sorted reference scores CaveGen ranks against (files/rank_file.txt)."""
    key = f"{cave_id}-{sublevel}-{kind};"
    with open(CAVEGEN / "files" / "rank_file.txt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith(key):
                return np.array([float(x) for x in line.strip().split(";")[1:] if x])
    return None
