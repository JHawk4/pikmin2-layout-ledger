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
