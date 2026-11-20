"""Markdown tables for docs/challenge-mode-seeds.md §8 from the cross-check and WR result files.

    python docs/challenge_dive/report_tables.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "p2seeds", "src"))

from p2seeds import rng  # noqa: E402

D = os.path.join(ROOT, "data", "challenge")
COL = ("red", "yellow", "blue", "white", "purple")


def counts_str(c):
    return ", ".join(f"{k} {n}" for n, k in zip(c, COL) if n) if c else ""


def crosscheck():
    rows = ["| run | stage | Pikmin | result | margin | rank of truth |", "|---|---|---|---|---|---|"]
    n_ok = n = 0
    for p in sorted(glob.glob(os.path.join(D, "crosscheck", "*.json"))):
        run = os.path.basename(p).split("_")[0] + " " + os.path.basename(p).split("_")[1]
        for r in json.load(open(p)):
            n += 1
            n_ok += bool(r["correct"])
            m = r.get("margin")
            rows.append(f"| {run} | CH{r['ch']} | {counts_str(r.get('counts'))} | "
                        f"{'**correct**' if r['correct'] else 'wrong'} | {m * 100:.1f}% | "
                        f"{r['truth_rank'] if r['truth_rank'] is not None else 'not in top 200'} |"
                        if m is not None else f"| {run} | CH{r.get('ch')} | | failed: {r.get('note')} | | |")
    return f"{n_ok} of {n} correct.\n\n" + "\n".join(rows)


def wrs():
    wl = {w["ch"]: w for w in json.load(open(os.path.join(D, "wr", "wr_list.json"), encoding="utf8"))}
    rows = ["| stage | record | Pikmin | floor-1 seed | margin | shift margin | status |", "|---|---|---|---|---|---|---|"]
    for ch in range(1, 31):
        w = wl.get(ch)
        if not w:
            continue
        p = os.path.join(D, "wr", "dives", f"wr_{ch:02d}.json")
        if not os.path.exists(p):
            rows.append(f"| CH{ch} | {w['score']:,} {w['user']} | | | | | not run |")
            continue
        r = json.load(open(p))
        if not r.get("ok"):
            rows.append(f"| CH{ch} | {w['score']:,} {w['user']} | | | | | {r.get('note')} |")
            continue
        c = r["candidates"][0]
        m, sm = r.get("margin") or 0, r.get("shift_margin") or 0
        ok = m >= 0.10 and sm >= 0.005
        rows.append(f"| CH{ch} | {w['score']:,} {w['user']} | {counts_str(r.get('counts'))} | "
                    f"`{c['layout_seed'] & 0x7FFFFFFF:08X}` | {m * 100:.1f}% | {sm * 100:+.1f}% | "
                    f"{'published' if ok else 'uncertain'} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(crosscheck())
    print()
    print(wrs())
