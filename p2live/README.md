# p2live

A Rust port of the p2seeds seed detector (the Python pipeline in `p2seeds/` stays the reference).
It is milestone 1 of the live tool in `docs/realtime-obs.md`: a library plus a command line over
video files, checked to give the same seeds as Python.

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
