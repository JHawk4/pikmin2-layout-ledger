# p2-vod-seeds

Recover the RNG seed, and so the exact CaveGen layout, of every story-mode
sublevel in a Pikmin 2 speedrun video. Works offline on recorded VODs only.

How it works: on each sublevel entry screen the cave name's letters fall with
starting speeds drawn from the game's RNG. The tool finds those screens,
recognizes the cave name, tracks every letter's fall, fits its starting speed,
and searches all 2^31 RNG states for the one that produces those speeds. The
layout seed follows from that (see `PLAN.md` for the full design).

## Layout

- `srcom_videos/`: reusable, game-agnostic library: speedrun.com leaderboards and
  small video downloads (≤480p, ≤30 fps, no audio).
- `p2seeds/`: the Pikmin 2 pipeline (feed detection, entry screens, letter tracking,
  seed search, sublevel labels, CaveGen rendering, HTML report).
- `vendor/CaveGen/`: fresh clone of https://github.com/JHawk4/CaveGen (not committed).
- `data/`: videos, caches and outputs (not committed).

## Setup

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -e srcom_videos -e p2seeds pytest
git clone https://github.com/JHawk4/CaveGen.git vendor/CaveGen
```

Java (JDK 8+) is needed to render layouts and to regenerate the test reference data.
Node is used by yt-dlp to download from YouTube.

Judge scores and treasure lists come from [CaveGen3](https://github.com/JHawk4/CaveGen3) when it is
checked out next to this project (`../cavegen3`) and the bridge is built (Rust); otherwise from Java CaveGen.
Both give identical scores; CaveGen3 is about 100x faster.

```bash
cargo build --release --manifest-path p2seeds/cg3/Cargo.toml --target-dir data/build/cg3
```

## Use

```bash
# download the top 5 Pay Off Debt (GameCube) runs
.venv/Scripts/python -m srcom_videos download --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=GC" --top 5

# analyze everything in the manifest -> data/output/<run>/report.html, seeds.csv, seeds.json
.venv/Scripts/python -m p2seeds run

# or one file
.venv/Scripts/python -m p2seeds analyze data/videos/some_run.mp4 --url https://www.youtube.com/watch?v=...

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
# landing page over every judged run -> data/output/index.html (and refreshes each run's judge.html)
.venv/Scripts/python -m p2seeds site
```

The landing page also shows where each seed falls in the RNG sequence (it should rise steadily through a
run) and checks the judge against real sublevel times measured from the videos.

`judge.html` embeds every layout render. For each sublevel it shows CaveGen's estimated clear time
and how that compares with 1000 random layouts. Fixed floors, where every seed scores the same, are marked.

## Published site

The report site is at https://jhawk4.github.io/p2-vod-seeds/. To update it after `p2seeds site`:

```bash
.venv/Scripts/python -m p2seeds publish
```

This copies the landing page and each run's pages and layout images into `data/pages` and pushes them to the
`gh-pages` branch as a single commit that replaces the previous one, so the history doesn't grow with each rebuild.

## How a seed is found

Each falling letter's starting velocity is fitted from its track, then the seed comes from a lattice
search (`lattice.py`): the RNG is affine, so the measured letters, relative to the best-measured one,
bound a lattice point in a box. LLL reduction and enumeration find every seed that fits in milliseconds,
from any subset of letters. Linking (`chain.py`) then confirms seeds against their neighbors: only seeds
that agree with another independently found seed anchor the searches near them, and anything filled in
must sit in RNG order between them. Seed distances use CaveGen's O(log n) `nth_inv` (`rng.index`).

## Tests

```bash
.venv/Scripts/python -m pytest srcom_videos/tests p2seeds/tests
```
