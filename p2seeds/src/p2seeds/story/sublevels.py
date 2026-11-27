"""Assign sublevel numbers to a run's sequence of entries.

The entry screen prints "Sublevel N"; when the digit can be read (digits.py)
it wins. Otherwise the number comes from the sequence: a new cave (or a long
gap, e.g. leaving and re-entering) starts at 1, and each further entry of the
same cave adds 1, never past the cave's last sublevel.
"""

from __future__ import annotations

from .. import caves

REENTRY_GAP_FRAMES = 30 * 60 * 6   # > 6 minutes between entries of one cave: assume a fresh descent


def assign(results) -> None:
    """Set `sublevel` and `sublevel_source` on each EventResult (in time order) that has a cave."""
    prev = None
    for r in results:
        if not r.cave_id:
            continue
        seq = 1
        if prev is not None and prev.cave_id == r.cave_id and prev.sublevel:
            gap = (r.settled_frame or 0) - (prev.settled_frame or 0)
            if gap < REENTRY_GAP_FRAMES:
                seq = min(prev.sublevel + 1, caves.get(r.cave_id).sublevels)
        read = getattr(r, "digit_value", None)
        if read is not None:
            r.sublevel = read
            r.sublevel_source = "digit" if read == seq else f"digit (sequence said {seq})"
        else:
            r.sublevel = seq
            r.sublevel_source = "sequence"
        prev = r
