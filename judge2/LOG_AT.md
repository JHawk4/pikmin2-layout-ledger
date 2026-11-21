# at2: the All Treasures judge (2026-11-21)

All Treasures collects every treasure, so the judge has no take/skip choices and no pokos.
What a layout costs is walking, carrying, enemies near the carry paths, gates, and two
quirks of the spawning that cost a lot of time: a treasure missing from the layout, and
fewer purple candypops (purple flowers) than usual on sublevels where runners pick purples.
CaveGen's `at` judge already has all of these. at2 (`crate/src/at2.rs`) re-weights its parts.

## Data

`at_snapshot.py` over the 5 Japanese GameCube runs read so far (iid01, kobachi, JackDraz,
keisen, CurtisDN_): every high-confidence floor with the next floor of the same cave read,
timed from entry screen to entry screen. Only each cave's last visit counts (the Bulblax
Kingdom purple farm goes down several floors, out, and in again). That gives 184 plays; 170 on
56 sublevels seen at least twice.

Treasure weights: Japanese runs use `config_jpn.txt` (`data/treasure_teki_config_jpn.csv`,
request `"region": "jpn"`). 28 treasures differ from the US table. With it, judge2's
port of CaveGen's at score equals Java CaveGen's (`-region jpn`) on all 186 judged floors of
kobachi and JackDraz. Without it, 24 of them change.

## Fit (`at_fit.py`)

took = runner + sublevel + Σ w·part, with fixed effects per sublevel and runner. All numbers
are within sublevel and runner.

| Weights | mse (s²) | R² at slope 1 | fitted slope | corr |
|---|---|---|---|---|
| none | 113.9* | 0 | | |
| CaveGen at (all 1) | 62.6 | 0.257 | 0.78 | 0.53 |
| **at2 = pod2's weights** (walk 1.22, carry 0.78, hazard 0.60, gate 0.58) | **60.1** | **0.288** | **0.96** | 0.54 |
| free fit, no shrinkage | | 0.295 | 1.00 | |

(* before the purple-farm fix; the other rows are after it. All rows leave out the missing-purple
term; its cost is below.)

The free fit (walking 1.84, carry 0.41, hazard 0.55, gate 0.48) leans the same way as pod2:
walking counts more, and carrying, enemies and gates count less. But leaving one run out, it predicts
no better than CaveGen's weights (mse 63 vs 63 at λ ≥ 50; 69 unshrunk). With 5 runs, any
reasonable weights explain about the same. pod2's weights, fitted on 25 Pay Off Debt runs
and never on these, come out calibrated here (slope 0.96 vs 0.78). That is an
out-of-sample check on them, so at2 uses them. Walking to purple candypops counts as walking.

## Missing treasures and purple flowers

How often random layouts (400 seeds per sublevel, Japanese weights) miss something:

| Sublevel | missing a treasure | missing purple candypop(s) |
|---|---|---|
| SC 4 | 3.2% | |
| SCx 7 | 1.0% | |
| GK 3 | 0.5% | |
| SR 5 | | 68.5% |
| FC 4 | | 31.2% |
| BK 4 | | 27.8% |
| BK 6 | | 4.8% |
| GK 5 | | 0.2% |

(CaveGen counts missing purples only where runners pick them: every sublevel with purple
candypops except the "purple20" ones, EC 2, FC 1, HoB 2, CoS 2, GK 2 and SR 2.)

In the runs: no play had a missing treasure, so that penalty keeps CaveGen's 300 s. Two plays had a
missing purple, both on SR 5 (kobachi 156 s and CurtisDN_ 160 s, against JackDraz and keisen with 148 s each).
With the other weights fixed, the fitted cost is **5.5 ± 9.8 s per missing purple**. CaveGen's 60 s is
5 SE off, and it wrecks the calibration: over the site's 173 plays the slope drops from 0.92 to 0.57
(R² 0.28 to 0.09), all from those two SR 5 plays. The slope by penalty, on the 170 snapshot plays:
0 s 0.96, 10 s 0.94, 20 s 0.89, 30 s 0.81, 60 s 0.57. **at2 uses 10 s.** Runners may rely on the
purples more on some sublevels (BK 4, FC 4?) than on SR 5. A per-sublevel penalty needs plays there.

Odd: BK 4 and FC 4 miss purples about 30% of the time, but none of
the 6 plays here did. That may be chance (P ≈ 0.12), or runners reset such layouts.

## How to run

    cargo build --release --manifest-path judge2/crate/Cargo.toml --target-dir data/build/judge2
    python judge2/at_snapshot.py <run dirs...>      # -> judge2/data/at_plays.json
    python judge2/at_fit.py

`p2seeds.judge2.add_to_run` fills `judge2_*` for runs whose judge.json has `"kind": "at"`,
plus `judge2_missing`, with the Japanese weights when the cave names are Japanese.
