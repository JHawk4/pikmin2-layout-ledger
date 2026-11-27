# Pikmin 2 Layout Ledger

A ledger of layout luck, time saved and pokos for Pikmin 2 Pay Off Debt speedruns (formerly `p2-vod-seeds`).

Every seed reader for Pikmin 2 speedrun videos lives here: each recovers the RNG seed, and so the exact
CaveGen layout, from something the game draws with its RNG. Game mechanics (the GC/Wii and Switch RNGs,
cave generation, judges, the layout viewer) come from [CaveGen3](https://github.com/JHawk4/CaveGen3); this
repository reads videos and builds the report site.

## Readers

**Story mode: falling letters.** On each sublevel entry screen the cave name's letters fall with starting
speeds drawn from the RNG. The reader finds those screens, recognizes the cave name, tracks every letter's
fall, fits its starting speed and finds the RNG state that produces those speeds; the layout seed follows.
Works offline on recorded VODs.
- Design and results: [story-plan.md](docs/story-plan.md), [story-evaluation.md](docs/story-evaluation.md)
  (Pay Off Debt), [story-evaluation-at.md](docs/story-evaluation-at.md) (All Treasures).
- The RNG chain between sublevels, treasures from the treasure panel, Japanese runs:
  [jp-all-treasures.md](docs/jp-all-treasures.md).
- Wii and Wii U VC runs (titles cut to black, route rescue): [wii-story.md](docs/wii-story.md).
- Switch (Pikmin 2 HD), a different RNG (musl's 64-bit LCG): [switch-rng.md](docs/switch-rng.md).
- The Gecko code that replays a run's layouts: [gecko-code.md](docs/gecko-code.md).
- Egg drops (can a runner steer an egg to Mitites?): [egg-mitites.md](docs/egg-mitites.md).

**Challenge Mode.** Challenge Mode has no entry-screen letters, so its seed comes from three other places:
- the results-screen score roll (digit draws) and the stage-select Pikmin dive:
  [challenge-mode-seeds.md](docs/challenge-mode-seeds.md); on Wii captures, where each frame blends two game
  frames: [wii-seeds.md](docs/wii-seeds.md);
- the layout seen in the video, matched against CaveGen3 layouts (the video side of the layout matcher, and
  the seed hunt's validator and finder tools): [layout-matcher.md](docs/layout-matcher.md),
  [docs/validator](docs/validator/README.md), [docs/ch_hunt](docs/ch_hunt/README.md).

**Live: `p2live`.** A Rust port of the story-mode reader that runs while a runner plays (camera or OBS
Virtual Camera, with a GUI and an OBS Browser Source). It uses the `cavegen3` crate from CaveGen3 via git.
[realtime-obs.md](docs/realtime-obs.md), [p2live/README.md](p2live/README.md),
[p2live/app/README.md](p2live/app/README.md).

**The ledger site.** Built from the story-mode results: layout luck, time saved and pokos per run
(see Use and Published site below).

## Layout

- `p2seeds/`: the Python package, organised by approach (`p2seeds/src/p2seeds/`):
  - core: `rng.py` (GC and Switch generators), `caves.py`, the CaveGen / CaveGen3 bridges (`cavegen.py`,
    `cg3.py`, `views.py`), `video.py`, `feed.py` and the command line (`cli.py`);
  - `story/`: the falling-letters reader (`events`, `calibrate`, `track`, `fit`, `search`, `lattice`,
    `analyze`, `chain`, `redo`, `route_rescue`, `treasures`, `report`, `details`, `live`, ...);
  - `challenge/`: the score-roll reader (`results.py`) and the Pikmin dive reader (`dive.py`,
    `dive_detect.py`, `dive_rgb.py`);
  - `ledger/`: the report site (`site`, `run_page`, `judge_report`, `judge_page`, `judge2`, `luck`,
    `gecko`, `charts`, `theme`, `i18n`, `ja_table`).

  Old flat module names (`p2seeds.chain`, `p2seeds.challenge_dive`, ...) still import, as the same module
  objects (`ALIASES` in `p2seeds/__init__.py`). `p2seeds/cg3/` is the small Rust bridge to CaveGen3 (judge
  scores, treasure lists, the layout matcher's `layoutmatch` and `itemscan`).
- `p2live/`: the Rust live reader (`p2live/app/`: the GUI app).
- `judge2/`: the refit Pay Off Debt judge (research scripts, logs and the `judge2` crate).
- `srcom_videos/`: reusable, game-agnostic library: speedrun.com leaderboards and
  small video downloads (≤480p, ≤30 fps, no audio).
- `docs/`: one report per topic (above), with its one-off research scripts in a folder of the same topic
  (`docs/challenge_dive/`, `docs/layout_matcher/`, `docs/hunt/`, `docs/switch/`, `docs/wii/`,
  `docs/realtime/`, ...).
- `vendor/CaveGen/`: fresh clone of https://github.com/JHawk4/CaveGen (not committed).
- `data/`: videos, caches and outputs (not committed).

## Setup

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -e srcom_videos -e p2seeds pytest
git clone https://github.com/JHawk4/CaveGen.git vendor/CaveGen
```

Java (JDK 8+) is needed to regenerate the test reference data, and as the fallback below.
Node is used by yt-dlp to download from YouTube.

Judge scores and treasure lists come from [CaveGen3](https://github.com/JHawk4/CaveGen3) when it is
checked out next to this project (`../cavegen3`) and the bridge is built (Rust); otherwise from Java CaveGen.
Both give identical scores; CaveGen3 is about 100x faster.

Layout pictures and the camera views are drawn by CaveGen3's command line (the same map as its web
page) when `data/build/cavegen3/cavegen3.exe` exists (or `P2SEEDS_CAVEGEN3` points at it); Japanese-region
runs and a missing program fall back to Java CaveGen. `p2seeds render --redraw OUT_DIR` draws a run's
layouts again.

```bash
cargo build --release --manifest-path p2seeds/cg3/Cargo.toml --target-dir data/build/cg3
cargo build --release --manifest-path ../cavegen3/Cargo.toml -p cavegen3-cli   # then copy target/release/cavegen3.exe to data/build/cavegen3/
```

## Use

```bash
# download the top 5 Pay Off Debt (GameCube) runs
.venv/Scripts/python -m srcom_videos download --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=GC" --top 5

# analyze everything in the manifest -> data/output/<run>/report.html, seeds.csv, seeds.json
.venv/Scripts/python -m p2seeds run

# or one file
.venv/Scripts/python -m p2seeds analyze data/videos/some_run.mp4 --url https://www.youtube.com/watch?v=...

# Switch (Pikmin 2 HD) runs use a different RNG (musl's 64-bit LCG, docs/switch-rng.md). `run` picks
# it from the platform. Layouts, judge and treasures need CaveGen3 (cavegen3.exe and p2seeds/cg3)
# built from a CaveGen3 with `--rng switch`; Java CaveGen has only the GC generator.
.venv/Scripts/python -m p2seeds analyze data/videos/some_switch_run.mp4 --rng switch

# score each recovered layout with CaveGen's judge -> data/output/<run>/judge.html, judge.json
.venv/Scripts/python -m p2seeds judge data/output/01_JackDraz_mewq470m --kind pod
```

```bash
# treasures and pokos per sublevel, from the treasure panel in the video (run before `site`)
.venv/Scripts/python -m p2seeds treasures data/output/01_JackDraz_mewq470m
```

```bash
# detection page per run -> data/output/<run>/report.html: tracking pictures, the comedown and landing
# views from the video, and the layout with both views outlined (drawn by CaveGen3's command line,
# from $P2SEEDS_CAVEGEN3 or data/build/cavegen3/cavegen3.exe)
.venv/Scripts/python -m p2seeds details data/output/01_JackDraz_mewq470m

# after improving the detector: re-run a finished run's sublevels that are not high confidence,
# keeping new high seeds that chain with a neighbour (then judge, treasures and details again)
.venv/Scripts/python -m p2seeds redo data/output/01_JackDraz_mewq470m
```

```bash
# the site over every judged run -> data/output/index.html (runs and their layout luck), layouts.html and
# detection.html (pick a run), timesave.html (every run's time per sublevel, raw or beyond the layout),
# pokos.html, accuracy.html (does the judge predict real times), seeds.html (RNG-order check); also
# refreshes each run's judge.html (`ledger/run_page.py`) and report.html
.venv/Scripts/python -m p2seeds site
```

Layout luck comes from **judge2** (`judge2/`, CaveGen's Pay Off Debt judge refit on these runs' real times;
also in CaveGen3 as the `judge2` judge). Each sublevel's luck is its score against the median of 1000
random layouts; a run's luck percentile compares its total with 20,000 simulated runs that each draw one
random layout of the same sublevels (`ledger/luck.py`).

`judge.html` shows every layout render, its luck, how random layouts of that sublevel are spread (a
violin per sublevel), and what the runner did against the median run, net of pokos and of the layout: PBs drew lucky layouts more often than chance, so the judge's difference between each layout and the median run's is taken out.

## Published site

The report site is at https://jhawk4.github.io/pikmin2-layout-ledger/. To update it after `p2seeds site`:

```bash
.venv/Scripts/python -m p2seeds publish
```

This copies the landing page and each run's pages and layout images into `data/pages` and pushes them to the
`gh-pages` branch as a single commit that replaces the previous one, so the history doesn't grow with each rebuild.

### Japanese

Every page has an English/日本語 switch in its header, like CaveGen3's. The pages are written in English once;
`i18n.js` at the site root (written by `site` and `publish`) swaps each piece of English it knows for Japanese
in the browser, including chart tooltips and text the pages' scripts add later. The choice is remembered
(`?lang=ja` / `?lang=en` in a link also sets it), and browsers set to Japanese get Japanese first. Numbers,
seeds, cave codes and runners' names fill placeholders, and treasure and cave names become the game's Japanese
names. The Japanese is in `p2seeds/src/p2seeds/ledger/ja_table.py` (see `ledger/i18n.py` for how it is matched). After
changing a page's English, list what the table lacks with:

```bash
.venv/Scripts/python -m p2seeds i18n data/pages
```

## How a seed is found

Each falling letter is tracked down its column by template matching (`story/track.py`). Some captures blend
two game frames into each video frame, so a falling letter shows twice; the detector tries both a
two-peak tracker and, when the copies overlap, a glyph-pair template matched at every separation.
Each falling letter's starting velocity is fitted from its track, then the seed comes from a lattice
search (`story/lattice.py`): the RNG is affine, so the measured letters, relative to the best-measured one,
bound a lattice point in a box. LLL reduction and enumeration find every seed that fits in milliseconds,
from any subset of letters. Linking (`story/chain.py`) then confirms seeds against their neighbors: only seeds
that agree with another independently found seed anchor the searches near them, and anything filled in
must sit in RNG order between them. Seed distances use CaveGen's O(log n) `nth_inv` (`rng.index`).

## Tests

```bash
.venv/Scripts/python -m pytest srcom_videos/tests p2seeds/tests
cargo test --manifest-path p2live/Cargo.toml
```

`test_rng_parity.py` checks both generators in `rng.py` against fixed sequences from CaveGen3, so the two
cannot drift apart.
