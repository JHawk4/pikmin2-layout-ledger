# judge2 log

Goal: a Pay Off Debt (PoD) layout judge whose within-sublevel predictions match runners'
actual net time (`cost = seconds between entry screens - pokos / 2`), with beta ~ 1 overall
and per sublevel. Metrics come from `evalkit.py`, the same sublevel + run fixed-effects
residualization as `p2seeds.site.calibration()`:

- `R2` = 1 - |yr - xr|^2 / |yr|^2: the prediction at face value (slope 1), the objective.
- `corr2`: R2 after the best global rescale. `beta` ± SE: slope of yr on xr.
- `chi2(beta_s=1)`: sum over sublevels of (beta_s - 1)^2 * Sxx_s / sigma^2, against the
  number of sublevels with variation (k). About k means per-sublevel betas are consistent with 1.
- high-var: plays on sublevels whose 5th-95th spread of random-layout old pod scores is >= 20 s.

## Setup

- Snapshot `data/plays.json` (snapshot.py): 997 high-confidence plays from 29 PoD runs; 931
  after dropping fixed layouts (`judge_fixed`, no variation). 0 plays without pokos.
- Split `data/split.json` (split.py): by **runner** (rng seed 20261115). Several runners have
  3-6 runs; their routing habits are what the judge gets tuned to, so a runner's runs stay on
  one side. OOS runners: Sergeant_Guy, ShadowLugia, iid01, randomRyze, tcbtrio, theurbandear
  (290 plays, 31%); in-sample 641 plays (639 after dropping lone plays of a sublevel).
- judge2 crate: `old_judge.rs` is CaveGen3's jhawk_judge.rs copied verbatim except for
  visibility and returning the pod parts; it reproduces judge.json's score on all 997 plays
  (0 mismatches). `pod2.rs` recomputes the pod score for any take/skip choice of the counted
  treasures and adds terms; with nothing skipped it equals the old score exactly.

## What the old PoD judge does

score = walking (Prim MST from the ship over the counted treasures, straight-line except
from the ship, / Olimar speed 199 cm/s) + hole distance / speed / (1 + treasures)
+ carry (sum of per-treasure pikmin-seconds: 3 s load per carrier + dig + carry distance
at a speed from carry strength / min(60, carriers)) + hazards (difficulty.sec / 2 for each
teki within 120 cm of a treasure's carry path) + gates on carry paths or the hole route
(3 + life * 2 / (13 * 60), min 6 s) - optional-treasure saves (for 6 "optional" treasures)
+ (expected pokos - treasure pokos - bug pokos) / 2 + GK special cases + 10 s per treasure.
15 low-value treasures are ignored; all others are assumed collected.

## Ideas

Numbers: in-sample (IN) n=639, out-of-sample (OOS) n=290. R2 / corr2 / beta ± SE / chi2, then the high-variance subset.

### 0. Baselines
| model | IN R2 | IN beta | IN chi2/k | OOS R2 | OOS beta | OOS chi2/k |
|---|---|---|---|---|---|---|
| old judge | 0.353 | 0.76±0.04 | 79/40 | 0.357 | 0.82±0.07 | 60/40 |
| old × 0.76 (fitted global scale) | 0.392 | 1.00 | 42/40 | 0.372 | 1.08±0.09 | 55/40 |

### B. No bug-poko credit — ACCEPTED
Hypothesis: the old judge subtracts pokos of enemies in the way ("bug pokos") as if the
runner carried their corpses, but PoD runners don't, and the outcome only counts pokos from
treasure panels. Removing the credit should remove noise.
IN 0.353 -> 0.404 (corr2 0.443); OOS 0.357 -> 0.382 (corr2 0.401). A free weight on the bug
term fits **negative** (-0.6: more killable enemies in the way = slower), i.e. it is an
enemy-density proxy, not a reward; kept at 0 on priors.

### C. Take-or-skip decisions + SH6 lens behind water — ACCEPTED
Hypothesis: the old judge assumes every counted treasure is collected. A runner skips a
treasure when collecting it costs more than its pokos are worth. pod2 recomputes the score for
every take/skip subset of the counted treasures (poko term = missing pokos / 2, hole walk
undivided when nothing is carried, carry paths/hazards/gates only for taken treasures) and
predicts the minimum. SH6: the lens (bey_goma, 120 pokos, carried by a Dwarf Bulborb) was
skipped in all 4 in-sample plays where its carry route crosses water after leaving its start
pool (and taken in 10/12 otherwise; the 2 dry skips are IceCube's), while the treasure that
starts in a pool but has a dry route was taken. So: lens route crosses water -> skip.
- decide alone: IN 0.361, OOS 0.350 (no gain; only changes a few far-lens layouts).
- decide + lens water: IN 0.417, OOS 0.383.

### D. No optional-treasure credit — ACCEPTED
Hypothesis: the six "optional" treasures get a time-save credit, but runners almost never
collect them (in-sample: locket 0/17, CoS-1 leaf 1/17, SCx-1 gum tape 2/17, FC-6 chess 2-4/17,
SH-6 queen 0/16), so the credit is noise. A free weight fits ~0.
IN 0.378, OOS 0.391 (beta 0.80 -> 0.90).

### B+C+D combined, and refitted part weights
| model | IN R2 | IN beta | IN chi2/k | IN high-var R2 | OOS R2 | OOS beta | OOS chi2/k | OOS high-var R2 |
|---|---|---|---|---|---|---|---|---|
| B+C+D | 0.489 | 0.86±0.04 | 66/40 | 0.507 | 0.448 | 0.90±0.06 | 57/40 | 0.482 |
| B+C+D × fitted scale | 0.503 | 1.00 | 50/40 | 0.520 | 0.453 | 1.04±0.07 | 55/40 | 0.481 |
| B+C+D + 5 fitted weights | 0.525 | 0.98±0.04 | 45/40 | 0.549 | 0.466 | 1.02±0.07 | 47/40 | 0.501 |

Fitted weights (in-sample): walking 1.24, carry 0.77, hazard 0.62, gate 0.59, GK adj 0.56.

### E. Rejected in-sample (leave-one-runner-out CV on the in-sample plays, decisions fixed)
CV R2 of the 5-weight base model: 0.509 (ridge toward the prior, lam 0-100: 0.509-0.511).
| idea | hypothesis | CV R2 | verdict |
|---|---|---|---|
| per-teki hazard weights (ridge) | difficulty table off per enemy | 0.39-0.48 | overfits, rejected |
| hazard classes: electric wires and bomb rocks apart | wires must be broken (in-sample weight 2.3x), bomb rocks don't attack (weight <0) | 0.507-0.514 | no gain, rejected. Flag on priors: bomb rocks probably should not count as hazards |
| walking split: MST vs hole share | captain's hole walk overlaps carrying | 0.503 | rejected (hole share weight 1.0, MST 1.5) |
| gate split: hole route vs treasure routes | | 0.506 | rejected |
| bug pokos as an enemy-density term | | 0.515 | +0.006, not worth a term that contradicts its meaning |
| carrier-teki fight time | treasure-carrying enemies cost more | worse | rejected (weight -0.17) |
| water on the hole route | non-blue squad can't follow | 0.506 | rejected (weight ~0) |
| hazard of teki on the hole route only | old judge only looks at carry paths | 0.506 | rejected (weight 0.13) |
| per-sublevel scale, empirical-Bayes shrunk to 1 | | tau^2 = 0 | no detectable per-sublevel heterogeneity in-sample (chi2 44/40), nothing to scale; also tau^2 = 0 for the old judge after its global rescale |
| seconds per treasure (cut) 0/20/30 instead of 10 | | in-sample R2 0.517/0.522/0.462 vs 0.525 | keep 10 s (user's cutscene estimate) |

### F. Soft take/skip decision (temperature 5 s) — ACCEPTED (final)
Hypothesis: the hard minimum flips on 1-2 s differences the judge can't resolve. The
single-treasure "gain from skipping" separates the data cleanly: lens behind water 59-95 s
(all skipped); SCx-1 tel_dial 2.7 and 4.5 s (both of its 2 skips); WFG-1 fire helmet 1-2 s
(taken 16/16); everything else < 0. So near-ties should be averages, not flips: each choice
is weighted by exp(-score / 5 s).
IN 0.526 (beta 0.98), OOS **0.469** (beta 1.02±0.07, chi2 47/40), OOS high-var 0.504.
Cluster-bootstrap (by run, in-sample) 95% ranges of the weights: walking 0.98-1.50,
carry 0.60-0.94, hazard 0.40-0.81, gate 0.30-0.84, GK adj 0.13-1.03.
Refit on all 929 plays: walking 1.20, carry 0.76, hazard 0.61, gate 0.70, adj 0.71 (R2 0.519
vs 0.517 shipped) — the shipped in-sample weights are kept.

## Final judge2 (crate/src/pod2.rs, MODEL)
For every take/skip choice of the counted treasures (all subsets up to 4, else each one alone):
score = 1.22 walking + 0.78 carry + 0.60 hazard + 0.58 gate + 0.54 GK-adj + 10 s per taken
treasure + (missing pokos)/2 [+100 s if SH-6's lens is taken across water]; no bug-poko or
optional-treasure credit. judge2 = average of the choices' scores weighted by exp(-score/5).

| | old IN | judge2 IN | old OOS | judge2 OOS | old all | judge2 all |
|---|---|---|---|---|---|---|
| R2 (slope 1) | 0.353 | 0.526 | 0.357 | 0.469 | 0.374 | 0.517 |
| corr2 | 0.392 | 0.526 | 0.374 | 0.469 | 0.401 | 0.517 |
| beta | 0.76±0.04 | 0.98±0.04 | 0.82±0.07 | 1.02±0.07 | 0.79±0.03 | 0.99±0.03 |
| chi2 per-sublevel beta=1 | 79/40 | 44/40 | 60/40 | 47/40 | 93/40 | 67/40 |
| high-var R2 | 0.360 | 0.550 | 0.375 | 0.504 | 0.384 | 0.543 |
| high-var beta | 0.76 | 0.98 | 0.84 | 1.07 | 0.79 | 1.01 |

Per-cave beta (all plays) old -> judge2: BK 0.70->1.03, CoS 0.70->1.26, EC 0.86->1.31,
FC 0.70->0.95, GK 0.72->0.87, HoB 0.70->0.85, SCx 0.86->1.03, SH 0.89->1.01, WFG 1.12->1.10.
OOS-only cave betas are noisier: FC 0.61±0.17 and HoB 0.52±0.19 are low there (not tuned on).
Per-sublevel table: `python judge2/final_eval.py`.

## Outliers looked at (in-sample)
- SH-6 is 18% of the old judge's residual sum of squares. Lens across water: chemical 0x2B1980E4
  (+37 s actual vs -12 old prediction), Kap 0x2A42B8B9, IceCube 0x402722E9: all skipped; layout
  image shows the Dwarf Bulborb's carry route through a pool. Fixed by the water rule.
- SH-6 dry-route skips by IceCube (0x7D42A01E: lens 590 cm away, off the hole route; 0x28B493CF:
  lens 2411 cm away). IceCube took the lens only when it was right on the hole route (off 0 cm);
  other runners took it up to 470 cm off. Runner habit (older WR runs), not modelled.
- SH-6 JackDraz 0x29698334: lens Bulborb starts *in* a pool with a dry route; taken, but ~15 s
  slower than predicted (luring it out?). One play; not modelled.
- GK-3 IceCube 0x5A6727F3 (wr25): 110 s vs 59 s for the best layout; dense Anode Beetles and
  electric wires along the routes. Execution plus wires (the per-class fit says wires cost
  ~2x the table) — not robust under CV.
- WFG-1 fire helmet: judge thinks skipping saves 1-2 s; always taken. SCx-1 tel dial: judge
  thinks skipping saves 3-5 s in 2 layouts; skipped exactly there (Kap, JackDraz).
- Optional treasures (locket, chess pieces, gum tape, leaf, queen) are essentially never taken;
  the old judge's credit for them was pure noise.

## Side finding
Old-judge ranks of real high-confidence plays average 44.3 (n=1091, 57% below 50), not 50:
real layouts are better than CaveGen's random-seed reference. SH-6: lens behind water in 5/23
real plays vs ~50% of random seeds (600 random and 400 evenly spaced seeds agree). Either the
game's seeds are not uniform, or the reference is off; worth a look before reading ranks literally.

## How to run
Build: `cargo build --release --manifest-path judge2/crate/Cargo.toml --target-dir data/build/judge2`
- `data/build/judge2/release/judge2.exe SH-6 0x2B1980E4 [more seeds]` prints old and judge2 scores.
- JSON lines on stdin: `{"sub":"SH-6","seed":"0x2B1980E4"}` -> old, pod2, both parts and the
  take/skip choices with probabilities; add `"dump":true` for the layout geometry;
  `{"sub":"SH-6","reference":1000}` -> both judges on 1000 evenly spaced seeds.
Analysis (Python venv): snapshot.py (once), split.py (once), run_judge2.py (layout features ->
data/judged.json, ignored by git, 6.6 MB), ideas.py [--oos NAME], final_eval.py, show.py SUB.
