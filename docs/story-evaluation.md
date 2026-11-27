# Evaluation: top 5 Pay Off Debt (GameCube) runs

Videos were downloaded with `srcom_videos` (360p, or 480p for kobachi, at 30 fps) and processed with
`p2seeds run`. These are the results after the fixes listed below.

| # | Runner   | Video        | Feed (x0-x1, y0-y1)  | Entries found | High | Medium | No seed |
|---|----------|--------------|----------------------|---------------|------|--------|---------|
| 1 | JackDraz | 360p         | 175-640, 0-360       | 52            | 51   | 1      | 0       |
| 2 | iid01    | 360p         | 121-620, 12-348      | 52            | 52   | 0      | 0       |
| 3 | kobachi  | 480p, splits panel | 205-852, 43-479 | 52           | 47   | 5      | 0       |
| 4 | Kap      | 360p         | 160-640, 0-360       | 52            | 52   | 0      | 0       |
| 5 | chemical | 360p         | 160-640, 0-359       | 52            | 51   | 1      | 0       |
| | **Total** | | | **260** | **253** | **7** | **0** |

- **Entries per cave:** every run has the same set: EC 1-2, HoB 1-5, WFG 1-5, SH 1-7, BK 1-7, SCx 1-8,
  FC 1-7, CoS 1-5, GK 1-6.
  - All five runners skip SCx9 and FC8, so this looks like the PoD route rather than missed entries.
- **Sublevel numbers:** all 260 come from reading the digit on screen. None needed the sequence
  fallback, and all are consecutive within each cave.
- **Rejected screens:** overworld area titles, menus and memory-card screens produce candidate events.
  All of them are rejected by cave-name recognition: the best score is ≤ 0.35 with a margin ≤ 0.04,
  against ≥ 0.38 and 0.12 required.
- **Cost:** about 20 minutes per 1.5-hour video on one core; five videos in parallel take about the
  same total time.

## What the first pass got wrong, and the fixes

| Problem | Cause | Fix |
|---|---|---|
| kobachi: 0 entries | The feed box included an 18 px strip of the splits panel, which is lit, so no frame looked like a dark entry screen | `find_feed` pulls each edge inward to where pixel variation reaches the game's level (`_tighten`) |
| iid01 FC6, GK6; Kap BK6: no seed or a wrong low-confidence seed | A repeated frame mid-fall that `drop_repeats` missed: after re-encoding, the duplicate differs by 0.1-0.3 instead of 0 | A frame counts as a repeat when it changed < 25% as much as its neighbors |
| chemical FC2: no seed | The capture skipped one game frame mid-fall, leaving no trace in the pixels | Fallback refit with a ±1 frame step at each position. The best shifts by letters kept and by rms both go to the search, and the more confident result wins |
| chemical GK5, kobachi WFG1: "too few letters" | Uneven frame pacing (one game frame shown twice, then the next skipped) | `game_times` gives each frame its game time: 0 for a repeat, 2 for a ~1.5× jump next to a repeat |

The fixes changed no seed that was already high confidence. Four entries that were medium became
high with the same seed. Kap BK6 changed from a wrong low-confidence seed to a high-confidence one.

## Known limits

- **Digits:** two-digit sublevels (HoH, DD) and the digit 9 have no reference yet, so story-mode
  caves past sublevel 8 depend on the sequence fallback. None of the PoD runs reach them.
- **Language, platform and categories:** only English GameCube runs have been tested. Other
  categories (All Treasures, 2-Player Battle, etc.) are untested.
- **Ground truth:** there is no independent ground truth for the seeds. "High" means at least 10
  letters agree tightly and the runner-up is far behind. Rendered layouts (`img/*_layout.png` in each
  report) can be compared by eye with the video.
