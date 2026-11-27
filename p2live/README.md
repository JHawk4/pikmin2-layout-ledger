# p2live

A Rust port of the p2seeds seed detector (the Python pipeline in `p2seeds/` stays the reference).
It covers milestones 1 and 2 of the live tool in `docs/realtime-obs.md`: a library plus a command
line over video files, checked to give the same seeds as Python, and the live loop (`live.rs`) with
a `replay` command that feeds it a VOD as a capture would.

```bash
cargo build --release --manifest-path p2live/Cargo.toml
# re-analyze every entry of a run and compare with its seeds.json (needs ffmpeg/ffprobe on PATH)
p2live/target/release/p2live entries data/output/01_JackDraz_mewq470m/seeds.json --jobs 4 --out parity.jsonl
# all runs, then a summary
p2live/scripts/parity_all.sh OUT_DIR /path/to/main/checkout
# Python's own per-entry result for the entries that differ from seeds.json (p2seeds environment)
python p2live/scripts/python_per_entry.py OUT_DIR /path/to/main/checkout --jobs 4
python p2live/scripts/parity_summary.py OUT_DIR
```

Glyph templates come from `vendor/CaveGen/files/templates/letters` (`P2LIVE_LETTERS` overrides),
sublevel digits from `p2seeds/src/p2seeds/data/digits` (`P2LIVE_DIGITS`).

| module | port of |
|---|---|
| `img` | templates.prep/match, cv2 INTER_AREA resize, TM_CCOEFF_NORMED (direct and FFT) |
| `templates` | glyphs, caves.py, letters_model.py |
| `calibrate` | events.is_entry_screen, analyze.entry_runs, calibrate.py |
| `track` | track.py |
| `fit` | fit.py (scipy's soft_l1 least squares as damped IRLS with bounds) |
| `lattice` | lattice.py, search._score, search.search_near |
| `digits` | digits.py and the sublevel-number reading in analyze.py |
| `analyze` | analyze.py (variants, timing-step refits, confidence), events.detect |
| `video` | frames through ffmpeg, gray as OpenCV converts it |

## Parity (2026-11-22)

Every entry of every run in `data/output` and `data/output_at` with its video on disk:
1,907 entries in 33 runs (06_keisen's 97 entries were skipped, since its video is not on disk).

- **1,681 entries:** seed and sublevel equal to `seeds.json`.
- **226 entries differ from `seeds.json`:** Python's own per-entry analysis gives the same seed,
  confidence and sublevel as p2live in all 226 (`python_per_entry.py`).
  - `seeds.json` holds each run's final seeds. They come after `chain.py`'s cross-entry pass
    (which confirms, replaces or fills in seeds using the neighbours) and after the
    sublevel-sequence fill-in. `p2live entries` does neither.
- **Caves:** 0 recognized differently.

Two fixes were needed to get there:

1. **YUV to BGR with the BT.601 matrix.** This is what OpenCV's reader does. ffmpeg honours a
   stream's bt709 tag, and most of these videos carry one. With bt709, saturated pixels came out
   up to ~30 levels off, so some sublevel digits read differently. With the BT.601 matrix the
   frames are byte-identical to cv2's.
2. **Two Python detector changes made after the port:**
   - a strong Japanese cave match (≥ 0.65) needs only a 0.08 margin;
   - above the name, the entry-screen check only looks at the middle half of the width, so a
     timer in a corner no longer hides the screen.

Things the comparison turned up in the Python data:

- `08_CurtisDN` HoB-2 (frame 29886) and FC-1 (122556): `seeds.json` has medium-confidence seeds
  that the RNG cannot reach from either neighbour. The per-entry high-confidence seed links to both
  (HoB-2 is 32,484 steps after HoB-1 and 24,125 before HoB-3), so the cross-entry pass replaced a
  right seed with a wrong one.
- `wr29_JackDraz` GK-4 (159307): the per-entry seed and the chain pass's seed both link to their
  neighbours, so the RNG alone does not tell which one is right.

Speed: analysis takes a median of 13.8 s per entry (p90 54 s) with 4 entries at a time sharing
4 busy cores. Calibrate and track dominate. Milestone 2 covers the live speed-ups.

## Live loop (milestone 2, 2026-11-23)

```bash
# simulated: as fast as it can, latency = frames waited / fps + measured analysis time
p2live/target/release/p2live replay data/output/wr17_theurbandear_mk4r711y/seeds.json --speed 0 --caves en --out live.jsonl
# real time with two workers, a 60 fps capture (each frame twice) that stutters 3% of the time
p2live/target/release/p2live replay data/output/wr29_JackDraz_mr95qp8m/seeds.json --speed 1 --workers 2     --double --jitter 0.03 --start 900 --duration 600 --caves en
```

`replay` compares each answer with the run's `seeds.json`. It prints how long after the entry screen
settled the first answer and the final answer were ready.

How the live answer gets fast (details in `live.rs`):

- **Early name read.** The cave name is read 8 game frames after the screen settles. After the
  stream's first screen, the learned scale makes this about 0.15 s.
- **Prefill.** The letters are then matched on the buffered fall frames into a per-screen
  `MatchCache`. Single templates only; the doubled-letter pair templates are matched on demand,
  with one correlation per letter for all gaps (`img::match_pairs`).
- **Seed attempts** at 12, 16, 20, 24, 28, 32 and 40 game frames after the settle. Each is a
  quick analysis that reuses the cache. A high-confidence or chained seed is reported at once.
- **Full analysis after the last attempt.** If the reported seed is not high, the full analysis
  runs. It replaces the shown seed only with a higher confidence for the same seed, or with a
  different seed that is high or chained.
- **Flicker repeats.** A screen that flickers and repeats within 5 s is analyzed again. Its answer
  replaces the first one if it is better.

### Results

**Simulated, whole runs.** Other jobs kept the 4-core machine busy throughout.

| run | first answer, median / p90 | seeds equal to offline |
|---|---|---|
| wr17 | 0.91 / 1.24 s | 53/53 |
| JKira | 0.90 / 1.27 s | 51/52 |
| CurtisDN | 1.08 / 4.06 s | 49/54 |
| wr20 | 1.13 / 1.41 s | 51/51 |
| wr29 | 1.05 / 2.11 s | 52/52 |

- **No wrong high-confidence seed.**
- **JKira BK-4:** a Medium answer where the offline answer is Low.
- **CurtisDN:**
  - Four differing entries are chained answers (SH-3, BK-3, GK-3, GK-4). Each is confirmed by its
    neighbours: the next sublevel's high seed chains from it, by 3,468 to 85,344 RNG steps. GK-3
    chains from GK-2. The offline Low answers chain to neither neighbour, so here the live answer
    is the right one.
  - SH-6 is Low both ways.
- **Before these speed-ups:** the medians were 1.1–2.1 s.

**Real time** (`--speed 1 --workers 2`, 3% stutter):

| stretch | first answer, median / p90 / max | seeds |
|---|---|---|
| wr17, 20 min at 30 fps | 1.28 / 1.60 / 1.91 s | 12/12 |
| wr29, 10 min at 60 fps | 3.60 / 5.66 / 7.89 s | 8/8 |

- **wr29 was measured with the CPU at 100% from other jobs.** The capture thread fell up to 7 s
  behind, and every attempt ran late with the whole fall.
- **The same wr29 stretch simulated:**
  - 2.2 s median at 60 fps with stutter;
  - 1.5 s median at 30 fps.
- **To do:** time it again on an idle machine.

**Stutter at 60 fps.** A doubled capture that also drops frames used to lose a game frame per drop.
The skipped-frame rule in `game_times` compared against a median that was half repeats. Clips that
repeat more than 40% of their frames now use the median of the neighbouring changes only. This
took the wr29 stretch from 6/8 to 8/8. The rule changes no entry of wr20. On wr26 (variable frame
rate) it changes one entry, which has no offline seed.
