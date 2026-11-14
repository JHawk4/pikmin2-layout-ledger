"""Count the treasures collected on each sublevel by spotting the treasure panel.

Every treasure brought back to the ship in a cave shows a full-width panel
("Value ... / Total ... / 10000") at the bottom of the screen. Its labels and
yellow-green bars always sit in the same place, so a template of the fixed part
(the numbers are left out) finds it in any stream layout once the game feed is
scaled to 480x360.

The count per sublevel shows when a runner took more or fewer treasures than
others did on the same sublevel, which changes how long it takes regardless of
the layout. Those plays are left out of the judge calibration.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .feed import Feed
from .video import Video

TEMPLATE = Path(__file__).parent / "data" / "panel" / "treasure_panel.png"
THRESHOLD = 0.7
STEP = 8                 # frames between samples (a panel stays up for a few seconds)
MERGE = 40               # a hit within this many frames of the last one is the same panel (one lasts ~4 s)


def _template() -> np.ndarray:
    return cv2.imread(str(TEMPLATE), cv2.IMREAD_GRAYSCALE)


def panel_score(feed_gray: np.ndarray, tpl: np.ndarray | None = None) -> tuple[float, np.ndarray]:
    tpl = _template() if tpl is None else tpl
    g = cv2.resize(feed_gray, (480, 360), interpolation=cv2.INTER_AREA)
    region = g[216:349, 0:300]
    score = float(cv2.minMaxLoc(cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED))[1])
    return score, g


def find_panels(video: Video, feed: Feed, start: int, stop: int) -> list[tuple[int, int]]:
    """(first, last) sampled frame of each treasure panel seen in [start, stop)."""
    tpl = _template()
    hits = [i for i, gray in video.sample(STEP, start, stop) if panel_score(feed.crop(gray), tpl)[0] >= THRESHOLD]
    return spans(hits)


def spans(hits: list[int]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for i in hits:
        if out and i - out[-1][1] <= MERGE:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [(a, b) for a, b in out]


def merge(hits: list[int]) -> list[int]:
    """First frame of each panel: hits within MERGE frames of the previous hit are the same panel."""
    panels, last = [], None
    for i in hits:
        if last is None or i - last > MERGE:
            panels.append(i)
        last = i
    return panels


def count_run(out_dir: Path, progress=None) -> dict:
    """Count panels between consecutive entries of one cave; saves treasures.json."""
    data = json.loads((out_dir / "seeds.json").read_text(encoding="utf-8"))
    meta, entries = data.get("meta", {}), [e for e in data["entries"] if e.get("cave")]
    video = Video(meta["video"])
    feed = Feed(*meta["feed"])
    counts = {}
    pairs = [(a, b) for a, b in zip(entries, entries[1:])
             if a["cave"] == b["cave"] and a.get("sublevel") and b.get("sublevel") == a["sublevel"] + 1]
    for k, (a, b) in enumerate(pairs):
        found = find_panels(video, feed, a["frame"], b["frame"])
        counts[str(a["frame"])] = {"cave": a["cave"], "sublevel": a["sublevel"], "treasures": len(found),
                                   "panel_frames": [f for f, _ in found], "panels": [list(p) for p in found]}
        if progress:
            progress(k + 1, len(pairs), a, len(found))
    (out_dir / "treasures.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    return counts


def load(out_dir: Path) -> dict:
    p = out_dir / "treasures.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    for v in data.values():           # files written before panel merging was fixed held split panels
        if "panels" not in v:
            v["panel_frames"] = merge(v["panel_frames"])
        v["treasures"] = len(v["panel_frames"])
    return data


# ---- poko values -------------------------------------------------------------
#
# A panel's "Value" is the poko value of the treasure just collected. Which
# treasures a sublevel holds (and their values) comes from CaveGen for the
# layout seed, so each Value only has to be told apart from a few candidates:
# the Value box is compared, digit slot by digit slot, with each candidate
# number. Treasures carried by enemies count too.

DIGITS_DIR = Path(__file__).parent / "data" / "panel"
HELPER_SRC = Path(__file__).resolve().parents[2] / "java" / "SublevelItems.java"
VALUE_ROWS = (258, 283)      # at 480x360
LAST_DIGIT_X, DIGIT_PITCH, DIGIT_W = 326.0, 25.0, 24


def _digit_templates() -> dict[str, np.ndarray]:
    return {p.stem[-1]: np.load(p).reshape(-1) for p in DIGITS_DIR.glob("digit_*.npy")}


def _norm(img: np.ndarray) -> np.ndarray:
    a = img.astype(np.float32)
    a = a - cv2.GaussianBlur(a, (0, 0), 3)          # keep the strokes, drop the box shading
    a = a.reshape(-1) - a.mean()
    return a / (np.linalg.norm(a) + 1e-6)


def _slot(g480: np.ndarray, k: int, dx: float = 0.0) -> np.ndarray:
    y0, y1 = VALUE_ROWS
    cx = LAST_DIGIT_X - DIGIT_PITCH * k + dx
    crop = g480[y0:y1, int(round(cx - DIGIT_W / 2)): int(round(cx + DIGIT_W / 2))]
    return cv2.resize(crop, (22, 25), interpolation=cv2.INTER_AREA)


def _blankness(slot: np.ndarray) -> float:
    inner = slot[5:-5, 3:-3].astype(np.float32)
    return float(np.percentile(inner, 97) - np.median(inner))      # < ~22 means no digit here


def value_score(g480: np.ndarray, value: int, templates) -> float:
    """How well the Value box shows `value` (higher is better), best over a small shift."""
    digits = str(value)[::-1]
    best = -9.0
    for dx in (-2, -1, 0, 1, 2):
        s = 0.0
        for k, d in enumerate(digits):
            s += float(_norm(_slot(g480, k, dx)) @ templates[d])
        s /= len(digits)
        if len(digits) < 3 and _blankness(_slot(g480, len(digits), dx)) > 30:
            s -= 0.3                                    # a digit where the candidate has none
        best = max(best, s)
    return best


def ensure_helper() -> Path:
    from . import cavegen
    build = cavegen.ensure_built()
    if not (build / "SublevelItems.class").exists():
        import subprocess
        subprocess.run(["javac", "-nowarn", "-encoding", "UTF-8", "--release", "8", "-cp", str(build), "-d", str(build),
                        str(HELPER_SRC)], check=True, capture_output=True)
    return build


def sublevel_items(triples: list[tuple[str, int, int]]) -> dict[tuple[str, int, int], list[tuple[str, int]]]:
    """(cave, sublevel, layout seed) -> [(treasure, pokos)] placed on that layout."""
    import subprocess
    from . import cavegen
    build = ensure_helper()
    args = [x for c, s, seed in triples for x in (c, str(s), f"0x{seed & 0xFFFFFFFF:08X}")]
    out = subprocess.run(["java", "-cp", str(build), "SublevelItems", *args], cwd=cavegen.CAVEGEN,
                         capture_output=True, text=True, timeout=600).stdout
    result, key = {}, None
    for line in out.splitlines():
        if line.startswith("# "):
            c, s, seed = line[2:].split()
            key = (c, int(s), int(seed, 16))
            result[key] = []
        elif key and line.strip():
            name, pokos, _ = line.split("\t")
            result[key].append((name, int(pokos)))
    return result


def choose(video, feed, panels, avail, templates) -> tuple[list, float | None]:
    """Which treasures the panels showed. When every treasure on the sublevel was collected
    the answer is all of them; otherwise the best-matching set (and how clearly it won)."""
    import itertools
    m = len(panels)
    if m == 0 or not avail:
        return [None] * m, None
    if m >= len(avail):
        return [list(x) for x in avail] + [None] * (m - len(avail)), None
    values = sorted({p for _, p in avail})
    score = []
    for _, last in panels:
        frames = [video.frame_at(last - off) for off in (8, 16, 24)]
        g = [cv2.resize(feed.crop(f), (480, 360), interpolation=cv2.INTER_CUBIC) for f in frames if f is not None]
        score.append({val: float(np.mean([value_score(x, val, templates) for x in g])) for val in values})
    totals = {}
    for combo in itertools.permutations(range(len(avail)), m):
        s = sum(score[i][avail[j][1]] for i, j in enumerate(combo))
        key = tuple(sorted(avail[j][1] for j in combo))
        if s > totals.get(key, (-1e9, None))[0]:
            totals[key] = (s, combo)
    ranked = sorted(totals.values(), key=lambda x: -x[0])
    best = ranked[0][1]
    margin = (ranked[0][0] - ranked[1][0]) / m if len(ranked) > 1 else None   # only sets with different pokos compete
    left = [avail[j] for j in range(len(avail)) if j not in best]
    picks = []
    for j in best:
        name, pokos = avail[j]
        twins = [n for n, p in left if p == pokos]          # same value, so the panel cannot tell them apart
        picks.append([" or ".join([name] + twins), pokos])
    return picks, margin


def read_values(out_dir: Path, progress=None) -> dict:
    """Add each panel's treasure and value (and the sublevel's poko total) to treasures.json."""
    data = json.loads((out_dir / "seeds.json").read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    entries = {str(e["frame"]): e for e in data["entries"] if e.get("cave")}
    counts = load(out_dir)
    keys = [k for k, v in counts.items() if entries.get(k, {}).get("layout_seed")]
    triples = [(counts[k]["cave"], counts[k]["sublevel"], int(entries[k]["layout_seed"], 16)) for k in keys]
    items = sublevel_items(triples)
    video, feed = Video(meta["video"]), Feed(*meta["feed"])
    templates = _digit_templates()
    for n, (k, t) in enumerate(zip(keys, triples)):
        v = counts[k]
        avail = list(items.get(t, []))
        v["items"] = [list(x) for x in avail]
        panels = v.get("panels", [])
        v["collected"], v["value_margin"] = choose(video, feed, panels, avail, templates)
        v["pokos"] = sum(p[1] for p in v["collected"] if p)
        if progress:
            progress(n + 1, len(keys), v)
    (out_dir / "treasures.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    return counts
