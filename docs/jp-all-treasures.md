# Japanese All Treasures runs: can the seeds be read?

Date: 2026-11-21. Follows up [`story-evaluation-at.md`](story-evaluation-at.md) (2026-11-14), which first ran the reader on the
top 3 Japanese GameCube All Treasures runs. This pass re-checks those results, tries two more Japanese runs
(both 360p, one with a timer overlay), checks the recovered layouts against the real floor times,
and fixes what was cheap to fix.

## Verdict

**Yes, for clean GameCube captures at 480p.** On those, about 3 in 4 floors get a high-confidence
seed. The layouts are right: floors the judge rates as harder than usual really took the runners longer
(see "Are the layouts right?"). Three caves stay out of reach on every capture: Dream Den (夢の穴, 3 characters),
Submerged Castle (水中の城, 4) and, without a clean 480p capture, White Flower Garden (白い花園, 4). Their names
are too short to pin down a seed.

**360p captures work only in part** (20–50% of floors). The letters fall the whole name height in about 9
frames, and at 360p too few clean points land on each fall. A 720p copy of the same run helps a little
but not much (5 instead of 3 high floors on one stretch). **Wii U VC runs (ranks 1, 2) remain out of reach**
(see [`story-evaluation-at.md`](story-evaluation-at.md)).

## Per run

Screens = cave names read (entry screens recognised). High and medium are seeds after linking. Failed =
floors read with no usable seed (low or none). Numbers for the first three runs are their saved letter fits
relinked with the old and with the new linking code, so the effect of the linking changes is shown alone.

| # | Runner | Capture | Screens read | High | Medium | Failed | Notes |
|---|---|---|---|---|---|---|---|
| 3 | iid01    | GC, 360p (498×336) | 80  | 15 | 0 | 65 | no change from the new linking |
| 4 | kobachi  | GC, 480p | 109 | 80 → **83** | 0 | 26 | new: CoS 1, CoS 2, SC 4 |
| 5 | JackDraz | GC, 480p | 108 | 76 → **80** | 0 | 28 | new: WFG 2–5 |
| 6 | keisen   | GC, 360p, timer in a corner | 0 → **97** | **50** | 1 | 46 | read nothing before the overlay fix; HoH margin fix adds about 7 more screens |
| 10 | CurtisDN_ | GC, 360p | 98 | 9 → **19** | 25 → **4** | 75 | the old 25 mediums were mostly wrong reads |
| 10 | CurtisDN_ 0:30–1:10 | same run, **720p** | 17 | 5 | 1 | 11 | 360p, same stretch: 3 high, 1 medium |

High seeds per cave (best runs):

| Cave (name, characters) | kobachi | JackDraz | keisen | CurtisDN_ |
|---|---|---|---|---|
| EC 始まりの洞窟 (6)     | 4/4 | 4/4 | 4/4 | 0/4 |
| HoB けだものの穴 (6)    | 5/5 | 4/4 | 2/5 | 0/5 |
| WFG 白い花園 (4)        | 3/5 | 4/5 | 0/5 | 0/5 |
| SCx 地下の秘密基地 (7)  | 9/9 | 9/9 | 9/9 | 3/9 |
| FC 辺境の洞窟 (5)       | 8/8 | 7/8 | 5/8 | 1/8 |
| CoS クモの根城 (5)      | 5/5 | 4/5 | 0/5 | 0/5 |
| GK 食神の台所 (5)       | 6/6 | 4/6 | 0/6 | 2/6 |
| SC 水中の城 (4)         | 1/5 | 0/5 | 0/5 | 0/5 |
| SR シャワールーム (7)   | 2/7 | 5/7 | 6/7 | 5/7 |
| BK デメマダラの王国 (8)  | 13/13 | 11/11 | 7/7 | 4/11 |
| SH ヘビガラスの穴 (7)   | 6/6 | 7/7 | 7/7 | 4/7 |
| CoC 混沌の魔窟 (5)      | 9/10 | 8/10 | 7/10 | 0/10 |
| HoH 百戦錬磨の穴 (6)    | 12/12 | 13/13 | 3/5 read | 0/2 read |
| DD 夢の穴 (3)           | 0/14 | 0/14 | 0/14 | 0/14 |

(All four columns are after the new linking. kobachi and JackDraz are relinked from their saved letter fits, so
they come out slightly below [`story-evaluation-at.md`](story-evaluation-at.md)'s 85 and 78, which include digits and links re-read by hand
afterwards. A few floors in each run were never read, see [`story-evaluation-at.md`](story-evaluation-at.md).)

## Are the layouts right?

The seeds are confirmed by the RNG chain, but nothing had compared a Japanese layout with the video. Two
checks:

- **Floor times.** For each high-confidence floor in iid01, kobachi and JackDraz, compare the judge's
  score against the median random layout of that floor (CaveGen's All Treasures judge, Japanese caveinfo)
  with how long the runner actually spent on it (to the next entry screen), relative to the
  other runs' time on that floor. If the seeds were wrong, the two would be unrelated. Over 113 floors
  they agree: **Spearman 0.40, p ≈ 1.5e-5**. A layout the judge calls hard really was slow.
- **By eye.** Comedown and landing views next to the CaveGen3 layout for 7 kobachi floors
  (`data/jp_at/spot/`, not committed). They are consistent where the pictures can tell (e.g. SCx 3: the
  hole is reached about 8 s after landing, matching the layout's short path), but these views are dark
  and close up, so the timing check is the stronger evidence.

**Region.** CaveGen's Japanese caveinfo (`files/gc/caveinfo-jpn`) differs from the US one only in two
*challenge-mode* files. Story-mode layouts are identical, so CaveGen3's pictures (which have no Japanese
region) are right for Japanese runs. What does differ is `config_jpn.txt`: 28 treasures have different
carry weights or values. That changes judge scores and pokos, not the layout. So the Java judge with
`-region jpn` (what `cavegen.REGION` already does) is still needed for scores.

## What fails, and why

1. **Names of 3–4 characters (DD, SC, WFG).** Every letter is measured about as well as an English
   one (σ ≈ 0.011 of the 0–5 speed range), but the shared speed offset takes one letter away. DD leaves 2
   useful numbers: 3–6 random seeds per 100k RNG steps fit as well as the true one, so even a known
   neighbour can't pick it out. That is the limit of the letters, not of the code; it would need another
   source of information (for example matching the comedown view against candidate layouts). SC leaves 3,
   so each link is a few percent likely to be chance. That is too weak alone, but enough along a run of floors
   (fixed in part, below).
2. **360p captures.** Per-entry reads go wrong without looking wrong: CurtisDN_'s Subterranean Complex
   read 7 letters on every floor, and 6 of the 9 seeds were wrong, with "medium" confidence. A wrong read
   looks like any other until it is checked against its neighbours.
3. **Overlays.** A timer in a top corner (keisen) made the entry-screen detector reject every screen
   (fixed).
4. **Missed screens.** Hole of Heroes screens rejected because a rival name sharing "の穴" came within
   the margin (fixed, see below); a few screens per run are never detected ("no settled entry screen").
5. **Speed.** A 3.5 h run takes 8–9 h to read on this machine with other jobs running (2.8 h when it
   had the machine to itself). Fine offline, but a batch of 20 runs is a multi-day job.

### Short names when the previous seed is known

A known previous floor limits the next seed to a window: at most ~140k RNG steps within a cave and
~360k across a day. A 4-character name gives 3 usable speeds. Within that window a wrong seed fits as
well as the right one only a few percent of the time, so a 4-character floor *is* readable after a
known floor. That is how WFG 2–5 (JackDraz) and SC 4 (kobachi) were found. Submerged Castle still
fails because of the chain, not the letters:

- kobachi: SC 3 measured too few letters. With one floor missing, the gap from GK 6 to SR 1 has
  several paths that fit, and only SC 4 is the same on all of them.
- JackDraz: GK 6 is low too, so the gap from GK 5 to SR 1 is 7 floors, past the 6 the gap fill takes on.

Dream Den (3 characters) stays out of reach even after a known floor: 3–6 wrong seeds fit per 100k
steps, and floors are ~60k apart.

**Can the time between entry screens narrow the window?** No, not enough. Over 1,361 pairs of
consecutive high-confidence floors (all 28 runs), the RNG advances 740 steps per second of play
(median), but the rate depends on the sublevel and the run. Fitted per sublevel, distance from time is
off by ±38% for 90% of floors (`data/jp_at/timedist.py`, `timedist2.py`). For a Dream Den floor of
~100k steps that leaves a window of ~75k steps, still 2–5 wrong seeds. It would help Submerged Castle
by a factor of about 1.5–3, too little to be worth the extra code now.

## Fixes on this branch

| Problem | Fix |
|---|---|
| Timer overlay in a top corner hides every entry screen | `events.is_entry_screen`: above the name, only the middle half of the width must be dark (gameplay is still ruled out by the bottom HUD) |
| SC/WFG/CoS links each 1–5% likely to be chance, so `_chains` drops them | `chain._bridge`: follows each gap of up to 6 unknown floors between two known seeds as one path (top 4 window candidates per floor, best 40 paths), scores the whole path by the product of its link chances times the number of paths tried, requires it to lead into the known seed after the gap, and assigns only seeds every near-best path agrees on |
| One wrong medium read between two right ones hides them from each other (CurtisDN_ SCx 2) | `_backbone` compares each seed with the next 6 known ones (1M steps per floor past the first) |
| Wrong medium reads stay medium | `_demote_strays`: a medium read out of RNG order with the backbone seeds on both sides drops to low, and the window searches can refill it |
| Backbone seeds a few floors apart and close in RNG stay medium | promoted to high when within 1M steps per floor |
| A "match" 41 steps after the previous floor looked near-certain | `MIN_LINK = 500`: generating a floor takes thousands of RNG calls (the closest real pair is ~900, BK purple-farm re-entries) |
| Hole of Heroes rejected at 0.72 vs 0.60 | Japanese names scoring ≥ 0.65 need a margin of 0.08, not 0.12. Re-running keisen's HoH stretch alone: 12 HoH screens read instead of 5, 3 high even without anchors outside the stretch (the full run was not redone) |

**Checked against every saved run** (25 Pay Off Debt and 3 All Treasures `fits.json`, relinked with old
and new code): no high seed changed or was lost. Gains are listed in the table above. Twelve medium reads in two
Pay Off Debt runs (CurtisDN_ `y6eo640z`, JackDraz `mr95qp8m`) dropped to low: each was out of RNG order
with the high seeds on both sides, so they were wrong (all "first falling stretch" reads), and the site only
counted mediums that were in order anyway. Tests: `p2seeds/tests/test_chain.py` adds the bridge, the
stray read and the minimum link distance.

## Adding these runs to the site

1. **Process** (per run, about 3–9 h): `analyze`, then `render` and `judge --kind at` (Java CaveGen,
   `-region jpn`; set automatically from the cave names' language). Pictures can come from CaveGen3, as story
   layouts are the same in both regions.
2. **A judge for All Treasures.** judge2 is fitted on Pay Off Debt times and routes. All Treasures
   collects every treasure, so it needs its own fit (or CaveGen's `at` judge as it stands, which the
   timing check above says is meaningful: ρ = 0.40). The judge2 pipeline (`judge2/`) could be refit on these runs'
   floor times once 5–10 runs are processed.
3. **Treasure panel and pokos.** `treasures.py` reads the English treasure panel; the Japanese panel
   and the Japanese values (`config_jpn.txt`) are untested.
4. **Site changes.** A separate All Treasures section (or a category switch), as luck percentiles and
   time saved compare like with like. Hide low-confidence floors, leave out the BK purple-farm entries
   (the first BK group in kobachi and JackDraz), and show DD/SC as "not readable" rather than missing.
5. **Which runs.** The 480p GameCube runs (kobachi, JackDraz) are worth publishing now. keisen and
   iid01 at 360p are half-empty; CurtisDN_ at 360p is mostly empty. If a runner has a 720p or 1080p
   upload, use it: `srcom_videos` caps at 480p, and YouTube has no 480p for many 16:9 uploads, so these come down as 360p.

## Files

- Outputs (not committed): `data/jp_at/out/<run>/` (keisen, CurtisDN_, the 720p and 360p stretches),
  `data/jp_at/relink/` (the same relinked with the final code), `data/jp_at/spot/` (pictures),
  `data/jp_at/relink_{old,new}.json` (the old-vs-new comparison over every saved run), `data/jp_at/logs/`.
- Scripts used for the checks are in `data/jp_at/*.py` (timing check: `timecheck.py`; bridge probe:
  `bridge_probe.py`).
