# p2-vod-seeds: Spec

Offline tool that takes speedrun VODs of Pikmin 2 **story mode** and outputs the RNG seed (and resulting CaveGen layout) for every sublevel entered.

Status: **spec only, no code written.**

---

## 1. Goals and non-goals

**Goals**
- Given a speedrun.com game/category, fetch the top N runs and their video links, download the videos small (≤480p, ≤30 fps, video only).
- For each video, find every sublevel entry, identify the cave and sublevel, recover the layout seed, and render the CaveGen layout.
- Produce a per-run report (JSON + CSV + HTML) with timestamps, links, seeds, confidence and layout images.
- The speedrun.com and download part is a **separate, reusable sub-library** with no Pikmin-specific code.

**Non-goals (for now)**
- Anything real-time. The tool only reads recorded video. (Real-time detection and manipulation are banned for runs.)
- Challenge mode (results-screen digits). Kept as a later extension.
- PAL and Japanese text. These are planned as extensions, not v1.
- Modifying `C:\Users\Jordan\Desktop\Hack\CaveGen`. That folder is read-only for this project; we use a fresh clone from GitHub (see §4).

---

## 2. What the existing detector does (verified from CaveGen source)

These facts drive the design, so I'm recording exactly what the code does.

| Fact | Where |
|---|---|
| RNG is an LCG: `s = s*0x41C64E6D + 0x3039 (mod 2^32)`, output `rand = (s >> 16) & 0x7FFF` | `Seed.java:615-660` |
| On a sublevel entry screen, each **character of the cave name (spaces included)** consumes one `rand()`. Its starting velocity is `v = rand * 5 / 32768`, so `v ∈ [0, 5)` | `Seed.seed_to_vel_vector` |
| Letter height model (480-unit screen space): `pos(f) = 200 + (v − 0.5)·f − f²/2`, with the top of the screen at about 164.65 units | `Letters.java:707-717` |
| Letter *i* of *n* starts after a delay of `i/n` seconds, quantized to 1/30 s frames (the game animates at 30 fps) | `Letters.java:165-175` |
| **Layout seed = letter seed advanced by `n_chars` rand calls** | `Manip.java:397` |
| The search for a seed has three modes: (1) scan forward from the last known seed, (2) scan from an "anchor" seed, (3) **LLL lattice search over the full seed space**, which needs ≥ 7 readable characters and the first 4 non-space. It uses at most 10 characters and has an 8 s timeout | `Letters.java:380-430`, `Seed.vs_array_to_seed` |
| Calibration today is manual, per OBS layout: `letters_xscale/yscale/xoffset/yoffset`, `x_scrunch_limit` (long names get horizontally squeezed), `space_mult` | `config.txt`, `continuous.py:343-440` |
| The animation shows only the **cave name, not the sublevel number**. The live tool relies on the user pressing `[`/`]` to say which sublevel is next | `Manip.java:377-382` |
| Letter templates for all English letters (plus the JP glyphs) already exist | `files/templates/letters/*.png` |

**Implication:** going from a velocity vector to a seed already works. The new work is everything upstream of it: finding the screens, calibrating automatically, tracking the letters, and labeling the sublevel.

Mode (3), the full-space lattice search, is what makes offline work possible. A VOD gives us no "last known seed", but every English story cave name has at least 12 characters, so the 7-character minimum is normally met.

---

## 3. Data sources (verified against speedrun.com API v1)

- Game: **Pikmin 2**, id `pdv9zv1w`
- Story categories:
  - Pay Off Debt `zd3x7ndn`, console variable `yn23w3jl` (GC `qyz7vv41`, Wii `ln8e440l`, Switch `10v6oowl`)
  - All Treasures `wdmggxdq`, console variable `6njy5y5n` (GC `qj7266eq`, Wii `lmo2rrj1`, Switch `1w47vvoq`)
  - No Major Exploits `jdrw35xk`, which has a PoD/AT subcategory
- Leaderboard endpoint: `/api/v1/leaderboards/{game}/category/{cat}?top=N&var-{var}={val}&embed=players`
- Current top 5 on GC: all have videos, mostly YouTube (`youtube.com/watch`, `youtu.be` with `?si=` tracking params, `youtube.com/live/...`), plus one Twitch VOD (`twitch.tv/videos/...`). Some Switch runs have **no video**.
- PoD on GC runs about 1.5 h and AT about 3.5 h. AT covers all 14 caves and is the best test set. PoD is shorter and the best first target.

---

## 4. Repository layout

The project home is `C:\Users\Jordan\Desktop\Claude\p2-vod-seeds`. It is created as an empty git repo; the session couldn't move there, so this spec lives in the session folder for now.

```
p2-vod-seeds/
├─ srcom_videos/              # REUSABLE sub-library (no Pikmin code)
│  ├─ pyproject.toml          # its own package metadata and deps
│  ├─ README.md
│  ├─ src/srcom_videos/
│  │  ├─ api.py               # speedrun.com client: rate limit, retries, on-disk cache
│  │  ├─ models.py            # dataclasses: Game, Category, Variable, Run, Player, VideoLink
│  │  ├─ leaderboard.py       # top_runs(game, category, variables, n) -> [Run]
│  │  ├─ links.py             # normalize/classify URLs (YouTube, youtu.be, /live/, Twitch, other)
│  │  ├─ download.py          # yt-dlp wrapper: format policy, resume, manifest, size cap
│  │  ├─ manifest.py          # JSON manifest of runs, links, files, status
│  │  └─ cli.py               # `python -m srcom_videos list|download ...`
│  └─ tests/                  # offline tests using recorded API fixtures
├─ p2seeds/                   # Pikmin-specific pipeline
│  ├─ src/p2seeds/
│  │  ├─ rng.py               # LCG, nth/next/prev seed, seed -> velocity vector
│  │  ├─ lattice.py           # port of the LLL full-space search (+ brute-force fallback)
│  │  ├─ letters_model.py     # physics, delay schedule, name -> character layout
│  │  ├─ templates.py         # compose cave-name templates from CaveGen letter PNGs
│  │  ├─ video.py             # decode, timestamps, duplicate-frame handling
│  │  ├─ events.py            # find fadeouts and entry screens
│  │  ├─ feed.py              # locate the game feed inside the stream layout
│  │  ├─ calibrate.py         # cave-name ID + scale/offset/scrunch fit
│  │  ├─ track.py             # per-letter vertical tracking (sub-pixel)
│  │  ├─ fit.py               # velocities (+ uncertainty) from tracks
│  │  ├─ solve.py             # velocities -> candidate seeds -> layout seed, confidence
│  │  ├─ sublevels.py         # sequence model that assigns sublevel numbers
│  │  ├─ cavegen.py           # call the vendored CaveGen jar to render layouts
│  │  ├─ report.py            # JSON/CSV/HTML output
│  │  └─ cli.py               # `python -m p2seeds analyze <video|manifest>`
│  ├─ tools/synth.py          # synthetic entry-screen generator (testing, §8)
│  └─ tests/
├─ vendor/CaveGen/            # fresh `git clone` of github.com/JHawk4/CaveGen, pinned commit
├─ data/                      # gitignored: videos/, clips/, cache/, output/
└─ PLAN.md
```

**Vendoring CaveGen:** I'll clone fresh from GitHub, pinned to the current `master` (`16c7960`), and **not** copy your local folder. Your local copy is one commit behind GitHub, and its uncommitted edits are challenge-mode digit templates and config, which don't matter for story mode. The clone is gitignored and set up by a script (or a git submodule), and it's built with `javac --release 8`. We use it for (a) letter templates, (b) reference test vectors from `Seed.java`/`Letters.java`, and (c) rendering layouts.

---

## 5. The `srcom_videos` sub-library

Designed to be reused for other games or projects. It knows nothing about Pikmin.

**API client (`api.py`)**
- `GET` only, with a descriptive User-Agent, and a rate limit under speedrun.com's 100 requests/min.
- Retries with backoff on 420/429/5xx.
- On-disk JSON cache with a TTL, so repeated runs make no network calls.
- Resolves game by abbreviation, categories, variables (including subcategory variables), and leaderboards with embedded players.

**Selection (`leaderboard.py`)**
- `top_runs(game="pikmin2", category="Pay Off Debt", variables={"Console (PoD)": "GC"}, n=5)`
- Accepts names or IDs. Returns `Run` objects with place, players, time, date, platform/region, and video links.
- Skips runs without videos but records them.

**Link handling (`links.py`)**
- Strips tracking parameters (`si`) and normalizes `youtu.be/ID`, `youtube.com/live/ID` and `watch?v=ID` to a canonical form.
- Classifies the host: YouTube, Twitch VOD, or other/unsupported.

**Downloading (`download.py`)**, using yt-dlp from Python, not a subprocess:
- **Format policy** (configurable presets `480p` / `240p`):
  - `bv*[height<=480][fps<=30][vcodec^=avc1] / bv*[height<=480][fps<=30] / bv*[height<=480]`
  - **Video only, no audio**, to save space and avoid merging.
  - YouTube normally serves 60 fps uploads at 30 fps for 480p and below, and Twitch offers `480p30`/`360p30`/`160p30`. So in the usual case **no re-encode is needed**.
  - If the only stream available is above 30 fps, re-encode with `ffmpeg -vf fps=30`. ffmpeg comes from the `imageio-ffmpeg` wheel, since there's no system ffmpeg on this machine.
- Resumable downloads. Skip files that already exist. A per-run size cap. Stable filenames: `{category}_{place:02}_{player}_{runid}.mp4`.
- **Manifest** (`manifest.json`): for each run, the speedrun.com metadata, the canonical URL, the chosen format (resolution/fps/codec), file path and size, and status (`ok`, `unavailable`, `private`, `expired`, `no_video`).
- **Clips-only option** (`--keep clips`): after the analyzer finds entry screens, it can cut ±10 s clips with stream copy and delete the full video. This hook is provided by the library and driven by `p2seeds`.

**Disk estimate:** 480p30 video-only is about 0.5–1 Mbps. That's roughly 0.35–0.7 GB per PoD run and 0.8–1.6 GB per AT run, so the top 5 of each comes to about **6–12 GB**. 240p is roughly a third of that. Clips-only mode drops it to around **50 MB per run**.

---

## 6. The `p2seeds` pipeline

Each stage writes its intermediate output to `data/output/<run>/` as JSON, so any stage can be re-run and debugged on its own.

### S1. Decode (`video.py`)
- OpenCV `VideoCapture`. The opencv-python wheel bundles ffmpeg.
- Read actual timestamps rather than assuming a constant frame rate.
- Detect duplicated or dropped frames by frame differencing, and map video frames onto a 30 fps **game-frame timeline**.

### S2. Find entry screens (`events.py`)
- **Coarse pass:** about 2 fps on downscaled grayscale. An entry screen looks like a near-black frame with a bright horizontal text band, right after a fadeout. Fadeouts are frames whose maximum intensity falls below a threshold (same idea as `get_screen_type` in `continuous.py`).
- **Fine pass:** decode every frame within ±3 s of each candidate to get the exact frame where the letters start and settle.
- Output: a list of entry events with frame ranges and timestamps.

### S3. Find the game feed (`feed.py`)
- Pixels that go black during fadeouts belong to the game feed; overlays (webcam, splits, borders) don't. Combine over many fadeouts to get a reliable crop box. Check that its aspect ratio is about 4:3 (GC) or 16:9 (Switch).
- Re-check at each event, in case the layout changes mid-stream.

### S4. Identify the cave and calibrate (`calibrate.py`)
- Build a template image for each of the 14 English cave names from the CaveGen letter PNGs, using the same layout rules as `continuous.py`: `space_mult`, `x_scrunch_limit` for long names, centering.
- On the settled frame (letters at rest), search over cave name × scale × x/y offset × scrunch, maximizing normalized cross-correlation.
- The best match gives **both the cave name and the calibration**, replacing the manual `setup_seed_detect.py` step. Its score becomes a confidence value.
- From that we get each letter's final x-range and rest position.

### S5. Track the letters (`track.py`)
- For each letter, match its template within its column on every frame of the fall. Refine to sub-pixel accuracy with a parabola fit on the correlation peak.
- Mark letters as missing when they are occluded or the match is weak. Missing letters are treated like spaces by the solver.

### S6. Fit velocities (`fit.py`)
- Convert pixels to game units with the calibrated scale (480 units per feed height, top at about 164.65).
- Fit each letter's `v` jointly with one shared **global frame-phase offset**. The phase is needed because decimating 60 fps captures to 30 fps can shift every frame by half a game frame. Use the known delay schedule and a robust (Huber) loss.
- Output `v_i ± σ_i`. The σ values feed the per-letter search tolerances.

### S7. Solve for the seed (`solve.py`, `lattice.py`, `rng.py`)
- **Primary:** a Python port of the LLL lattice search (`vs_array_to_seed`), with the precomputed basis copied from `Seed.java` as data. Fast numpy implementation, with Numba as an option.
- **Fallback:** brute force over all 2^31 starting states, chunked and vectorized. Offline we can afford minutes per event, which removes the "first 4 letters must be readable" restriction.
- Rank candidates by error-weighted residual. **Confidence** is based on (a) the residual of the best candidate and (b) the gap to the second-best.
- `layout_seed = next_seed(letter_seed, n_chars)`.
- **Validation:** the port must reproduce the Java results exactly on reference vectors generated from the vendored Java code.

### S8. Label sublevels (`sublevels.py`)
- Sequence model: a new cave name means sublevel 1, and each later entry with the same name adds 1, capped at that cave's sublevel count from caveinfo.
- Handles leaving and re-entering a cave (starts again at sublevel 1), save-reloads and resets (a repeated sublevel), and gaps where an entry wasn't detected (flagged; a time-gap heuristic estimates what was missed).
- If Phase 0 shows the entry screen also displays the sublevel number, read it directly and use the sequence model only as a cross-check.

### S9. Render layouts (`cavegen.py`)
- Run `java -jar vendor/CaveGen/CaveGen.jar cave <CAVE> <n> -seed 0x<seed> -noprints ...` and store the PNG.

### S10. Report (`report.py`)
- `seeds.json` / `seeds.csv`, one row per entry: run, player, video timestamp, a link that jumps to the timestamp (YouTube `&t=`, Twitch `?t=`), cave, sublevel, letter seed, layout seed, confidence, and flags.
- A static `report.html` with, per entry, a settled-frame thumbnail, the detected track overlay, the seed, and the CaveGen layout image.
- An aggregate page across all analyzed runs.

---

## 7. Tooling and environment

- **Python 3.13** via `py -3.13` and a project venv. In this shell, bare `python` points to 2.7, so always use the venv.
- Python packages needed (none are installed yet for 3.13): `yt-dlp`, `opencv-python`, `numpy`, `imageio-ffmpeg`, `requests`, `pytest`, and optionally `numba`.
- **Java 21** (already installed) to build and run the vendored CaveGen with `--release 8`.
- No system ffmpeg or Tesseract is needed. Cave names are identified by template matching, not OCR.

---

## 8. Testing strategy

1. **Unit tests:** RNG (`nth`, `nth_inv`, next/prev), seed → velocity vector, name → character layout, and URL normalization.
2. **Cross-checks against the Java code:** generate (seed → velocities → expected search result) vectors from the vendored `Seed`/`Letters` and require exact agreement. This also covers the `+n_chars` layout-seed step.
3. **Synthetic entry screens** (`tools/synth.py`): render the letter animation from a known seed using the real templates and the physics model, then degrade it with random scale and offset, a stream-layout border, a webcam box over some letters, 60→30 fps decimation, H.264 compression at 480p and 240p, and noise. This gives **end-to-end tests with known answers and no real video**, and is how we measure accuracy at 480p versus 240p.
4. **Real-video fixtures:** don't commit videos (they're large and not ours). Commit only small derived data: event timestamps and extracted letter tracks as JSON, plus the URL and timestamp to re-download each clip.
5. **Ground truth:** for a sample of real entries, confirm the seed visually: the layout's first room, the hole position and visible treasures should match the footage. Record results in `ground_truth.csv`.
6. **Metrics:** entry-event recall, cave-ID accuracy, seed success rate, **wrong seeds reported with high confidence** (the most important metric; the target is zero), and sublevel-label accuracy.

---

## 9. Phases

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **0. Feasibility spike** | Download 1 top PoD GC run at both 480p and 240p. Hand-pick 3 entry screens. Check frame rate and duplicate frames, letter legibility, and whether the sublevel number is on screen. Run the existing math on hand-extracted tracks. | Recover at least 1 seed that matches the footage. Decide 480p vs 240p. |
| **1. `srcom_videos`** | Package, CLI, manifest, format policy, tests with recorded API fixtures | `download --top 5` for PoD GC fetches all 5 runs within the size budget |
| **2. Core math** | `rng`, `letters_model`, `lattice` + brute-force fallback | Exact agreement with Java reference vectors |
| **3. Synthetic harness** | `synth.py` plus end-to-end tests | ≥ 95% correct seeds on clean synthetic clips at 480p, 0 wrong seeds reported with high confidence |
| **4. Video pipeline** | decode, events, feed, calibrate, track, fit | Every entry detected on the Phase 0 video, cave ID 100% correct |
| **5. Labeling + output** | sublevels, CaveGen rendering, HTML report | Full report for one PoD run |
| **6. Evaluation** | Top 5 PoD GC + top 5 AT GC | Metrics table, a list of failure cases, threshold tuning |
| **7. Extensions** | Wii/Switch (16:9, possible timing differences), NME, JP text, PAL (different frame timing), challenge mode digits, CaveRipper rendering | As needed |

Phase 0 matters most: it tests the one real unknown before we build anything large.

---

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Compression and low resolution blur letter positions | Velocity error goes over the search tolerance, so no seed or a wrong one | Sub-pixel tracking, fitting over many frames, per-letter σ, measuring 480p vs 240p in Phase 0 and 3. **I recommend 480p as the default**: in a stream layout the game feed is often only 60–75% of the frame, and at 240p one pixel would be about 2.7 game units |
| 60→30 fps decimation and dropped frames | Timing offset | Fit a global phase, map to the game-frame timeline by differencing |
| Overlays covering letters | Fewer usable characters | Treat them as missing; the brute-force fallback removes the "first 4 letters" requirement |
| Wrong sublevel labels | A correct seed rendered for the wrong sublevel | Sequence model + caveinfo bounds + flags; read the on-screen number if there is one |
| Several candidate seeds | Ambiguous result | Gap-based confidence; report as ambiguous rather than guess |
| Differences between GC, Wii and Switch | The model may not hold | v1 is **GC NTSC-U only** (filtered with speedrun.com's platform/region fields); other platforms are a later phase |
| Videos go missing (Twitch expiry, privated, deleted) | Fewer runs to analyze | Record the status in the manifest and move on to the next run |
| Disk usage | Several GB | 480p video-only; clips-only mode |
| Community norms | Publishing analyses of other people's runs | Keep reports local or private by default; check with the community before sharing |

---

## 11. Decisions needed before coding

1. **Resolution:** default to 480p (recommended), or 240p? Phase 0 measures both either way.
2. **Keep full videos or clips only after analysis?** I recommend keeping the full video until Phase 6, then switching to clips only.
3. **Scope of the first test set:** top 5 **PoD GC**, then top 5 **AT GC** (recommended), or other categories or consoles?
4. **Seed search:** a Python port (recommended: one language, easier to test) or calling the Java code?
5. **Repo location:** `Desktop\Claude\p2-vod-seeds` (empty git repo already created) and, later, a GitHub repo (now public at JHawk4/pikmin2-layout-ledger)?
