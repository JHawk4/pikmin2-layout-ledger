# Evaluation: top 5 All Treasures runs (GameCube and Wii)

The five fastest All Treasures runs on speedrun.com, across both consoles. Every one is the Japanese
version, so this is also the first test of Japanese cave names.

| Rank | Runner    | Time    | Console            | Video | Result |
|------|-----------|---------|--------------------|-------|--------|
| 1    | mercysnow | 3:18:02 | Wii U VC (JPN)     | 360p  | not processed (see the Wii section) |
| 2    | kobachi   | 3:21:59 | Wii U VC (JPN)     | 360p  | not processed (see the Wii section) |
| 3    | iid01     | 3:30:46 | GameCube (JPN)     | 360p  | 17 of 80 entries seeded |
| 4    | kobachi   | 3:32:56 | GameCube (JPN)     | 480p  | 85 of 109 entries seeded, all high confidence |
| 5    | JackDraz  | 3:36:12 | GameCube (JPN)     | 360p  | 78 of 108 entries seeded, all high confidence |

The videos are in `data/videos_at`, the results in `data/output_at/<run>/` (`seeds.json`, `report.html`,
`judge.html`), and the logs in `data/logs/at_*.log`.

## High-confidence seeds per cave (GameCube runs)

| Cave (Japanese name, characters) | iid01 | kobachi | JackDraz |
|---|---|---|---|
| EC 始まりの洞窟 (6)        | 2/4  | 4/4   | 4/4   |
| HoB けだものの穴 (6)       | –    | 5/5   | 4/4   |
| WFG 白い花園 (4)           | 0/5  | 3/5   | 0/5   |
| SCx 地下の秘密基地 (7)     | 7/9  | 9/9   | 9/9   |
| FC 辺境の洞窟 (5)          | 0/8  | 8/8   | 7/8   |
| CoS クモの根城 (5)         | 0/5  | 3/5   | 5/5   |
| GK 食神の台所 (5)          | 0/6  | 6/6   | 5/6   |
| SC 水中の城 (4)            | 0/5  | 0/5   | 0/5   |
| SR シャワールーム (7)      | 0/7  | 6/7   | 5/7   |
| BK デメマダラの王国 (8)    | 7/7  | 13/13 | 11/11 |
| SH ヘビガラスの穴 (7)      | –    | 6/6   | 7/7   |
| CoC 混沌の魔窟 (5)         | 0/10 | 10/10 | 8/10  |
| HoH 百戦錬磨の穴 (6)       | –    | 12/12 | 13/13 |
| DD 夢の穴 (3)              | 0/14 | 0/14  | 0/14  |
| **Total**                  | **16 + 1 medium / 80** | **85 / 109** | **78 / 108** |

- **BK appears twice.** kobachi and JackDraz farm purple Pikmin in BK ("Farm" split) before the real
  descent. The farm entries are 15–20 s apart and only ~1,000 RNG steps apart.
- **Some entries are missing.** HoH 4, 6 and 8 (kobachi), HoH 8 and 11 (JackDraz) and SH 3 (kobachi) have
  no entry: their screens weren't detected or the name wasn't recognized. The sublevel numbers of
  the other entries are still right, because they are read from the screen.
- **iid01 has no HoB, SH or HoH entries.** Its splits include HoB and SH, but their entry screens weren't
  recognized; the splits don't name HoH. Its route also differs: the splits include AW, VoR, PoD and
  95P.

## How the seeds are confirmed

Japanese names are short: 3–8 characters, each falling as one letter. The first one or two fall
while the previous screen is still fading out, so usually only 2–6 letters can be measured. That is
rarely enough to pick one seed out of 2^31.

What makes it work is the chain. Between two sublevel entries the game advances the RNG by a bounded
amount, while unrelated seeds are about 2^31 steps apart.

- `chain.link` follows each entry's top candidates through the next entry's window (1M steps).
- It scores every link by the chance that a match that good would turn up at that distance by
  coincidence (`link_chance`).
- It accepts a chain when the product of those chances is ≤ 1e-4 (high) or ≤ 1e-3 (medium).
- Two seeds that were each found on their own and also lie within 1M steps of each other are both
  promoted to high.

Every high seed in kobachi and JackDraz is confirmed by a link to a neighbor. Their RNG distances
from the previous sublevel:

| Run | Links | Median | Largest |
|---|---|---|---|
| iid01    | 12 | 60k | 131k |
| kobachi  | 77 | 64k | 409k (SCx 1, across a day on the surface) |
| JackDraz | 69 | 69k | 471k (CoS 1, across a day) |

These match the Pay Off Debt runs (≤ 137k within a cave, ≤ 360k across caves), allowing for the longer
surface days of All Treasures. A wrong seed would almost never land this close: the chance is about
1M / 2^31 per link.

`fits.json` (the measured letters and global candidates before linking) is saved next to each
`seeds.json`. Running `chain.relink_dir(out_dir)` re-tunes the linking without re-reading the video.

## What fails, and why

- **DD (夢の穴, 3 characters): none in any run.** At most 2 letters can be measured, and 2 letters
  can't single out a seed even within one window.
- **SC (水中の城, 4 characters): none.** Usually 2–3 letters are measured, which is too few to link.
  WFG (白い花園, also 4) only works when all 4 letters are clean (kobachi WFG 1–3).
- **iid01: 360p with a slightly stretched feed (498×336).** Japanese glyphs match weakly at that size
  (track scores ≈ 0.5–0.65 against ≈ 0.7–0.9 at 480p). The letters fall the whole name height in about
  9 frames. Most entries end up with only 3 measured letters, which is too few to start a chain; only
  the long names (SCx, BK) and the start of EC worked. A higher-resolution copy of this run would
  probably fix most of it.

## Wii U VC (ranks 1 and 2): not feasible yet

- **16:9 output.** Character spacing is stretched about 4/3 against the glyph height. The calibration
  now fits the pitch separately (it searches ×0.95–1.3 of the stretched width), but recognition still
  fails: the forced EC match scores 0.26 against ≥ 0.48 needed.
- **Fading and the swirl.** On VC the entry screen fades out before the letters have landed. The
  swirl effect covers much of the name, so only 2–3 letters per entry could be tracked in tests.
- **Untested CaveGen match.** It is unknown whether the Wii U VC uses the same RNG calls for the
  letters and the layout. Nothing confirms it yet.

Making this work would need Wii-specific glyph templates (captured from these videos), a fit that
copes with fades, and one known seed to check the RNG against. That is a project of its own, not a
tuning pass.

## Fixes made for Japanese names and All Treasures

| Problem | Fix |
|---|---|
| No Japanese cave names | `caves.CAVES_JA`: 14 names from CaveGen's `jp_cave_names.txt`, glyphs `u<codepoint>.png` |
| Japanese pitch ≠ glyph width (EC vs FC confusion) | `calibrate.compose` draws glyphs at `gsx` inside a fitted advance; the pitch is searched |
| DD (夢の穴) runner-up is a substring of HoB (けだものの穴) | the margin ignores rival names that contain the matched name |
| DD matched random text at ~0.40 | `MIN_CAVE_SCORE_JA = 0.48` |
| WFG entries never detected | the name/sub-band row threshold dropped from 3% to 1.5% (a short name covers ~2.5%) |
| WFG "too few letters with a usable fall" | Japanese fits accept track scores ≥ 0.5 and 2 letters |
| Sublevels 10–15 read as 0–5 | `digit_crop` keeps a narrow leading "1" further away than the grouping gap; added Japanese 0, 4 and 9 references |
| Japanese digits drawn in separate strokes split into two "digits" | read as two digits only if both parts read; otherwise read the crop as one |
| Weak chain links accepted (668k, fit rms 1.6 px) | volume-based `link_chance`, an rms guard, chance-based acceptance |
| JPN layouts rendered with US caveinfo | `cavegen.REGION`: `render` and `judge` pass `-region jpn` for Japanese runs |
| Runs processed with `--no-render` had no layouts | new `p2seeds render OUT_DIR` |

## Judge

The layouts were rendered with `p2seeds render` and scored with `p2seeds judge <run> --kind at`, using
CaveGen's `-region jpn` caveinfo. Each run's `judge.html` shows them.

Figures below count only high-confidence entries on floors that vary by seed. "Saved" is the
judge's median minus its estimate, summed:

| Run | Judged (high) | Saved by layout luck vs median | Luckiest floors | Unluckiest floors |
|---|---|---|---|---|
| iid01    | 13 | +40 s  | SCx 7 (+14.7 s), BK 5 (+8.5 s) | BK 4 (−5.8 s), SCx 5 (−5.3 s) |
| kobachi  | 76 | +108 s | SH 6 (+19.3 s), CoC 7 (+17.1 s), HoH 12 (+16.3 s) | CoS 4 (−22.7 s), BK 6 (−19.1 s) |
| JackDraz | 71 | +121 s | SR 5 (+60.0 s), HoH 3 (+35.0 s), SR 3 (+24.4 s) | CoC 6 (−13.3 s), SH 5 (−13.1 s) |

Caveats:

- `judge.html` (the report-site session's code) also judges **low**-confidence seeds. Those are
  probably wrong and should be ignored or hidden.
- **Farm entries are not descents.** The judge scores the BK purple-farm entries as normal BK floors;
  they should be excluded from any timesave total.
- CaveGen's reference ranks come from its `rank_file.txt`, built with the US caveinfo. For JPN, only
  two treasure names differ (`ch_NARI_03toy`, `ch_NARI_04series`), so ranks should be very close.
- **Layouts not checked against the video.** The seeds are confirmed by the RNG chain, but no
  rendered JPN layout has been compared with what the video shows on that floor.
