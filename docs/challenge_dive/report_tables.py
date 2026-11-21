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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_site_seeds import assess, preceding_roll_check  # noqa: E402

D = os.path.join(ROOT, "data", "challenge")
COL = ("red", "yellow", "blue", "white", "purple")


def counts_str(c):
    return ", ".join(f"{k} {n}" for n, k in zip(c, COL) if n) if c else ""


def crosscheck():
    """Cross-check table. A `<video>_f0.json` (current pipeline: best coarse loss over dive-start
    offsets, compiled exact loss) supersedes the base file's row for the same visit."""
    rows = ["| run | stage | Pikmin | result | margin | earlier pipeline |", "|---|---|---|---|---|---|"]
    n_ok = n = hi = hi_ok = 0
    lo_ok = []
    for p in sorted(glob.glob(os.path.join(D, "crosscheck", "*.json"))):
        if p.endswith("_f0.json"):
            continue
        run = os.path.basename(p).split("_")[0] + " " + os.path.basename(p).split("_")[1]
        newer = {}
        if os.path.exists(p[:-5] + "_f0.json"):
            newer = {tuple(r["visit"]): r for r in json.load(open(p[:-5] + "_f0.json"))}
        for r0 in json.load(open(p)):
            r = newer.get(tuple(r0["visit"]), r0)
            was = ""
            if r is not r0 and r0.get("margin") is not None:
                was = f"{'correct' if r0['correct'] else 'wrong'}, {r0['margin'] * 100:.1f}%"
            elif r is r0:
                was = "(not rerun)"
            m = r.get("margin")
            if m is None:
                rows.append(f"| {run} | CH{r.get('ch')} | | failed: {r.get('note')} | | |")
                continue
            if r.get("truth_valid") is False:
                rows.append(f"| {run} | CH{r['ch']} | {counts_str(r.get('counts'))} | no truth (another menu visit "
                            f"since the last results screen) | {m * 100:.1f}% | |")
                continue
            n += 1
            n_ok += bool(r["correct"])
            if m >= 0.10:
                hi += 1
                hi_ok += bool(r["correct"])
            rows.append(f"| {run} | CH{r['ch']} | {counts_str(r.get('counts'))} | "
                        f"{'**correct**' if r['correct'] else 'wrong'} | {m * 100:.1f}% | {was} |")
    head = f"{n_ok} of {n} correct; {hi_ok} of {hi} with a margin of 10% or more."
    return head + "\n\n" + "\n".join(rows)


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
        s, _, m, sm = assess(r)
        m, sm = m or 0, sm or 0
        ok = m >= 0.10 and sm >= 0.005 and sum(min(k, 50) for k in r.get("counts", [])) >= 8
        ver = preceding_roll_check(r, s)
        rows.append(f"| CH{ch} | {w['score']:,} {w['user']} | {counts_str(r.get('counts'))} | "
                    f"`{c['layout_seed'] & 0x7FFFFFFF:08X}` | {m * 100:.1f}% | {sm * 100:+.1f}% | "
                    f"{'published (confirmed by the previous roll)' if ver else 'withheld (margin rule only)' if ok else 'uncertain'} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(crosscheck())
    print()
    print(wrs())
