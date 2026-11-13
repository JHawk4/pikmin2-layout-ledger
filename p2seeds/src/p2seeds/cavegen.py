"""Render layouts with the vendored CaveGen (compiled on first use)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CAVEGEN = ROOT / "vendor" / "CaveGen"
BUILD = ROOT / "data" / "build" / "cavegen"


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
           "-noprints", "-nostats", *extra_args]
    subprocess.run(cmd, cwd=CAVEGEN, check=True, capture_output=True, timeout=120)
    out = CAVEGEN / "output" / f"{cave_id}-{sublevel}" / f"{seed_hex}.png"
    if not out.exists():
        raise FileNotFoundError(f"CaveGen produced no image at {out}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, dest)
    return dest
