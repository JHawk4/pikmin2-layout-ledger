"""Summarize p2live parity runs: python p2live/scripts/parity_summary.py OUT_DIR"""
import json, sys, collections
from pathlib import Path

rows = [json.loads(l) for p in sorted(Path(sys.argv[1]).glob("*.jsonl")) for l in p.read_text().splitlines() if l.strip()]
by = collections.Counter()
for r in rows:
    exp_known = r["expected"] is not None
    by[(r["expected_confidence"], "same" if r["same"] else ("no seed" if r["letter_seed"] is None else "differs"), r["confidence"])] += 1
print(f"{len(rows)} entries")
print(f"{'python conf':<12} {'rust seed':<9} {'rust conf':<9} count")
for (ec, s, rc), n in sorted(by.items()):
    print(f"{ec:<12} {s:<9} {rc:<9} {n}")
hw = [r for r in rows if r["confidence"] == "high" and not r["same"] and r["letter_seed"]]
print(f"\nrust high but differs: {len(hw)}")
for r in hw:
    print(f"  {r['run']} {r['frame']} {r['cave']}-{r['sublevel']} rust {r['letter_seed']} python {r['expected']} ({r['expected_confidence']}) {r['note']}")
miss = [r for r in rows if r["expected_confidence"] == "high" and not r["same"]]
print(f"\npython high, rust not equal: {len(miss)}")
for r in miss[:80]:
    print(f"  {r['run']} {r['frame']} {r['expected_cave']}-{r['expected_sublevel']} rust {r['cave']}-{r['sublevel']} {r['letter_seed']} {r['confidence']} | {r['note']} | py: {r['expected_note']}")
cave_diff = [r for r in rows if r["cave"] and r["cave"] != r["expected_cave"]]
sub_diff = [r for r in rows if r["cave"] and r["sublevel"] != r["expected_sublevel"]]
print(f"\ncave differs: {len(cave_diff)}, sublevel differs: {len(sub_diff)}")
t = sorted(r["t_analyze"] for r in rows)
if t:
    print(f"analysis time per entry (4 jobs sharing 4 cores): median {t[len(t)//2]:.1f}s, p90 {t[int(len(t)*.9)]:.1f}s, max {t[-1]:.1f}s")
