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


SALVAGED = Path(__file__).parent / "data" / "panel" / "salvaged.png"   # "Treasures Salvaged" header
SALVAGED_THRESHOLD = 0.6


def scan(video: Video, feed: Feed, progress=None) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """One pass over the whole video: (treasure panel spans, cave-complete screen spans).

    The cave-complete screen ("Treasures Salvaged", listing the cave's treasures and its
    pokos from creatures) marks leaving a cave: what follows until the next cave is surface."""
    tpl = _template()
    sal = cv2.imread(str(SALVAGED), cv2.IMREAD_GRAYSCALE)
    p_hits, s_hits = [], []
    for i, gray in video.sample(STEP):
        score, g = panel_score(feed.crop(gray), tpl)
        if score >= THRESHOLD:
            p_hits.append(i)
        elif float(cv2.matchTemplate(g[0:90, 0:360], sal, cv2.TM_CCOEFF_NORMED).max()) >= SALVAGED_THRESHOLD:
            s_hits.append(i)
        if progress and i % (STEP * 5000) == 0:
            progress(i, video.frame_count)
    exits: list[list[int]] = []
    for i in s_hits:                               # the "Cave complete!" overlay can split one screen
        if exits and i - exits[-1][1] <= 300:
            exits[-1][1] = i
        else:
            exits.append([i, i])
    return spans(p_hits), [(a, b) for a, b in exits]


def count_run(out_dir: Path, progress=None) -> dict:
    """Find every treasure panel and assign it to a sublevel or to the surface; saves treasures.json.

    A sublevel runs from its entry screen to the next sublevel's; a cave's last sublevel runs
    to the cave-complete screen (its "exit"), and from there to the next cave is surface.
    Surface panels are kept under "surface:<frame>" keys (cave "surface"): their pokos count
    in the run's total but belong to no sublevel."""
    data = json.loads((out_dir / "seeds.json").read_text(encoding="utf-8"))
    meta, entries = data.get("meta", {}), [e for e in data["entries"] if e.get("cave") and e.get("sublevel")]
    video = Video(meta["video"])
    feed = Feed(*meta["feed"])
    panels, exits = scan(video, feed, progress)
    windows = []                                   # (start, end, key, entry or None, exit span)
    for k, e in enumerate(entries):
        nxt = entries[k + 1] if k + 1 < len(entries) else None
        if nxt and nxt["cave"] == e["cave"] and nxt["sublevel"] == e["sublevel"] + 1:
            windows.append((e["frame"], nxt["frame"], str(e["frame"]), e, None))
        else:                                      # last sublevel of the cave: until it is left
            stop = nxt["frame"] if nxt else video.frame_count
            ex = next((x for x in exits if e["frame"] < x[0] < stop), None)
            windows.append((e["frame"], ex[0] if ex else stop, str(e["frame"]), e, ex))
    counts = {}
    for w0, w1, key, e, ex in windows:
        counts[key] = {"cave": e["cave"], "sublevel": e["sublevel"], "panels": [], "last": ex is not None or None,
                       "window": [w0, w1]}
        if ex:
            counts[key]["exit"] = list(ex)
    for a, b in panels:
        w = next((w for w in windows if w[0] <= a < w[1]), None)
        if w is None:
            counts[f"surface:{a}"] = {"cave": "surface", "sublevel": None, "panels": [[a, b]]}
        else:
            counts[w[2]]["panels"].append([a, b])
    for v in counts.values():
        v["panel_frames"] = [a for a, _ in v["panels"]]
        v["treasures"] = len(v["panels"])
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
VALUE_BLANK = 0.38           # Value slot blankness relative to the ones digit's (always a digit): empty
                             # slots measure 0.18-0.31, a thin leading 1 0.45+, on colour and grey captures


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
        # the number's length is clear from whether the next slot is empty: an empty slot scores
        # at most ~33 on blankness, a digit at least ~43 (measured on 60 hand-read panels)
        ref = max(_blankness(_slot(g480, 0, dx)), 1e-6)
        nxt = _blankness(_slot(g480, len(digits), dx)) / ref
        if len(digits) < 3 and nxt > VALUE_BLANK:
            s -= 1.0                                    # a digit where the candidate has none
        if len(digits) >= 2 and _blankness(_slot(g480, len(digits) - 1, dx)) / ref < VALUE_BLANK:
            s -= 1.0                                    # the candidate's leading digit is not there
        best = max(best, s)
    return best


# The panel's second line, "Total ... 0x [ 1112 ] / 10000", is the run's poko total after this
# treasure. A total that rose by more than the treasure's value means pokos from enemies
# ("bug pokos") came in since the previous panel. Same font as the Value; fitted on known totals.
TOTAL_ROW, TOTAL_LAST_X, TOTAL_PITCH = 287, 325.0, 24.0
TOTAL_BLANK = 55.0           # blankness below this: no digit in the slot (digits score 60+, empty box ~30)
SLOT_JITTER = (-2, -1, 0, 1, 2)   # px each digit slot may shift on its own


def _total_slot(g480: np.ndarray, k: int, dx: float = 0.0) -> np.ndarray:
    cx = TOTAL_LAST_X - TOTAL_PITCH * k + dx
    crop = g480[TOTAL_ROW:TOTAL_ROW + 25, int(round(cx - 12)): int(round(cx + 12))]
    return cv2.resize(crop, (22, 25), interpolation=cv2.INTER_AREA)


MAX_BUG = 2000              # most pokos from enemies between two treasure panels we consider
OVER_CAP = 1.5              # score cost of creature pokos beyond what the layouts allow
BUG_PENALTY = 0.0001       # score per bug poko (digit scores are summed, ~0.5-0.9 per matching digit)


def panel_alignment(out_dir: Path, video: Video, feed: Feed, panels: list) -> np.ndarray:
    """Affine fix (2x3) that lines this run's panel digits up with the slots, cached in
    panel_align.json. Captures differ slightly (a game area that is not exactly 4:3, a few
    pixels of crop), and a few pixels are enough to misread digits; the shift and scale where
    the digits match the templates best are kept."""
    path = out_dir / "panel_align.json"
    if path.exists():
        return np.float32(json.loads(path.read_text())["matrix"])
    pick = panels[:: max(1, len(panels) // 10)][:10]
    gs = [cv2.resize(feed.crop(video.frame_at((a + b) // 2)), (480, 360), interpolation=cv2.INTER_CUBIC)
          for a, b, *_ in pick]
    tmat = np.stack(list(_total_templates().values()))
    vmat = np.stack(list(_digit_templates().values()))

    def score(M):
        sc = 0.0
        for g in gs:
            h = cv2.warpAffine(g, M, (480, 360), borderMode=cv2.BORDER_REPLICATE)
            for k in range(3):
                sc += float((tmat @ _norm(_total_slot(h, k))).max())
            sc += float((vmat @ _norm(_slot(h, 0))).max())
        return sc / max(1, len(gs)) / 4

    def mat(scale, dx, dy):                       # scale about the digit area, then shift
        cx, cy = 300.0, 285.0
        return np.float32([[scale, 0, cx - scale * cx + dx], [0, scale, cy - scale * cy + dy]])
    best = (score(mat(1, 0, 0)), 1.0, 0, 0)
    for dx in range(-6, 7, 2):
        for dy in range(-6, 7, 2):
            c = score(mat(1, dx, dy))
            if c > best[0]:
                best = (c, 1.0, dx, dy)
    _, _, bx, by = best
    for scale in (0.97, 0.98, 0.99, 1.0, 1.01, 1.02, 1.03):     # refine around the best shift
        for dx in range(bx - 2, bx + 3):
            for dy in range(by - 2, by + 3):
                c = score(mat(scale, dx, dy))
                if c > best[0]:
                    best = (c, scale, dx, dy)
    M = mat(*best[1:])
    path.write_text(json.dumps({"matrix": M.tolist(), "score": best[0], "scale": best[1], "dx": best[2], "dy": best[3]}))
    return M


def _aligned(g: np.ndarray, M: np.ndarray | None) -> np.ndarray:
    return g if M is None else cv2.warpAffine(g, M, (480, 360), borderMode=cv2.BORDER_REPLICATE)


def _total_templates() -> dict[str, np.ndarray]:
    """Digit templates for the Total line (trained on hand-read totals, train_totals in the repo history)."""
    return {p.stem[-1]: np.load(p).reshape(-1) for p in DIGITS_DIR.glob("total_digit_*.npy")}


def _total_slots(g480s: list[np.ndarray], templates) -> tuple[np.ndarray, np.ndarray]:
    """Per slot (right to left, 4 slots): mean digit scores (4 x 10) and mean blankness."""
    sc = np.zeros((4, 10))
    bl = np.zeros(4)
    tmat = np.stack([templates[str(d)] for d in range(10)])
    for g in g480s:
        for k in range(4):
            # each digit at its best small shift: captures stretch the panel a little differently,
            # and 2 px off is enough to read a 0 as a 7 (the run-wide alignment can't fix the pitch)
            ss = [_total_slot(g, k, dx) for dx in SLOT_JITTER]
            bl[k] += max(_blankness(s) for s in ss)
            sc[k] += np.max([tmat @ _norm(s) for s in ss], axis=0)
    return sc / max(1, len(g480s)), bl / max(1, len(g480s))


def total_score(sc: np.ndarray, bl: np.ndarray, total: int) -> float:
    """How well the slot scores show `total` (higher is better)."""
    digits = str(total)[::-1]
    if len(digits) > 4:
        return -9.0
    s = sum(sc[k, int(d)] for k, d in enumerate(digits)) / len(digits)
    for k in range(len(digits), 4):                 # slots that should be empty
        if bl[k] > TOTAL_BLANK and k < 3:
            s -= 0.3
    return s


_ALL = np.arange(10000)
_DIG = np.stack([(_ALL // 10 ** k) % 10 for k in range(4)])          # digit k (right to left) of each total
_LEN = np.where(_ALL >= 1000, 4, np.where(_ALL >= 100, 3, np.where(_ALL >= 10, 2, 1)))


def _total_scores(sc: np.ndarray, bl: np.ndarray) -> np.ndarray:
    """total_score for every total 0..9999 at once."""
    s = np.zeros(10000)
    for k in range(4):
        used = _LEN > k
        s += np.where(used, sc[k][_DIG[k]], 0.0)
        s -= np.where(~used & (bl[k] > TOTAL_BLANK) & (k < 3), 0.3 * _LEN, 0.0)   # (mean below is over _LEN)
    return s                      # summed: each digit is evidence (a 4-digit total outweighs a 3-digit value)


def read_totals(out_dir: Path, progress=None) -> dict:
    """Read every panel's Value and Total, then the bug pokos between panels.

    The Total after a panel is the previous Total + this panel's Value + whatever came from
    enemies since (never negative). All panels are decoded together (dynamic programming over
    the total, 0..9999): each panel scores its Value among the treasures CaveGen placed on the
    sublevel and its Total digit by digit, and each unexplained poko costs BUG_PENALTY, so the
    whole sequence that fits the digits best wins. Adds to each treasures.json entry, per panel:
    "values", "totals" and "bug_before" (pokos since the previous panel beyond its treasure)."""
    data = json.loads((out_dir / "seeds.json").read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    counts = load(out_dir)
    video, feed = Video(meta["video"]), Feed(*meta["feed"])
    templates = _digit_templates()
    ttemplates = _total_templates()
    panels = sorted((a, b, key, i) for key, t in counts.items() for i, (a, b) in enumerate(t.get("panels", [])))
    M = panel_alignment(out_dir, video, feed, panels) if panels else None
    steps = []                                   # per panel: (values, value scores, total scores)
    for n, (a, b, key, i) in enumerate(panels):
        gs = []
        for f in range(a + 8, max(a + 9, b - 8), 12):
            g = video.frame_at(f)
            if g is not None:
                gs.append(_aligned(cv2.resize(feed.crop(g), (480, 360), interpolation=cv2.INTER_CUBIC), M))
        # the treasures CaveGen placed on the sublevel; on the surface (or without a seed) any value
        options = sorted({int(x[1]) for x in counts[key].get("items") or []}) or list(range(1, 1000))
        vs = value_scores(gs, options, templates) if gs else np.zeros(len(options))
        ts = _total_scores(*_total_slots(gs, ttemplates)) if gs else np.zeros(10000)
        steps.append((options, vs, ts))
        if progress:
            progress(n + 1, len(panels), key, None)
    # Viterbi over the total. best[T] = best score of a sequence ending at total T.
    # T_k = T_{k-1} + v_k + bug, bug >= 0, costing BUG_PENALTY per poko. Creatures can give no
    # more than they are worth: a bug beyond the cap of the cave sublevels between the two
    # panels costs OVER_CAP as well (a misread Value or Total is then the likelier story).
    windows = {k: (v["window"], v.get("creature_cap")) for k, v in counts.items() if v.get("window")}
    prev = np.full(10000, -np.inf)
    prev[0] = 0.0
    back = []
    prev_end = 0
    for (a, b, key, i), (options, vs, ts) in zip(panels, steps):
        cap = sum((c if c is not None else 300) for (w0, w1), c in windows.values() if min(w1, a) > max(w0, prev_end))
        m = int(min(MAX_BUG, cap + 5))
        prev_end = b
        A = prev + BUG_PENALTY * _ALL             # A[T'] - pen*x = prev[T'] - pen*(x - T')
        W, Widx = A.copy(), _ALL.copy()           # best start within the cap: x - m <= T' <= x
        for d in range(1, m + 1):
            sh = np.concatenate([np.full(d, -np.inf), A[:-d]])
            better = sh > W
            W = np.where(better, sh, W)
            Widx = np.where(better, _ALL - d, Widx)
        C = np.maximum.accumulate(A)              # any start (beyond the cap, penalized)
        Cidx = np.maximum.accumulate(np.where(A == C, _ALL, 0))
        over = C - OVER_CAP > W
        start_score = np.where(over, C - OVER_CAP, W)
        start_idx = np.where(over, Cidx, Widx)
        cur = np.full(10000, -np.inf)
        choice = np.zeros(10000, int)
        best_prev = np.zeros(10000, int)
        for j, val in enumerate(options):
            x = _ALL - val                        # the total before this treasure and its creatures
            xc = np.clip(x, 0, 9999)
            cand = np.where(x >= 0, start_score[xc] - BUG_PENALTY * xc, -np.inf) + vs[j] + ts
            better = cand > cur
            cur = np.where(better, cand, cur)
            choice = np.where(better, j, choice)
            best_prev = np.where(better, start_idx[xc], best_prev)
        back.append((choice, best_prev))
        prev = cur
    T = int(np.argmax(prev))
    path = []
    for (choice, best_prev), (options, _, _) in zip(reversed(back), reversed(steps)):
        path.append((T, options[choice[T]]))
        T = int(best_prev[T])
    path.reverse()
    last = 0
    for (a, b, key, i), (tot, val) in zip(panels, path):
        t = counts[key]
        for name in ("totals", "values", "bug_before"):
            t.setdefault(name, [None] * len(t.get("panels", [])))
        t["totals"][i], t["values"][i], t["bug_before"][i] = int(tot), int(val), int(tot - last - val)
        last = tot
    allocate_bugs(counts)
    (out_dir / "treasures.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    return counts


def creature_cap(cave: str, sublevel: int, seed: int) -> int | None:
    """Most pokos creatures can give on this layout (None if CaveGen3 can't tell)."""
    from . import cavegen, cg3
    if not cg3.available() or cavegen.REGION != "us":
        return None
    try:
        return cg3.layout(cave, sublevel, seed).get("creature_pokos")
    except ValueError:
        return None


MAX_CLIPPED = 30            # a sublevel whose creature pokos needed more clipping has no reliable poko count


def reliable_pokos(t: dict | None) -> int | None:
    """A sublevel's pokos (treasure + creature), or None when they could not be read reliably."""
    if not t or t.get("pokos") is None or (t.get("bug_clipped") or 0) > MAX_CLIPPED:
        return None
    return t["pokos"]


def _missed_treasures(counts: dict, keys: list[str], amount: float) -> list[tuple[str, str, int]]:
    """Uncounted treasures on these sublevels whose values add up to `amount` (within 5%, at
    least 5 pokos), fewest first: [(sublevel key, name, value)], or [] if none fit."""
    import itertools
    pool = []
    for k in keys:
        v = counts[k]
        seen = list(v.get("values") or []) + [x[1] for x in v.get("inferred") or []]
        for name, val in v.get("items") or []:
            if val in seen:
                seen.remove(val)                 # already counted
            else:
                pool.append((k, name, int(val)))
    tol = max(5.0, 0.05 * amount)
    for n in (1, 2, 3):
        best = None
        for combo in itertools.combinations(pool, n):
            gap = abs(sum(c[2] for c in combo) - amount)
            if gap <= tol and (best is None or gap < best[0]):
                best = (gap, combo)
        if best:
            return list(best[1])
    return []


def allocate_bugs(counts: dict) -> None:
    """Give each sublevel its pokos from creatures ("bug_pokos").

    The pokos a panel's Total shows beyond its treasure came in since the previous panel.
    Creatures only give pokos in caves, so they belong to the cave sublevels between the two
    panels (never the surface). A sublevel can give no more than its creatures are worth
    ("creature_cap": every creature CaveGen places on the layout, at the judges' poko values),
    so the pokos are shared by time spent in each sublevel among those with room left, up to
    their caps. Pokos beyond what every sublevel in between could hold are a misread or a
    missed treasure: they are clipped and recorded as "bug_clipped" on the panel's sublevel."""
    panels = sorted((a, b, key, i) for key, t in counts.items() for i, (a, b) in enumerate(t.get("panels", [])))
    windows = {k: v["window"] for k, v in counts.items() if v.get("window")}
    for v in counts.values():
        if v.get("window"):
            v["bug_pokos"], v["bug_clipped"], v["inferred"] = 0.0, 0, []
    prev_end = 0
    for a, b, key, i in panels:
        bug = float((counts[key].get("bug_before") or [0] * (i + 1))[i] or 0)
        if bug > 0:
            time = {k: max(0, min(w[1], a) - max(w[0], prev_end)) for k, w in windows.items()}
            room = {k: (counts[k].get("creature_cap") if counts[k].get("creature_cap") is not None else float("inf"))
                       - counts[k]["bug_pokos"] for k, x in time.items() if x > 0}
            left = bug
            while left > 1e-6:
                open_ = {k: time[k] for k, r in room.items() if r > 1e-6}
                if not open_:
                    break
                tot = sum(open_.values())
                given = 0.0
                for k, x in open_.items():
                    g = min(room[k], left * x / tot)
                    counts[k]["bug_pokos"] += g
                    room[k] -= g
                    given += g
                left -= given
                if given < 1e-6:
                    break
            if left > 0.5 and counts[key].get("cave") == "surface":
                # creatures give nothing on the surface: the surface treasure's Value was misread
                # (read freely, it most often loses its hundreds digit)
                counts[key]["values"][i] += int(round(left))
                left = 0.0
            if left > 0.5:
                # treasures collected without their panel being read (two panels back to back
                # merge into one): uncounted treasures on these sublevels that add up to the rest
                found = _missed_treasures(counts, [k for k, x in time.items() if x > 0], left)
                for k, name, val in found:
                    counts[k]["inferred"].append([name, val])
                    left -= val
            if left > 0.5:
                owner = key if counts[key].get("window") else max(time, key=time.get, default=None)
                if owner and owner in counts:
                    counts[owner]["bug_clipped"] += int(round(left))
        prev_end = b
    for v in counts.values():
        if "bug_pokos" in v:
            v["bug_pokos"] = round(v["bug_pokos"], 1)
            # the sublevel's pokos: its treasures (each panel's Value) and its creatures
            v["treasure_pokos"] = sum(x for x in v.get("values") or [] if x) + sum(x[1] for x in v.get("inferred") or [])
            v["pokos"] = int(round(v["treasure_pokos"] + v["bug_pokos"]))


def refresh_bugs(out_dir: Path) -> dict:
    """Recompute creature caps and the split of creature pokos from saved readings (no video)."""
    data = json.loads((out_dir / "seeds.json").read_text(encoding="utf-8"))
    from . import cavegen
    cavegen.set_region_for(data["entries"])
    seeds = {str(e["frame"]): e for e in data["entries"] if e.get("layout_seed")}
    counts = load(out_dir)
    for k, v in counts.items():
        if v.get("window") and k in seeds:
            v["creature_cap"] = creature_cap(v["cave"], v["sublevel"], int(seeds[k]["layout_seed"], 16))
    allocate_bugs(counts)
    (out_dir / "treasures.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    return counts


def value_scores(g480s: list[np.ndarray], values: list[int], templates) -> np.ndarray:
    """value_score averaged over frames, for many candidate values at once.

    Each slot's digit scores and blankness are computed once per frame and shift, then every
    candidate is scored from those (the same rules as value_score). Reading a surface panel
    tries every value 1..999, which was the slow part of read_totals."""
    dxs = (-2, -1, 0, 1, 2)
    nf = len(g480s)
    S = np.zeros((nf, len(dxs), 3, 10))
    B = np.zeros((nf, len(dxs), 3))
    for f, g in enumerate(g480s):
        for j, dx in enumerate(dxs):
            for k in range(3):
                sl = _slot(g, k, dx)
                B[f, j, k] = _blankness(sl)
                v = _norm(sl)
                S[f, j, k] = [float(v @ templates[str(d)]) for d in range(10)]
        B[f] /= np.maximum(B[f, :, :1], 1e-6)         # relative to the ones digit (contrast varies)
    out = np.zeros(len(values))
    for n, value in enumerate(values):
        digits = [int(c) for c in str(value)[::-1]][:3]
        L = len(digits)
        s = sum(S[:, :, k, d] for k, d in enumerate(digits)) / L          # (frames, shifts)
        if L < 3:
            s = s - np.where(B[:, :, L] > VALUE_BLANK, 1.0, 0.0)
        if L >= 2:
            s = s - np.where(B[:, :, L - 1] < VALUE_BLANK, 1.0, 0.0)
        out[n] = float(np.mean(s.max(axis=1))) if nf else 0.0
    return out


def ensure_helper() -> Path:
    from . import cavegen
    build = cavegen.ensure_built()
    if not (build / "SublevelItems.class").exists():
        import subprocess
        subprocess.run(["javac", "-nowarn", "-encoding", "UTF-8", "--release", "8", "-cp", str(build), "-d", str(build),
                        str(HELPER_SRC)], check=True, capture_output=True)
    return build


def sublevel_items(triples: list[tuple[str, int, int]]) -> dict[tuple[str, int, int], list[tuple[str, int]]]:
    """(cave, sublevel, layout seed) -> [(treasure, pokos)] placed on that layout, including
    treasures carried by teki. From CaveGen3 when its bridge is built (US runs), else Java."""
    import subprocess
    from . import cavegen, cg3
    if cg3.available() and cavegen.REGION == "us":
        return {(c, s, seed): [(i["name"].lower(), int(i["value"] or 0)) for i in cg3.layout(c, s, seed)["items"]]
                for c, s, seed in triples}
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
        v["creature_cap"] = creature_cap(*t)
        panels = v.get("panels", [])
        v["collected"], v["value_margin"] = choose(video, feed, panels, avail, templates)
        v["pokos"] = sum(p[1] for p in v["collected"] if p)
        if progress:
            progress(n + 1, len(keys), v)
    (out_dir / "treasures.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    return counts
