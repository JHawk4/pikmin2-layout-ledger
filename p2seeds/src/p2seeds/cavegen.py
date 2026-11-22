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
    """Pick the region from a run's entries (seeds.json rows or results with `lang`). Switch runs
    use CaveGen3's US caveinfo whatever the language (no Switch caveinfo has been compared)."""
    global REGION
    from . import rng
    if rng.active() == "switch":
        REGION = "us"
        return
    langs = {(e.get("lang") if isinstance(e, dict) else getattr(e, "lang", None)) or "en" for e in entries}
    REGION = "jpn" if langs == {"ja"} else "us"


def switch_ready() -> bool:
    """Switch layouts need CaveGen3 (Java CaveGen has only the GC generator): its command line
    for pictures and p2seeds' bridge (cg3.py) for judges and treasures."""
    from . import cg3
    from .views import cavegen3_exe
    return cg3.available() and cavegen3_exe() is not None


def _cg3_seed_args(seed: int) -> list[str]:
    """The seed and generator arguments for CaveGen3's command line."""
    from . import rng
    if rng.active() == "switch":
        return [f"{seed & rng.MASK64:016X}", "--rng", "switch"]
    return [f"{seed & 0xFFFFFFFF:08X}"]


def _need_cavegen3(what: str) -> None:
    from . import rng
    if rng.active() != "gc":
        raise RuntimeError(f"{what} for a Switch layout needs CaveGen3 built with its Switch generator")


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
    """Generate `cave_id`-`sublevel` from `seed` and copy the image to `dest`.

    Drawn by CaveGen3's command line (the same map as its web page, at 80 px per cell like Java
    CaveGen) when it is built; Japanese-region runs and extra CaveGen options still use Java."""
    seed_hex = f"{seed & 0xFFFFFFFF:08X}"
    from .views import cavegen3_exe
    exe = cavegen3_exe()
    if exe is not None and REGION == "us" and not extra_args:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([str(exe), "generate", f"{cave_id}-{sublevel}", *_cg3_seed_args(seed), "--scale", "2", "-o", tmp],
                           check=True, capture_output=True, timeout=120)
            out = next(Path(tmp).glob("*.png"))
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out, dest)
        return dest
    _need_cavegen3("drawing")
    build = ensure_built()
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
    """Score one layout with CaveGen's judge. None if CaveGen has no judge for this sublevel.

    Uses CaveGen3 (same scores, much faster) when its bridge is built and the run is US."""
    from . import cg3
    ref = reference_scores(cave_id, sublevel, kind)
    if cg3.available() and REGION == "us" and ref is not None:
        score = round(cg3.layout(cave_id, sublevel, seed, kind)["score"], 2)   # as Java prints it
        fixed = float(ref.min()) == float(ref.max())
        return Judgement(kind, float(score), cg3.rank(score, ref), float(np.median(ref)), fixed)
    _need_cavegen3("judging")
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
