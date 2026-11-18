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

# Round 2 (2026-11-17): net timesave with creature pokos

The outcome now counts every poko collected on the sublevel, creatures included
(`cost = seconds between entry screens - (treasure pokos + creature pokos) / 2`, pokos from
`treasures.reliable_pokos()`, as `p2seeds.site.calibration()`). Everything above was fit on
treasure pokos only (snapshot `data/plays.json`; to rerun it set `evalkit.PLAYS = "plays.json"`).

## Setup
- Snapshot `data/plays_net.json` (snapshot_net.py, taken 2026-11-17 22:27 from the main
  checkout's data/output, which other sessions keep re-processing): 1195 high-confidence plays
  from 29 runs; 21 without reliable pokos (more than 30 creature pokos clipped), 80 fixed layouts.
  Per play: run, runner, sub, layout_seed, judge (old), judge2 (shipped), took, treasure_pokos,
  bug_pokos, bug_clipped, pokos (reliable total), creature_cap, cost.
- Same runner split (`data/split.json`, unchanged): in-sample 676 plays, OOS 415.
- Measurement validity, decided before looking at any residual and applied to every judge
  (`evalkit.VALID_ONLY`): drop a play whose treasure pokos exceed the sum of every treasure
  CaveGen placed on its layout (impossible: misread value, panel of another sublevel, wrong seed).
  Removes 0 in-sample and 3 OOS plays (listed under measurement errors). Raw numbers are given too.
- Dump additions (features.rs): per teki its distance to each treasure's route and to the hole
  route (`near_tre`, `near_hole`, `off_tre`); per variant `tree_walk` (pod2.rs). judge2's score is unchanged.
- Fast vectorized model `vmodel.py` (reproduces the Rust score to 1e-13) and `ideas_net.py`
  (in-sample fit + leave-one-runner-out CV; `--oos` once per idea).

## Creature pokos: what they are
- Small: mean 3.5 pokos per play in-sample (1.75 s); runners get ~18-20% of `creature_cap`.
  Within sublevel (sublevel + run fixed effects) their SD is 2.7 pokos = 1.4 s, **2.2% of the
  within-sublevel variance of net cost**. A perfect creature model could add at most ~0.02 R2.
- `creature_cap` is ~constant within a sublevel (creature counts are fixed on most sublevels):
  within-sublevel corr2 with measured creature pokos 0.00. It is a valid upper bound (measured
  <= cap in 100% of plays), but that is enforced by the allocation's clipping, not independent.
- Measurement smearing: creature pokos between two panels are shared among the sublevels in
  between by time; 46% of plays have a fractional (smeared) value, and within sublevel creature
  pokos correlate +0.22 with seconds taken (0.06 pokos per second). Sublevels without their own
  panel get a share of a neighbour's creatures.

## Creature-poko model (creatures.py, cre_eval.py, cre_lin.py)
Hypothesis: a runner kills the creatures on the route (hole route and the taken treasures'
carry routes) and those carrying a treasure they take; corpses ride home with the carry.
E[creature pokos] = sum over carcass teki of pokos * sigmoid(a + b * carries_taken - d / s),
d = straight-line distance to the nearest travelled route. Fit on in-sample creature pokos
(judge2's likeliest take/skip choice): a = -1.25, b = 1.78, s = 157 cm (net_creature_theta.json).

| predictor of measured creature pokos | IN level R2 | OOS level R2 | IN within-sub corr2 | OOS within-sub corr2 |
|---|---|---|---|---|
| model (3 params) | 0.267 | 0.298 | 0.008 | 0.021 |
| in-sample sublevel means | 0.601 | 0.517 | - | - |
| old judge's bug term (2 x bug) | -0.58 | -0.37 | 0.050 | 0.036 |
| creature_cap | -18.6 | -15.1 | 0.000 | - |

Leave-one-runner-out CV of the within-sublevel fit: logistic model corr2 0.004 (R2 -0.03);
distance-band regression (carrier, <100, 100-200, 200-400, 400-800, >800 cm) in-sample R2 0.017,
CV -0.009 (the route the runner actually took instead of judge2's: the same). **Within a
sublevel, creature pokos are not predictable from the layout**: what varies is the runner and
the measurement. The model only gets the level (which sublevels give creature pokos), and
sublevel means do that better.

## Ideas (net outcome)
IN n=676, OOS n=412 (valid plays; raw OOS n=415 below). R2 / beta / chi2 per-sublevel beta=1, high-var
(5th-95th random-layout spread >= 20 s) R2, LORO-CV R2 (weights refitted without each runner).

| idea | hypothesis | IN R2 | IN beta | IN chi2/k | IN hv R2 | LORO-CV R2 | OOS R2 | OOS beta | OOS chi2/k | OOS hv R2 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| old judge | | 0.386 | 0.78 | 81/40 | 0.395 | - | 0.320 | 0.79 | 75/40 | 0.361 | |
| N0 judge2 as shipped | | **0.536** | 0.98 | 50/40 | 0.557 | - | **0.418** | 0.93 | 51/40 | 0.475 | **kept** |
| N1 refit the 5 weights on the net outcome | creature pokos shift the balance of the parts | 0.537 | 0.99 | 49/40 | 0.560 | 0.508 | 0.416 | 0.93 | 52/40 | 0.472 | no gain; weights barely move (walk 1.29, carry 0.75, haz 0.52, gate 0.58, adj 0.41) |
| N2 + old bug term, free weight | | 0.543 | 0.99 | 50/40 | 0.566 | 0.514 | 0.414 | 0.93 | 53/40 | 0.471 | rejected (fits +0.43: a cost, enemy density near the ship, as in round 1) |
| N3 refit + expected creature pokos / 2 credit (weight 1) | the outcome now pays for creatures | 0.534 | 0.99 | 49/40 | 0.557 | 0.505 | 0.410 | 0.92 | 51/40 | 0.467 | rejected |
| N4 refit + creature term, free weight | | 0.538 | 0.99 | 50/40 | 0.560 | 0.493 | - | | | | rejected in-sample: fits **+1.03** (creatures near the route cost time, net of their pokos) |
| N5 refit + carrier pokos credit (taking a creature-carried treasure also pays the carrier) | | 0.537 | 0.98 | 50/40 | 0.560 | 0.508 | - | | | | no change, rejected |
| N6 shipped + creature credit (weight 1, no refit) | | 0.533 | 1.00 | 49/40 | 0.554 | - | 0.413 | 0.94 | 50/40 | 0.469 | rejected |
| N7 hazard split: in-the-way teki worth pokos vs the rest | fights that repay pokos cost less net | 0.537 | 0.99 | 50/40 | 0.560 | 0.507 | 0.415 | 0.92 | 53/40 | 0.472 | rejected; weights 0.50 (poko teki) vs 0.60 (others): the right direction, but not significant. **Flag on priors** |
| N8 soft-choice temperature 2 s / 10 s (refit) | | 0.535 / 0.537 | | | | 0.501 / 0.509 | - | | | | flat, keep 5 s |
| N9 walking = route-tree length (union of routes on the waypoint tree) instead of the straight-line MST | the captain walks corridors | 0.480 | 1.00 | 72/40 | 0.488 | 0.440 | - | | | | rejected |
| N10 MST walking + route-tree length, free | | 0.537 | 0.99 | 49/40 | 0.560 | 0.507 | - | | | | tree weight 0.01, rejected |
| per-sublevel scale, empirical-Bayes shrunk | | tau2 = 0 | | | | LORO = base | - | | | | nothing to scale in-sample (as round 1) |

Raw OOS (impossible poko counts kept, n=415): old 0.176 (beta 0.83), judge2 0.216 (beta 0.95),
high-var 0.385 vs 0.482. One play (wr30_iid01 HoB-2, 580 treasure pokos on a layout with no
treasure) is 34,600 s2 of squared error on its own.

**Decision: judge2's score is unchanged.** Crediting expected creature pokos is not supported:
the weight that fits is the wrong sign in-sample, and every creature variant is slightly worse
in-sample and OOS. Creature pokos are a near-constant per sublevel (absorbed by the sublevel
effect) plus runner/measurement noise; the time to fight and carry route creatures is already in
the hazard term, which the net outcome barely changes (N7).

## Final (unchanged judge2 vs old, valid plays; `python judge2/final_eval.py`, saved in data/final_eval_net.txt)
| | old IN | judge2 IN | old OOS | judge2 OOS | old all | judge2 all |
|---|---|---|---|---|---|---|
| R2 (slope 1) | 0.386 | 0.536 | 0.320 | 0.418 | 0.373 | 0.496 |
| corr2 | 0.420 | 0.536 | 0.343 | 0.421 | 0.400 | 0.497 |
| beta | 0.78±0.04 | 0.98±0.04 | 0.79±0.06 | 0.93±0.06 | 0.79±0.03 | 0.97±0.03 |
| chi2 per-sublevel beta=1 | 81/40 | 50/40 | 75/40 | 51/40 | 105/41 | 79/41 |
| high-var R2 | 0.395 | 0.557 | 0.361 | 0.475 | 0.394 | 0.530 |
| high-var beta | 0.78 | 0.99 | 0.82 | 0.97 | 0.80 | 0.99 |

Per-cave beta, all plays, old -> judge2: BK 0.63->0.97, CoS 0.82->1.31, EC 0.59->0.92, FC 0.73->0.96,
GK 0.74->0.92, HoB 0.59->0.68, SCx 0.86->1.04, SH 0.90->0.94, WFG 0.94->0.92. OOS-only: CoS 1.57±0.22
and HoB 0.38±0.28 stand out (HoB low in round 1 too).
Per-sublevel (all plays, judge2 beta ± SE): high spread GK-3 0.78±0.23, SH-2 0.80±0.10, SCx-7 0.74±0.16,
FC-4 0.78±0.11, SH-6 0.93±0.16, FC-6 0.95±0.12, GK-2 1.00±0.21; furthest from 1: FC-3 1.53±0.21,
CoS-4 1.48±0.20, SH-4 1.43±0.21, FC-5 1.40±0.16, SCx-3 1.39±0.16 vs FC-1 0.59±0.23, FC-2 0.58±0.17,
WFG-2 0.60±0.14, BK-2 0.47±0.20. chi2 79/41 on all plays is mild heterogeneity, but in-sample
alone shows none (tau2 = 0), so per-sublevel rescaling cannot be validated yet. Worth a look with more runs.

## Outliers (round 2)
In-sample residual sum of squares is concentrated in SH-6 (11.5%), GK-3 (9%), CoS-3 (8%), FC-3 (5%).

Judge (or runner-choice) errors:
- SH-6 dry lens far off the hole route is sometimes skipped: IceCube 0x7D42A01E (lens 590 cm from
  the ship, 590 cm off the hole route; residual +38 s), IceCube 0x28B493CF (2411 cm away), and
  OOS theurbandear 0x4872B7C4 (883 cm off route, +31 s). judge2 predicts taking it; every lens
  <= 470 cm off route was taken. Skipping cost these runners ~60 s of pokos, so the judge picks
  the better line; not modelled (3 plays, 2 runners).
- SH-6 water rule: 7 of 8 lenses whose carry crosses water were skipped. The exception, OOS iid01
  0x4C0218B3 (lens 35 cm off the hole route), took it: actual +7.5 s vs judge +33.7 s. But
  theurbandear 0x4568D848 (0 cm off route, water) skipped, so no refinement.
- GK-3 (spread 50 s, beta 0.78): IceCube 0x5A6727F3 (+25 s, near hole and treasures, slow) and
  JKira 0x6469A19E (+27 s) vs JackDraz fast on far-hole layouts (0x17EE990A -17 s, 0x566D2C05 -14 s).
  Anode Beetles and wires along the routes; execution variance, nothing robust (as round 1).
- FC-1 and FC-2 betas ~0.6 on all plays: the judge's spread there is too wide.

Suspected measurement errors (main checkout data as of the snapshot; run, sublevel, entry frame):
- wr30_iid01_y2v8lljz HoB-2 f29932 (0x2C5B3BF9): panel values [450, 130] = 580 treasure pokos on a
  layout with no treasure; the next sublevel HoB-3 f33511 (0x623D16F2) read [150, 150] where the
  layout holds 150 + 230. Panels attributed to the wrong sublevel (or a wrong seed/boundary).
- CoS-3 kan_nichiro (130) read as 100 in wr21_IceCube_z11q6nwz f177144 (0x004F97D7) and
  wr17_theurbandear_mk4r711y f177162 (0x5F8B92F7): values [100, 100] where 26 of 28 CoS-3 plays read
  [100, 130]. Total pokos ~20-30 short, cost ~10-15 s too high (residuals +24 and +21 s).
- 02_iid01_y46k3x3z FC-1 f120788 (0x1CBD8CA1): values [100, 100], layout holds 70 + 100 (impossible).
- 10_theurbandear_z52nqvgz SCx-7 f115879 (0x174F8D49): values [100, 300, 100], layout holds 100, 300,
  60 (tape_red read as 100; impossible, 500 > 460).
- 10_theurbandear_z52nqvgz SCx-6 f112805: bolt_l 85 read as 80 (minor).
- `collected` (the treasure names shown on the site) does not match `values` in about a dozen more plays, e.g.
  02_iid01 SH-2 f56932 values [190] but collected futa_a_silver (40); SH-4 plays list flower_red (20)
  where the second value is 120. The outcome uses values, so only the display is wrong.

## How to run (round 2)
- `python judge2/snapshot_net.py <main checkout>/data/output` (once) -> data/plays_net.json
- build (below), then `python judge2/run_judge2.py` -> data/judged.json (layout dumps, git-ignored)
- `python judge2/vmodel.py` (checks the Python model equals the Rust score),
  `python judge2/ideas_net.py [NAME]` (in-sample + LORO), `python judge2/ideas_net.py --oos NAME`,
  `python judge2/creatures.py`, `cre_eval.py`, `cre_lin.py` (creature pokos),
  `python judge2/final_eval.py`, `persub_net.py [in|oos|all]`, `outliers_net.py [in|oos|all] [N]`.
- In a git worktree, `crate/Cargo.toml`'s path to cavegen3 (`../../../cavegen3`) needs
  `cavegen3` next to the worktree (a junction to Desktop/Claude/cavegen3 works).

## How to run
Build: `cargo build --release --manifest-path judge2/crate/Cargo.toml --target-dir data/build/judge2`
- `data/build/judge2/release/judge2.exe SH-6 0x2B1980E4 [more seeds]` prints old and judge2 scores.
- JSON lines on stdin: `{"sub":"SH-6","seed":"0x2B1980E4"}` -> old, pod2, both parts and the
  take/skip choices with probabilities; add `"dump":true` for the layout geometry;
  `{"sub":"SH-6","reference":1000}` -> both judges on 1000 evenly spaced seeds.
Analysis (Python venv): snapshot.py (once), split.py (once), run_judge2.py (layout features ->
data/judged.json, ignored by git, 6.6 MB), ideas.py [--oos NAME], final_eval.py, show.py SUB.
