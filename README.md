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
- `vendor/CaveGen/`: fresh clone of https://github.com/JHaack4/CaveGen (not committed).
- `data/`: videos, caches and outputs (not committed).

## Setup

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -e srcom_videos -e p2seeds pytest
git clone https://github.com/JHaack4/CaveGen.git vendor/CaveGen
```

Java (JDK 8+) is needed to render layouts and to regenerate the test reference data.
Node is used by yt-dlp to download from YouTube.

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

`judge.html` embeds every layout render. For each sublevel it shows CaveGen's estimated clear time
and how that compares with 1000 random layouts. Fixed floors, where every seed scores the same, are marked.

## Tests

```bash
.venv/Scripts/python -m pytest srcom_videos/tests p2seeds/tests
```
