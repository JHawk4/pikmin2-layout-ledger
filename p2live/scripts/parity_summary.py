"""Summarize p2live parity runs: python p2live/scripts/parity_summary.py OUT_DIR

Compares with seeds.json, and, where OUT_DIR/python_per_entry.jsonl exists (python_per_entry.py),
with Python's own per-entry result. seeds.json holds the run's final seeds, after chain.py's
cross-entry pass and the sublevel-sequence fill-in, which p2live entries does not do.
"""
import json, sys, collections
from pathlib import Path

out = Path(sys.argv[1])
rows = [json.loads(l) for p in sorted(out.glob("*.jsonl")) if p.name != "python_per_entry.jsonl"
        for l in p.read_text().splitlines() if l.strip()]
skipped = [r for r in rows if r["note"] == "no frames decoded"]
rows = [r for r in rows if r["note"] != "no frames decoded"]
by = collections.Counter()
for r in rows:
    by[(r["expected_confidence"], "same" if r["same"] else ("no seed" if r["letter_seed"] is None else "differs"), r["confidence"])] += 1
print(f"{len(rows)} entries" + (f" ({len(skipped)} more skipped: video not on disk)" if skipped else ""))
print("\nagainst seeds.json (final seeds, after the chain pass)")
print(f"{'python conf':<12} {'rust seed':<9} {'rust conf':<9} count")
for (ec, s, rc), n in sorted(by.items()):
    print(f"{ec:<12} {s:<9} {rc:<9} {n}")
hw = [r for r in rows if r["confidence"] == "high" and not r["same"] and r["letter_seed"]]
print(f"\nrust high but differs from seeds.json: {len(hw)}")
for r in hw:
    print(f"  {r['run']} {r['frame']} {r['cave']}-{r['sublevel']} rust {r['letter_seed']} python {r['expected']} ({r['expected_confidence']}) {r['note']}")

per_path = out / "python_per_entry.jsonl"
if per_path.exists():
    per = {(p["run"], p["frame"]): p for p in map(json.loads, per_path.read_text().splitlines())}
    seed_eq = sub_eq = conf_eq = n = 0
    bad = []
    for r in rows:
        p = per.get((r["run"], r["frame"]))
        if p is None:   # equal to seeds.json, which is at least as strong as Python's per-entry
            continue
        n += 1
        s = p["py_seed"] == r["letter_seed"]
        seed_eq += s
        sub_eq += p["py_sublevel"] == r["sublevel"]
        conf_eq += p["py_confidence"] == r["confidence"]
        if not s or p["py_sublevel"] != r["sublevel"]:
            bad.append((r, p))
    print(f"\nagainst Python's per-entry result ({n} entries that differ from seeds.json):")
    print(f"  seed equal {seed_eq}/{n}, sublevel equal {sub_eq}/{n}, confidence equal {conf_eq}/{n}")
    for r, p in bad:
        print(f"  {r['run']} {r['frame']} {r['cave']}: rust {r['letter_seed']} {r['confidence']} sub {r['sublevel']} {r.get('digit_votes')}"
              f" | py {p['py_seed']} {p['py_confidence']} sub {p['py_sublevel']} {p['py_votes']} | {p['py_note'][:60]}")

cave_diff = [r for r in rows if r["cave"] and r["cave"] != r["expected_cave"]]
sub_diff = [r for r in rows if r["cave"] and r["sublevel"] != r["expected_sublevel"]]
print(f"\ncave differs from seeds.json: {len(cave_diff)}, sublevel differs: {len(sub_diff)}")
t = sorted(r["t_analyze"] for r in rows)
if t:
    print(f"analysis time per entry (4 jobs sharing 4 cores): median {t[len(t)//2]:.1f}s, p90 {t[int(len(t)*.9)]:.1f}s, max {t[-1]:.1f}s")
