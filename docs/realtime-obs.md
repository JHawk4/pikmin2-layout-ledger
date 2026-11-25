# Live seeds: could the detector run while a runner plays?

**Verdict: yes.** The seed search is not the problem: it already takes milliseconds (the lattice
search replaced the 2^31 scan). A proof of concept that reads frames as a stream, with no look-ahead,
finds the same seeds as the offline pipeline. It runs at real speed on 30 fps and simulated 60 fps
input, with the seed ready **about 5–9 s after the letters land**. That is around when the ship has
landed and the runner has control. Most of that time is the cave-name recognition and plain Python
overhead, and both can be cut. A budget of **about 1–2 s after landing**, before the title screen
fades, looks reachable without a native port or a GPU.

Measured on this machine, an i7-8565U laptop (4 cores). Other jobs had the CPU at **100% the whole
time**, so every number here is pessimistic. Expect them to be 2–3x faster on an idle desktop.

## Priorities (from the user)

CaveGen's old real-time setup worked fairly well; its problem was setup pain. In order:

1. **A standalone executable** with minimal dependencies, minimal setup and a solid, intuitive GUI.
2. **Speed:** layouts on screen sooner.
3. **Robustness** of the detection.

## Plan

One Rust program: no Python, no Java and no OBS plugin. It contains the ported detector, the
CaveGen3 crate for layouts, camera input, a GUI (egui, a single binary) and a small web server for an
OBS Browser Source.

**Setup wizard**, about a minute, with no config file to edit:

1. **Pick the input:** cameras are listed, with "OBS Virtual Camera" preselected. A capture card
   directly (when OBS isn't using it) and a video file (for testing) are the other choices.
2. **Crop:** a live frame with the game picture found automatically from motion; drag the handles to
   adjust.
3. **Category and region,** with the language detected automatically.
4. **Live check:** "enter any cave". The wizard shows when it sees the entry screen and the seed it
   found.

There is no letter calibration: the name's scale and position are fitted on every screen.

Settings are saved as named profiles (input, crop, category, region), so later sessions start
straight in. The wizard only reruns when the profile's camera or crop no longer matches.

**Modes** (those of CaveGen's `seed manip <mode>` GUI, `Manip.java`):

| mode | category | what it reads | what it shows |
|---|---|---|---|
| `pod` | story, Pay Off Debt | falling letters on each entry screen | the layout, judged with the pod judge (skippable treasures not highlighted) |
| `at` | story, All Treasures | the same | the layout with the AT judge |
| `attk` | challenge mode, single levels | the score digits on the results screen (purple), the level-enter screen | the RNG state, then which levels and frames would give a top-ranked layout, with the wait for each |
| `key`, `cmat`, `700k` | challenge-mode full-game runs ("CMAL manip") | the same digits | the next level to pick and when, from a precomputed times table (`seed timestable`, ~2 days to build) weighing wait, scroll time, split variance and layout luck |

Helpers around these: `titleloop` (advance a last-known seed by title-screen loops), `timer`
(frame window to enter a challenge level for a target seed), and CaveViewer to inspect a layout.
The new app should cover all of these modes, with story mode (pod/at) first.

**Main window:**

- the current cave and sublevel, its seed and confidence, and the layout, drawn large;
- this run's sublevels so far;
- "copy Browser Source URL" and "new run" (which resets the chain);
- an optional view of the tracked letters, to check what it measured.

**Language and performance.** The latency is set mostly by waiting for frames (the ~1.7 s fall)
and by the algorithm: cached name scale, a shorter tail, keeping CaveGen3 loaded. It is not set by
the language; Python with those fixes would also land near 1.5 s. Rust still wins on the things
the user ranked first:

- one small exe with no runtime, against a ~150 MB PyInstaller bundle that antivirus often flags;
- CaveGen3 linked in directly;
- real threads with no GIL stalls in the capture loop.

The detector should avoid OpenCV in Rust, a heavy native build. It only needs normalized
cross-correlation of small glyphs over narrow strips, which is easy to write and vectorize. The
fit is a small least-squares problem. Camera input comes from Media Foundation on Windows and
AVFoundation on macOS (e.g. the `nokhwa` crate).

For the GUI, Tauri (a Rust core with an HTML interface, using the system WebView, still one small
exe) is a good fit: the Browser Source overlay is a web page anyway, so the two share code. egui
(drawn by Rust itself) is the simpler fallback.

**Milestones:**

1. **Detector port.** A Rust library plus a command line over video files. Done when its seeds equal
   the Python seeds on every run in `data/output` (about 1,500 entries).
   **Done (`p2live/`):**
   - 1,907 entries in 33 runs, including the Japanese `output_at` runs.
   - Every seed, confidence and sublevel equals Python's per-entry analysis.
   - 1,681 entries are also equal to the final `seeds.json`. The other 226 differ only through
     the cross-entry chain pass and the sublevel-sequence fill-in, which are not ported yet.
   - Details are in `p2live/README.md`.
2. **Live loop.** Frame input, a ring buffer and workers, with the section 2 speed-ups. Target: seed
   ready less than 1.5 s after the letters land. Tested by replaying VODs at real speed with
   virtual-camera-like pacing (repeats and drops).
   **Done (`p2live/src/live.rs`, `p2live replay`):**
   - **Speed:** in simulated replays of five whole runs, the first answer is ready a median of
     0.9–1.1 s after the screen settles (p90 1.2–4.1 s; the slow tail is hard, blurry falls).
   - **Accuracy:** no wrong high-confidence seed.
   - **Real time at 30 fps with 3% stutter (wr17, 20 min):** 12/12 seeds; median 1.3 s, max 1.9 s.
   - **Real time at 60 fps with 3% stutter (wr29, 10 min):** 8/8 seeds. It was 3.6 s median, but
     the CPU was at 100% from other jobs and the capture thread fell behind. Time it again on an
     idle machine.
   - Details are in `p2live/README.md`.
3. **GUI and Browser Source,** settings saved next to the exe.
   **Built (`p2live/app/`), not yet tried by a person:**
   - **Camera input:** a DirectShow reader, so the OBS Virtual Camera is listed.
   - **Setup:** a four-step wizard. The game picture is found automatically, within a few pixels
     on 9 runs' stream layouts.
   - **Settings:** profiles saved next to the exe.
   - **Layouts:** drawn by CaveGen3 in under 0.5 s.
   - **Browser Source:** an overlay page on 127.0.0.1.
   - **The GUI is egui, not Tauri.** One binary with no Node or WebView build. The overlay is a
     plain page the app serves.
   - **Headless test on a wr17 clip:** HoB 2–4 equal to offline, ready 0.6–1.0 s after the screen
     settled.
   - **Challenge Mode modes (attk, key, cmat, 700k):** added (`p2live/src/challenge.rs`,
     `p2live/app/src/manip.rs`).
     - **Roll reader:** a Rust port of the score-roll reader. It equals the Python reader on all
       60 screens of two CMAL runs.
     - **Planning:** CaveGen's manip planning and A-press timing, synced to the captured frames.
   - **Still to do:** frames from a running OBS Virtual Camera.
4. **Packaging.** A Windows exe first, then macOS. One test with real OBS and its virtual camera
   (needs OBS installed on the dev machine).

## 0. Prior art: CaveGen's real-time setup

CaveGen already has a live setup (readme "REAL TIME SEED DETECTION", `continuous.py`, `Manip.java`,
`Letters.java`). It works like this:

- **Input:** the OBS virtual camera.
- **Detection:** `continuous.py` finds story entry screens by brightness, and records the lowest lit
  row of each letter's column in the top ~15% of the screen over 48 frames.
- **Search and display:** Java `Manip`/`Letters` search for the seed (near an anchor or the previous
  seed) and show the layout in a Java window.

What this project adds on top of it:

| | CaveGen RTA | this detector |
|---|---|---|
| cave name | not read: taken from an expected cave order, stepped with `[` `]` and Shift-K | recognized on screen (any order, both languages) |
| calibration | manual: record a video, save frames, tune crop and `letters_x/yscale/offset` and `x_scrunch_limit` by trial and error | name scale and position fitted on every screen; only the crop is needed |
| letter measurement | one lit-row edge per frame, top band only | sub-pixel template tracking over the whole fall, fitted with the fall physics (phase, scale, floor) |
| search | Java, near an anchor or a precomputed table | lattice search from any 3+ letters, no anchor needed; chaining as a fallback |
| bad captures | none | blended / uneven / doubled frames handled |
| install | git, Python + numpy + cv2, Java, OBS virtual-cam plugin, config editing | the goal: one program, or one OBS plugin |

So the architecture recommended below is the same one, rebuilt on a detector that needs no manual
calibration or expected cave order.

## 1. Where the time goes

### Per entry screen, clean captures

`p2seeds/scripts/bench_stages.py` times each stage, best of 3. Four entries from JackDraz 01
(465×360 feed) and kobachi 03 (647×436 feed):

| stage | time | notes |
|---|---|---|
| entry-screen check (every frame) | **2–7 ms/frame** | fine at 60 fps if the frame is first scaled down to ≤480 lines |
| repeat-frame timing (`game_times`) | 0.4–0.8 s | |
| cave name (`calibrate`), all 28 names | **3.6–13 s** | the largest stage: ~550 `matchTemplate` calls over scales × caves |
| cave name, only the 9 Pay Off Debt names | 2.0–6.8 s | what a runner's category allows |
| letter tracking | 1.8–2.4 s | every letter × every frame of a 150-frame clip |
| velocity fit (scipy) | 0.4–0.85 s | |
| seed search (lattice) | **0.05–0.12 s** | already fast: no Rust port, chaining or GPU needed for it |
| layout image (CaveGen3 CLI) | 0.5–4 s, usually 1–1.5 s | includes starting the process |

### Whole `analyze_event`, 16 entries from 4 runs

From `p2seeds/scripts/profile_realtime.py`, which runs the full offline analysis for each entry:

- **15 of the 16 seeds match** the recorded offline seeds.
- **Clean captures** (JackDraz 01, kobachi 03, wr29 EC/SH/FC, Curtis CoC): 33–263 s on the loaded
  CPU, 80–90% of it in `calibrate`. Offline it is called 5–10 times per window, once per dark text
  screen.
- **Hard captures** (Curtis 08 with uneven frame pacing, wr29 GK with blended frames): 100–1650 s.
  When the first try is not high confidence, the variant loop runs (weak matches, wall clock,
  blended/pair tracking, first stretch). Each variant then tries every ±1-frame timing step
  (`_fit_with_step`), which adds up to **1000–2500 scipy fits**. This is the real worst-case
  bottleneck. Live, it needs a time budget, with chaining as the fallback (section 2).

### Timeline of one entry screen

Measured on 18 entries from 2 runs, plus the letter model:

- The letters fall for about **1.7 s**: each takes ~20–23 game frames to land, and they start
  staggered over 1 s.
- The name then sits settled for **1.3–3.3 s**, typically 2–2.5 s, before the fade-out.
- The game picture is back **0–3 s after the fade-out**. The ship's descent comes after that (not
  measured here).

So the runner sees gameplay roughly **2.5–5 s after the letters land**, and has control a few
seconds after that.

## 2. Latency budget

The PoC (section 4) runs at real speed. It recognizes only Pay Off Debt names and uses 3 worker
threads:

| capture | entries | seeds equal to offline | ready after the letters landed | split |
|---|---|---|---|---|
| 30 fps | 6 (HoB 1–5, one twice) | 6/6 | 8.6–19 s (1 worker) | name 1.5–3.5 s, analysis 1.6–3.3 s, render 0.7–3.8 s; the rest was queueing behind non-cave text screens |
| 60 fps (every frame doubled) | 5 | 5/5 | **6.2–9.0 s** (3 workers, incl. render) | name 2.3–3.8 s, analysis 1.5–2.3 s, render 0.5–1.4 s |
| 60 fps, one entry | 1 | 1/1 | **4.7 s** (no render) | |

- The capture loop never fell more than 0.6–1 s behind real time.
- The 60 fps case works because `game_times` drops the repeated frames. The GameCube game updates
  the letters at 30 fps.

### Making it ready before the fade-out (≈2 s after landing)

1. **Cave name, ~2–4 s → ~0.1 s.** Within one stream the glyph scale never changes. After the first
   entry, keep each cave's fitted (sx, sy) and match only that one scale per cave: 9 matches instead
   of ~300. A coarse pass at half resolution can rank the caves first. This is the biggest win.
2. **Stop waiting 40 frames after landing (`FALL_TAIL`, 1.3 s).** The settled run starts when the
   last letter has dropped below the top band. Only the bounces come later, and the fit cuts those
   off. ~10 frames is enough, and it saves ~1 s.
3. **Track only the fall.** Skip the dark lead frames, and stop each letter once it has settled. The
   letter loops can run in parallel (cv2 releases the GIL). This saves ~1–1.5 s.
4. **Give the fallbacks a time budget (~1 s), then chain.** Each sublevel's letter seed sits a bounded
   number of RNG steps after the previous sublevel's layout seed. `search_near` over that window
   settles a seed from 2–3 letters in well under a second. The PoC already does this for
   medium/low fits. Live, this replaces the expensive variant × timing-step loop. Hard captures
   still have to be checked, because the chain breaks after a reset or a death.
5. **Render in a long-running CaveGen3 process** (the `cg3` bridge is already one) instead of starting
   the CLI each time: 1–1.5 s → ~0.2 s.

With 1–3 and 5 done, a clean entry is roughly 0.3 s waiting for frames, 0.1 s name, ~0.5 s
track + fit, <0.1 s search and ~0.2 s render. That is **≈1–1.5 s after landing**, while the name is
still on screen.

A Rust/C++ port of the search would gain nothing, because the search is already 0.1 s. A GPU is
unnecessary. A full native port only matters for packaging (section 3), not for speed.

## 3. Integration options

What the input needs:

- **The game picture alone, cropped**: a 4:3 or 16:9 region the runner sets once, or an OBS source
  that is just the game capture.
- **At least ~360 lines.** Scale down to ≤480 lines first, because the detector is tuned for
  `s = H/480` and per-frame cost grows with pixels.
- **Every frame, evenly paced, for the ~3 s of the fall.** Dropped frames are the main failure mode,
  so frame-accurate capture matters more than resolution.
- **60 fps progressive is fine.** 480i that OBS deinterlaces by blending gives the "blended" frames
  the pipeline already handles. A Retro-Tink / OSSC line-doubled feed is the cleanest input.

| option | frames | install for runners | Windows / macOS | showing the layout | verdict |
|---|---|---|---|---|---|
| **Native OBS filter plugin** (C/C++ or Rust over libobs), whole pipeline inside | exact, every frame (texrender + stage-surface readback) | install a plugin; a build per OS and OBS major version; macOS signing | both, but each needs its own build and CI | draw in OBS (a source) | best final experience; **4–8 weeks** to port tracking, fit (Ceres/Eigen) and lattice, and to bundle OpenCV |
| **OBS Python/Lua script** | no practical pixel access from scripts (Lua has no numpy; Python needs the user's own matching Python install) | painful | fragile | text/image source | **no** |
| **obs-websocket `GetSourceScreenshot`** polling | not frame-accurate: drops and jitters frames | nothing extra (built into OBS 28+) | both | browser source | **no** for the fall; fine for control and status |
| **Standalone app reading the OBS Virtual Camera** (OBS 30+ can output a single source) | every frame, steady | one download (a PyInstaller exe, ~150 MB with numpy/scipy/OpenCV plus the CaveGen3 exe); start the virtual camera on the game source | both (DirectShow / AVFoundation) | small local web server; an OBS **Browser Source** at `http://localhost:PORT` shows the layout, seed and sublevel, updating itself | **recommended first** |
| Standalone app + **NDI** | every frame | NDI plugin + runtime | both | browser source | a fallback when the virtual camera is in use |
| Standalone app + a tiny **"frame tap" OBS filter** (C, ~300 lines: scale to 480p gray, write to shared memory) | exact | plugin + app | both | browser source | **phase 2**, if the virtual camera is a problem (one virtual cam per OBS, often used for a facecam) |

**Recommendation:** start with the standalone Python app (this PoC grown up). It reads the OBS
Virtual Camera set to output the game source, and shows the layout through a Browser Source. All
the existing analysis code stays in use, and a fix in the offline tool reaches the live one for
free. The app is one download and works on both OSes. If runners want the virtual camera for
something else, add the thin frame-tap filter rather than porting the pipeline.

### Effort estimate

| piece | estimate |
|---|---|
| Live speed-ups 1–5 above, with a time budget and chaining across a reset | 3–5 days |
| App: virtual-camera input, setup screen (pick camera, draw the crop, category/region), local web page for the Browser Source, run log | 1–1.5 weeks |
| Packaging: Windows exe; macOS build including CaveGen3 for arm64/x64 and camera permission | 3–5 days, +1 week for macOS |
| Optional frame-tap OBS filter (Win + mac CI) | 1–2 weeks |
| Full native plugin instead | 4–8 weeks |

## 4. Proof of concept

```powershell
# from the main checkout (videos and CaveGen3 live in data/)
.venv\Scripts\python -m p2seeds.live data\videos\01_JackDraz_mewq470m.mp4 --seeds data\output\01_JackDraz_mewq470m\seeds.json --start 900 --duration 300 --caves pod --render data\scratch\live
```

`p2seeds/src/p2seeds/live.py` plays a video at real speed (`--speed`) and hands each frame to
`Live.push`, the way a capture callback would. `--double` simulates a 60 fps capture.

The capture loop only runs the per-frame entry-screen check and keeps a 400-frame ring buffer. When
an entry-screen run has lasted `FALL_TAIL` frames, it copies the buffer to a worker thread. The
worker then:

1. reads the cave name on the newest frames;
2. runs the offline `_analyze_entry` (tracking, fit, lattice, the same fallbacks);
3. chains from the previous layout seed when the fit is not high confidence;
4. renders the layout with CaveGen3.

It prints each sublevel's seed with its timing. With `--seeds` it also compares the result against
the offline seeds.

Sample output (60 fps, real speed, loaded CPU):

```
[0:10.63] HoB-1  seed 0x2730DF31 -> layout 0x4A905CAB  (high)  ready 7.8s after the letters landed (queued +0.7s, name 3.84s, analysis 2.27s, render 1.09s)
[1:06.87] HoB-2  seed 0x44D5BBF1 -> layout 0x23A06B6B  (high)  ready 9.0s after the letters landed (queued +0.6s, name 3.21s, analysis 2.21s, render 1.08s)
...
9000 frames (300 s of video) in 300 s; entry-screen check 3.71 ms/frame; capture loop fell behind by at most 0.64 s
```

Things the PoC does not do yet:

- the speed-ups in section 2;
- a time budget on the fallbacks: one flicker-split duplicate spent 69 s in them before the dedup
  was added;
- finding the feed crop itself: it takes `--feed` or the run's `seeds.json`, and a live setup would
  have the runner draw it once;
- Japanese runs (`--caves pod-ja` exists but is untested live);
- handling a reset or death that breaks the chain.

## 5. speedrun.com rules

Settled: runs that use a live layout tool like this have their own category, so the runner may see
the layout. Optionally hiding it from the stream (a projector window only the runner sees) is a
display choice, not a rules requirement.
