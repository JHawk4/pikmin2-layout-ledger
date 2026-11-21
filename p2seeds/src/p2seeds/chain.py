"""Link consecutive sublevel entries through the RNG.

Between two sublevel entries the game advances the RNG by a bounded amount:
in the runs checked so far, at most ~140k steps between sublevels of one cave
and ~360k across a day on the surface. Unrelated seeds are ~2^31 apart, so a
seed found within that window of its predecessor is independently confirmed,
and an entry whose letters alone are too few or too noisy (short Japanese
names) can be found by searching only that window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import letters_model, rng
from .analyze import MAX_FIT_RMS_PX
from .search import Candidate, search_near

NEAR = 2_000_000          # window searched after (or before) a known seed
CONFIRM = 4_000_000       # a seed this close to its predecessor counts as confirmed


def _known(r) -> bool:
    return r.letter_seed is not None and r.confidence in ("high", "medium")


def link(results, near: int = NEAR) -> None:
    """Fill `chain_dist` on every result and recover seeds the per-entry search missed.

    `results` are EventResults in video order (one per sublevel entry).
    """
    for r in results:
        r.chain_dist = None
    # only seeds found by the full search AND agreeing with another such seed anchor the
    # window searches; a lone read, even a confident one, could be wrong
    settled = _backbone(results)
    _demote_strays(results, settled)
    before = [(r.letter_seed, r.layout_seed, r.confidence, r.note, r.candidates) for r in results]
    _chains(results)
    filled = _forward(results, near, set(settled))
    _backward(results, near, set(settled) | filled)
    _bridge(results)
    _check_order(results, before, settled)
    for prev, r in zip(results, results[1:]):
        if r.letter_seed is not None and prev.layout_seed is not None:
            r.chain_dist = rng.distance(prev.layout_seed, r.letter_seed, limit=CONFIRM)
    # two seeds each found on their own that also sit within LINK steps of each other:
    # a coincidence has chance ~LINK / 2^31 on top of each one's own small chance
    for prev, r in zip(results, results[1:]):
        if r.chain_dist is not None and r.chain_dist <= LINK and _known(prev) and _known(r):
            for x in (prev, r):
                if x.confidence == "medium":
                    x.confidence = "high"
                    x.note = (x.note + " seed confirmed by its neighbor's").strip()
    # the same for backbone seeds with entries between them (each within LINK per sublevel)
    for a, b in zip(settled, settled[1:]):
        ra, rb = results[a], results[b]
        if _known(ra) and _known(rb) and ra.layout_seed is not None and \
                rng.distance(ra.layout_seed, rb.letter_seed, limit=LINK * (b - a)) is not None:
            for x in (ra, rb):
                if x.confidence == "medium":
                    x.confidence = "high"
                    x.note = (x.note + " seed confirmed by a later or earlier sublevel's").strip()


def _apply(r, cands: list[Candidate], how: str, dist: int | None = None) -> bool:
    """Take the best window match if it is unlikely to be chance (one try per entry)."""
    if not cands or not _good(cands[0]) or r.fit.rms_px > MAX_FIT_RMS_PX:
        return False
    best = cands[0]
    if dist is not None:
        best.distance = dist
    p = link_chance(best, r.fit.sigma)
    if p > 1e-2:
        return False
    n = _n(r)
    r.candidates = cands
    r.letter_seed = best.letter_seed
    r.layout_seed = letters_model.layout_seed(best.letter_seed, n)
    r.confidence = "high" if p <= 1e-3 else "medium"
    r.note = (r.note + f" seed found {how}").strip()
    return True


LINK = 1_000_000          # window for one link while following candidate chains
GOOD_PER_LETTER = 4.0     # chi-square per measured letter for a match to count
WEAK_LINK = 0.01          # a link this likely to be chance ends a chain
ACCEPT_HIGH = 1e-4        # chance that a whole chain is coincidence, for high confidence
ACCEPT_MEDIUM = 1e-3
# Generating a floor alone takes thousands of RNG calls, so the next entry can't follow within a few
# hundred steps (the closest real pair seen is ~900, Bulblax Kingdom's quick purple-farm re-entries).
# A "match" that close is a coincidence that link_chance would wrongly rate as near-certain.
MIN_LINK = 500
BRIDGE_GAP = 6            # longest run of unknown entries the bridge follows
BRIDGE_TOP = 4            # window candidates tried per entry
BRIDGE_BEAM = 40          # partial paths kept per step
BRIDGE_AGREE = 100.0      # paths within this factor of the best must agree on a seed to assign it
BRIDGE_INFORMATIVE = 0.5  # a seed whose own link is likelier than this to be chance is not assigned


@dataclass
class _Hyp:
    letter_seed: int
    layout_seed: int
    score: float
    chance: float              # probability the links so far are all coincidences
    back: "_Hyp | None"
    entry: int
    cands: list = field(default_factory=list)
    dist: int | None = None


def _n(r) -> int:
    return r.num_chars or (len(r.fit.v) if r.fit is not None else 0)


def _good(c: Candidate) -> bool:
    m = int(np.sum(np.isfinite(c.residuals)))
    return m >= 2 and c.score / m <= GOOD_PER_LETTER


def link_chance(c: Candidate, sigma: np.ndarray) -> float:
    """Expected number of random RNG states within `c.distance` steps that would fit the
    measured letters at least as well as `c` does.

    That is the distance times the share of letter space inside the ellipsoid
    chi-square <= score (floored at 0.5 per dimension, so a lucky near-zero score is
    not over-trusted). The fitted bias takes one dimension, the tightest one.
    """
    m = np.isfinite(c.residuals) & np.isfinite(sigma)
    sig = np.sort(sigma[m])[1:]                  # the bias absorbs the tightest constraint
    k = sig.size
    if k < 1 or c.distance is None or c.distance < MIN_LINK:
        return float("inf")
    x = max(c.score, 0.5 * k)
    unit_ball = np.pi ** (k / 2) / math.gamma(k / 2 + 1)
    share = unit_ball * x ** (k / 2) * np.prod(sig / 5.0)
    return float(c.distance * min(1.0, share))


def _chains(results, per_entry: int = 6, keep: int = 12) -> None:
    """Follow candidate chains through entries that neither search settles alone.

    Every entry starts hypotheses from its best global candidates (or its seed,
    when already known). Each hypothesis is extended by a window search of the
    next entry from its layout seed; a clean match there is a link, valued by how
    likely such a match is by chance at that distance (`link_chance`). A chain is
    accepted when all its links together are very unlikely to be coincidence.
    """
    hyps: list[list[_Hyp]] = [[] for _ in results]
    for i, r in enumerate(results):
        n = _n(r)
        if _known(r):
            hyps[i].append(_Hyp(r.letter_seed, r.layout_seed, 0.0, ACCEPT_HIGH, None, i, r.candidates))
        elif r.candidates and r.fit is not None and r.fit.rms_px <= MAX_FIT_RMS_PX:
            for c in r.candidates[:per_entry]:
                if _good(c):
                    hyps[i].append(_Hyp(c.letter_seed, letters_model.layout_seed(c.letter_seed, n),
                                        c.score, 1.0, None, i, [c]))
        hyps[i].sort(key=lambda h: (h.chance, h.score))
        del hyps[i][keep:]
        if i + 1 >= len(results):
            break
        nxt = results[i + 1]
        if nxt.fit is None or np.sum(np.isfinite(nxt.fit.v)) < 2 or nxt.fit.rms_px > MAX_FIT_RMS_PX:
            continue
        n_next = _n(nxt)
        for h in hyps[i]:
            cands = search_near(nxt.fit.v, nxt.fit.sigma, h.layout_seed, LINK, top=3)
            if not cands or not _good(cands[0]):
                continue
            c = cands[0]
            p = link_chance(c, nxt.fit.sigma)
            if p > WEAK_LINK:
                continue
            hyps[i + 1].append(_Hyp(c.letter_seed, letters_model.layout_seed(c.letter_seed, n_next),
                                    h.score + c.score, h.chance * p, h, i + 1, cands, c.distance))

    # accept the most convincing chains first; an entry keeps the first chain that claims it
    ends = [h for hs in hyps for h in hs if h.back is not None]
    ends.sort(key=lambda h: (h.chance, h.score))
    claimed: set[int] = set()
    for h in ends:
        if h.chance > ACCEPT_MEDIUM:
            break
        path = []
        node = h
        while node is not None:
            path.append(node)
            node = node.back
        entries = {p.entry for p in path}
        if entries & claimed:
            continue
        if any(_known(results[p.entry]) and results[p.entry].letter_seed != p.letter_seed for p in path):
            continue          # never overrule a seed the letters alone already settled
        if not _fits_neighbors(results, path):
            continue          # out of order with a settled seed just before or after it
        conf = "high" if h.chance <= ACCEPT_HIGH else "medium"
        for p in path:
            r = results[p.entry]
            if _known(r) and r.letter_seed == p.letter_seed:
                continue
            r.letter_seed, r.layout_seed = p.letter_seed, p.layout_seed
            r.candidates = p.cands
            r.confidence = conf
            r.note = (r.note + f" seed confirmed by a chain of {len(path)} sublevels").strip()
        claimed |= entries


def _backbone(results) -> list[int]:
    """Entries whose full-search seed agrees with the next or previous full-search seed:
    the later one follows the earlier within CONFIRM steps per sublevel between them.
    Two wrong seeds, or a wrong and a right one, agree only by chance (~0.2% per gap)."""
    known = [i for i, r in enumerate(results) if _known(r) and r.layout_seed is not None]
    ok: set[int] = set()
    # each seed is compared with the next few, not only the next one: a single wrong read in
    # between (CurtisDN's Subterranean Complex 2, at 360p) must not hide two that agree
    for n, a in enumerate(known):
        for m, b in enumerate(known[n + 1: n + 1 + BACKBONE_AHEAD]):
            per = CONFIRM if m == 0 else LINK      # past a read in between, the tighter window
            if rng.distance(results[a].layout_seed, results[b].letter_seed, limit=per * (b - a)) is not None:
                ok |= {a, b}
    return sorted(ok)


BACKBONE_AHEAD = 6


def _demote_strays(results, settled: list[int]) -> None:
    """A medium read that is out of RNG order with the backbone seeds on both sides of it is wrong; drop it
    to low so the window searches from its neighbours can look for the right one."""
    s = set(settled)
    for i, r in enumerate(results):
        if i in s or r.confidence != "medium" or r.letter_seed is None:
            continue
        j = max((k for k in settled if k < i), default=None)
        k = min((k for k in settled if k > i), default=None)
        if j is None or k is None:
            continue          # only between two backbone seeds: past the ends, a reset may break the order
        ok = True
        if j is not None and results[j].layout_seed is not None:
            ok = rng.distance(results[j].layout_seed, r.letter_seed, limit=CONFIRM * (i - j)) is not None
        if ok and k is not None and r.layout_seed is not None:
            ok = rng.distance(r.layout_seed, results[k].letter_seed, limit=CONFIRM * (k - i)) is not None
        if not ok:
            r.confidence = "low"
            r.note = (r.note + " (its own read was out of RNG order with its neighbours)").strip()


def _gap(results, i: int, settled: set[int], step: int) -> int | None:
    """Index of the next backbone entry after (step=1) or before (step=-1) entry i."""
    j = i + step
    while 0 <= j < len(results):
        if j in settled:
            return j
        j += step
    return None


def _check_order(results, before, settled: list[int]) -> None:
    """Undo any seed linking filled in that is out of RNG order with the seeds the letters
    settled on their own: it must follow the settled seed before it and lead to the one after
    it, within CONFIRM steps per sublevel between them. (A window search picks the best match
    in its window even when the true seed is elsewhere, e.g. JKira's Snagret Hole 2, which
    landed in Bulblax Kingdom's range, past Snagret Hole 3.)"""
    known = set(settled)
    for i, r in enumerate(results):
        if i in known or r.letter_seed is None or r.letter_seed == before[i][0]:
            continue
        j = max((k for k in settled if k < i), default=None)
        k = min((k for k in settled if k > i), default=None)
        ok = True
        if j is not None and results[j].layout_seed is not None:
            ok = rng.distance(results[j].layout_seed, r.letter_seed, limit=CONFIRM * (i - j)) is not None
        if ok and k is not None:
            ok = rng.distance(r.layout_seed, results[k].letter_seed, limit=CONFIRM * (k - i)) is not None
        if not ok:
            r.letter_seed, r.layout_seed, r.confidence, note, r.candidates = before[i]
            r.note = (note + " (a linked seed was out of order with its neighbors, so it was dropped)").strip()


def _fits_neighbors(results, path) -> bool:
    """A chain must sit in RNG order between the settled seeds next to it in the video.

    The chain's links are each checked, but its ends are not: a chain ending on a wrong seed
    can land after the next sublevel's own settled seed (JKira's Snagret Hole 2 sat in Bulblax
    Kingdom's range, past Snagret Hole 3). Require the settled entry just before the chain to
    lead to its first seed, and its last seed to lead to the settled entry just after."""
    first = min(path, key=lambda p: p.entry)
    last = max(path, key=lambda p: p.entry)
    before = results[first.entry - 1] if first.entry > 0 else None
    after = results[last.entry + 1] if last.entry + 1 < len(results) else None
    if before is not None and _known(before) and before.layout_seed is not None and before.letter_seed != first.letter_seed:
        if rng.distance(before.layout_seed, first.letter_seed, limit=CONFIRM) is None:
            return False
    if after is not None and _known(after) and after.letter_seed != last.letter_seed:
        if rng.distance(last.layout_seed, after.letter_seed, limit=CONFIRM) is None:
            return False
    return True


def _usable(r) -> bool:
    return r.fit is not None and np.sum(np.isfinite(r.fit.v)) >= 2 and not _known(r)


def _forward(results, near: int, settled: set[int]) -> set[int]:
    """Search just after each anchor (a backbone seed, or one found this way from it), no
    further than the next backbone seed. Returns the entries it filled."""
    anchor, filled = None, set()
    for i, r in enumerate(results):
        if i in settled:
            anchor = r
            continue
        if _known(r):
            anchor = None         # a lone read: neither an anchor nor searched again
            continue
        if anchor is not None and _usable(r):
            window = near
            k = _gap(results, i, settled, 1)
            if k is not None:
                d = rng.distance(anchor.layout_seed, results[k].letter_seed, limit=near)
                window = d if d is not None else near
            cands = search_near(r.fit.v, r.fit.sigma, anchor.layout_seed, window)
            if _apply(r, cands, f"near the previous sublevel ({anchor.cave} {anchor.sublevel or '?'})"):
                anchor = r
                filled.add(i)
    return filled


def _backward(results, near: int, settled: set[int]) -> None:
    """Search just before each anchor, no further back than the previous backbone seed."""
    anchor = None
    for i in range(len(results) - 1, -1, -1):
        r = results[i]
        if i in settled:
            anchor = r
            continue
        if _known(r):
            anchor = None
            continue
        if anchor is not None and _usable(r):
            n = _n(r)
            window = near
            k = _gap(results, i, settled, -1)
            if k is not None and results[k].layout_seed is not None:
                d = rng.distance(results[k].layout_seed, anchor.letter_seed, limit=near)
                window = d if d is not None else near
            # r's layout seed (= letter seed + n) lies up to `window` steps before anchor's letter seed
            start = rng.next_seed(anchor.letter_seed, -(window + n))
            cands = search_near(r.fit.v, r.fit.sigma, start, window)
            # distance from r's layout seed to the anchor's letter seed
            dist = window - cands[0].distance + 1 if cands else None
            if _apply(r, cands, f"just before the next sublevel ({anchor.cave} {anchor.sublevel or '?'})", dist):
                anchor = r


def _bridge(results) -> None:
    """Follow every short gap of unknown entries between two known seeds as one path.

    Short names (Submerged Castle 水中の城: 4 letters) give each link a chance of a few percent
    of being coincidence: too weak for `_chains`, which drops any link above WEAK_LINK. Taken
    together, though, four such links in a row are very unlikely to be chance. This tries the
    best few window candidates of each entry from every partial path, keeps paths that lead into
    the known seed after the gap, and scores each by the product of its link chances times the
    number of paths tried (so trying many paths is paid for). An entry is filled only when every
    path nearly as good as the best agrees on it and its own link says something (a 3-letter
    read that fits anywhere is left empty).
    """
    i = 1
    while i < len(results):
        if _known(results[i]) or not _known(results[i - 1]) or results[i - 1].layout_seed is None:
            i += 1
            continue
        a, b = i - 1, i
        while b < len(results) and not _known(results[b]):
            b += 1
        gap, i = list(range(a + 1, b)), b
        if b >= len(results) or len(gap) > BRIDGE_GAP or not any(_usable(results[j]) for j in gap):
            continue
        end = results[b]
        # a path: (chance, layout seed it reached, [(entry, candidate, its link chance)])
        paths = [(1.0, results[a].layout_seed, [])]
        tried = 1
        for j in gap:
            r = results[j]
            if not _usable(r) or r.fit.rms_px > MAX_FIT_RMS_PX:
                continue              # searched past from the seed before it
            n, new, k = _n(r), [], 0
            for p, seed, steps in paths:
                for c in search_near(r.fit.v, r.fit.sigma, seed, LINK, top=BRIDGE_TOP):
                    if not _good(c):
                        continue
                    k += 1
                    q = min(1.0, link_chance(c, r.fit.sigma))
                    new.append((p * q, letters_model.layout_seed(c.letter_seed, n), steps + [(j, c, q)]))
            tried *= max(1, k / max(1, len(paths)))
            new.sort(key=lambda t: t[0])
            paths = new[:BRIDGE_BEAM]
            if not paths:
                break
        done = [t for t in paths if t[2] and end.letter_seed is not None
                and rng.distance(t[1], end.letter_seed, limit=LINK) is not None]
        if not done:
            continue
        best = done[0][0] * tried
        if best > ACCEPT_MEDIUM:
            continue
        close = [t for t in done if t[0] <= done[0][0] * BRIDGE_AGREE]
        conf = "high" if best <= ACCEPT_HIGH else "medium"
        for j, c, q in done[0][2]:
            if q > BRIDGE_INFORMATIVE:
                continue
            if any(all(s[1].letter_seed != c.letter_seed for s in t[2] if s[0] == j) for t in close):
                continue
            r = results[j]
            r.letter_seed, r.layout_seed = c.letter_seed, letters_model.layout_seed(c.letter_seed, _n(r))
            r.candidates, r.confidence = [c], conf
            r.note = (r.note + f" seed found by following the gap from {results[a].cave} "
                      f"{results[a].sublevel or '?'} to {end.cave} {end.sublevel or '?'}").strip()


# --- saving the pre-link state, so chains can be re-tuned without re-reading video ---

def dump(results, path) -> None:
    """Write what linking needs (fits and global candidates, before any linking) as JSON."""
    import json

    def fl(x):
        return [None if not np.isfinite(v) else float(v) for v in x]

    rows = []
    for r in results:
        rows.append({
            "frame": r.settled_frame, "cave": r.cave_id, "sublevel": r.sublevel, "lang": getattr(r, "lang", "en"),
            "num_chars": _n(r), "confidence": r.confidence, "note": r.note,
            "letter_seed": r.letter_seed, "layout_seed": r.layout_seed,
            "fit": None if r.fit is None else {"v": fl(r.fit.v), "sigma": fl(r.fit.sigma), "rms_px": r.fit.rms_px},
            "candidates": [{"letter_seed": c.letter_seed, "score": c.score, "bias": c.bias,
                            "residuals": fl(c.residuals)} for c in r.candidates[:8]],
        })
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)


class _Fit:
    def __init__(self, d):
        self.v = np.array([np.nan if x is None else x for x in d["v"]])
        self.sigma = np.array([np.nan if x is None else x for x in d["sigma"]])
        self.rms_px = d["rms_px"]


class Saved:
    """A result rebuilt from dump(), enough for link()."""

    def __init__(self, d):
        self.settled_frame, self.cave_id, self.sublevel = d["frame"], d["cave"], d["sublevel"]
        self.cave, self.lang, self.num_chars = d["cave"], d["lang"], d["num_chars"]
        self.confidence, self.note = d["confidence"], d["note"]
        self.letter_seed, self.layout_seed = d["letter_seed"], d["layout_seed"]
        self.fit = _Fit(d["fit"]) if d["fit"] else None
        self.candidates = [Candidate(c["letter_seed"], c["score"], c["bias"],
                                     np.array([np.nan if x is None else x for x in c["residuals"]]))
                           for c in d["candidates"]]


def load(path) -> list:
    import json
    with open(path, encoding="utf-8") as fh:
        return [Saved(d) for d in json.load(fh)]


def relink_dir(out_dir) -> list:
    """Re-run link() from out_dir/fits.json and update the seed fields of out_dir/seeds.json."""
    import json
    from pathlib import Path

    out_dir = Path(out_dir)
    results = load(out_dir / "fits.json")
    link(results)
    by_frame = {r.settled_frame: r for r in results}
    data = json.loads((out_dir / "seeds.json").read_text(encoding="utf-8"))
    for e in data["entries"]:
        r = by_frame.get(e["frame"])
        if r is None:
            continue
        e["letter_seed"] = f"0x{r.letter_seed:08X}" if r.letter_seed is not None else None
        e["layout_seed"] = f"0x{r.layout_seed:08X}" if r.layout_seed is not None else None
        e["confidence"], e["note"], e["chain_dist"] = r.confidence, r.note, r.chain_dist
    (out_dir / "seeds.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return results
