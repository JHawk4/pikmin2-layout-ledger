# p2live-app

Live Pikmin 2 layouts for a runner's stream: the `p2live` seed detector on the OBS Virtual Camera,
with a setup wizard, saved profiles, the layout drawn by CaveGen3, and an OBS Browser Source.
Milestone 3 of `docs/realtime-obs.md`.

```bash
cargo build --release --manifest-path p2live/app/Cargo.toml
p2live/app/target/release/p2live-app.exe            # the window
```

## Using it

1. **In OBS**, click Start Virtual Camera.
   - With Settings › Output type: Source › the game capture, it sends just the game.
   - Otherwise it sends the whole scene, and step 2 finds the game in it.
2. **Run `p2live-app.exe`.** The first time, a four-step setup opens:
   1. **Input.** The OBS Virtual Camera is listed first. A capture card works too, when OBS is
      not using it. A video file (needs ffmpeg) is for trying it out.
   2. **Game picture.** It is found from what moves on screen while you play. Drag the corners to
      adjust.
   3. **Category** (Pay Off Debt, All Treasures or a Challenge Mode category), **console**
      (GameCube/Wii/Wii U or Switch) **and game language** (or detect automatically).
   4. **Check.** Enter any cave; its seed and layout show.
3. **For the stream:**
   - Click **Copy Browser Source URL**: `http://127.0.0.1:8787/`.
   - In OBS, add Sources › + › Browser with that URL.
   - The page is transparent and shows the newest layout with its sublevel and seed. Add
     `?caption=0` to the URL to hide the text, or `?size=N` to set the text size.

The settings are saved next to the exe (`p2live-settings.json`, or `%APPDATA%\p2live` when that
folder is not writable). Later starts go straight to the main view.

- **Profiles** keep the input, the crop, the category and the learned name scale. Once a name has
  been read, later screens read about ten times faster.
- **Setup…** changes the current profile.
- **New run** clears the run, so the next seed is not chained to the last one.
- **Anchor** (story): click **✔ Right seed: anchor** on a sublevel, or type a layout seed under
  Anchor. The next sublevels are searched just after it first, which is faster and needs fewer
  letters, and it moves along with each sure seed. A seed found that way says "near the anchor".

## Challenge Mode (attk, key, cmat, 700k)

Pick a Challenge Mode category in setup; step 4 then waits for a results screen instead of a cave.
These modes are CaveGen's real-time manip (`Manip.java`, `Seed.java`), ported:

1. **The score roll.** On each results screen the score digits roll from the global RNG
   (`randInt(9) + 1` per unlocked digit per frame). `p2live::challenge` reads the roll to its end.
   - It is a port of `p2seeds/challenge/results.py` 
   - The panel is registered by template, so GC 4:3, Wii and Wii U 16:9 and any crop work.
   - Decoding starts as soon as the digits stop changing, and takes about 1.2 s once the panel's
     position is known. The position is found at the start of the first screen.
2. **The plan.** Floor 1 of every level is generated and judged with CaveGen3 for the next seeds
   the level select can give. The first one is the roll's last draw + 1004: four menu draws, then
   1000 for the Pikmin dive. This checks out on cmal04, where Cryptic Cavern 1 = `0F129F12`.
   - Ranks come from CaveGen's rank file.
   - **attk** (score attack): levels marked P are preferred, and levels marked I are left out.
     Only layouts in the best `rank threshold` % are shown.
   - **key, cmat, 700k** (all levels): the wait and the scrolling are counted, along with the
     layout against the level's average and the volatility of the floors after it. A times
     table adds the expected cost of the levels still to play (see **Times tables** below).
     - 700k is scored with the attk judge, since CaveGen's own 700k judge was never finished.
     - **A floor with no key** (CH18 Hazard Training, 0.4% of its floor 1s) counts as the
       level's average + 120 s: the runner resets and plays the level again. CaveGen counted it
       as a flat 300 s (key) or 500 (cmat). The option shows "no key".
   - **Special targets** (CaveGen's `@CH18,151AC72B,...` lines, in Manip settings): the
     nearest listed seed ahead, within "draws ahead at most", shows above the options with how
     many title loops away it is (4505 draws each), and its countdown when a menu wait reaches it.
3. **When to press A.** Each option shows the level, the menu moves from the cursor (U/D/L/R) and a
   countdown to its window.
   - Frame 0 is the "Don't Save" press. It is placed `seconds of delay` (CaveGen's 2.0 s) before
     the last black frame of the fade to the level select.
   - That fade is found in the captured frames, so the countdown is synced to the video, not to
     the PC clock as CaveGen's was.
   - Getting the seed before the target means the delay is too high; after it, too low.
4. **Level enters and played levels.** The floor's title card (the level's name in orange on
   black, CaveGen's "red" test, plus a dark-picture check) for 10 game frames is a level enter.
   The option picked in the list (the top one unless you clicked another) is then marked played,
   and the cursor moves to it. With no level enter seen, the next results screen marks it. Click
   the level grid to fix it: a level the runner played without a plan (the run's first) is marked
   by a click.
5. **Title loops.** Left on the level select, the game goes through the title demo and comes back
   4505 draws later. As in CaveGen, with no level enter, an even number of fades (2 or more) since
   the results screen is a loop. The plan is made again from the menu's state then + 4505, timed
   from the next fade. **Title loop +1** does the same by hand. It can be turned off in Manip
   settings.
6. **Splits.** The run's clock starts at its first level enter. "vs splits" is the time so far
   against the summed splits (CaveGen's `splits`, m.ss per level, in Manip settings) of the
   levels played.
7. **Anchor and seeds by hand.** The last roll's end is the anchor for the next screen, so a roll
   with few readable digits can still be found near it. Type a state and click **Anchor** to set
   one yourself, or **Plan from it** to plan as if a roll had ended there (CaveGen's last known
   seed, for when a roll can't be read).

### Times tables

CaveGen's table `t[S]` is, for every set S of levels still to play, the expected time the rest of
the run spends against the levels' averages. It assumes each round offers one random layout per
remaining level and the runner always takes the best "this layout + the rest". It has 2^30 entries
(4 GiB) and takes about 2 days to build.

`t[S]` is very nearly a sum of one number per level and set size: `t[S] ~ sum of w_j(|S|)` over
the levels j in S. That is 900 numbers. The app builds them directly, in `times.rs`:

1. Judge 200,000 random floor 1s per level with CaveGen3. CaveGen used 1,000 quantiles of its rank
   file.
2. For each set size, sample 3,000 sets of levels. Evaluate CaveGen's formula on 4,000 random
   draws, independent per level, using the previous size's numbers. Fit the numbers by least
   squares.

Building all three tables (key, cmat, attk for 700k) takes about 12 minutes on this laptop. The tables are
shipped in `data/times_*.json` (21 KB each), so nothing has to be found or downloaded.

**How close it is.** Simulated over 1,000 full 30-level runs, with the same layout draws for
every method, the time saved per run against average layouts:

| method | size | saved per run |
|---|---|---|
| CaveGen's table | 4 GiB | 261.0 s |
| the shipped table | 21 KB | 260.1 s |
| no table (greedy) | 0 | 223.5 s |

CaveGen's table also had a flaw this build avoids. It paired every level's samples in one fixed
shuffle, so the levels' draws were not independent.

CaveGen's own 4 GiB file can still be used instead: give its path in Manip settings.

```bash
p2live-app.exe --build-times p2live/app/data --samples 200000   # the shipped tables
```

**What it does not do:**
- **Levels:** the played level is the option picked in the list, not read from the screen, and
  there is no plan before a run's first level (no roll precedes it).
- **Timing:** the frame tables are CaveGen's, for GameCube at 30 fps. Its per-level "frames from A
  to the level" are its own rough estimates.
- **Title loops:** detected by CaveGen's fade count, which has not been checked on a video with
  a real title loop.

```bash
p2live challenge video.mp4 --out rolls.json                     # every results screen's roll
p2live-app.exe --headless clip.mp4 --find 7 --run 25 --category key   # the plan, without the window
```

**Checked on CMAL videos:**
- **Roll ends:** the same as the Python reader on all 183 screens of six runs: cmal02 (Wii U,
  Japan), cmal04 (Wii U, USA), cmal08 (GC, Japan), cmal09 (Wii, Japan), cmal13 and cmal26 (GC,
  USA). On cmal09, 16 of the 30 screens are unreadable for both readers.
- **Timing, cmal04 at 3:00 (headless, real speed):**
  - The roll end is `0x2DECAB0E`.
  - Frame 0 falls at frame 387 of the clip.
  - The runner's real A press (frame about 466, 2.6 s after frame 0) lies inside the plan's window
    for the seed they got (`0F129F12`: 0–6.2 s).

## Switch (Pikmin 2 HD)

Pick **Switch** as the console in setup. Pikmin 2 HD's `rand()` is musl's 64-bit LCG
(`docs/switch-rng.md` on the switch-rng branch), so seeds are 16 hex digits.

- **Story:** letter searches, chaining and anchors use the 64-bit generator. Layouts are drawn
  and judged by CaveGen3's Switch mode.
  - Checked on saved letter fits: tcbtrio's EC-1 → EC-2 gives the expected seed and its
    16,424-draw gap.
  - Not yet run on Switch video through the live detector.
- **Challenge Mode:** each score digit is `9 * (s >> 49) / 32768 + 1`, and a roll is solved from
  24 digits on a 64-bit lattice.
  - On cmal01 (tcbtrio, Switch): all 30 rolls decode, and consecutive screens are 18,207–117,485
    draws apart, as the Switch study found. Decoding takes 2–6 s a screen, against about 1 s on
    GameCube.
  - Switch's level select is as blue as the results screen. Once the panel's place is known, a
    blue run counts only if it shows the results panel.
- **Menu timing:** the same frame tables, with the durations read from `rand() / RAND_MAX` at 31
  bits. That the game's frame counts and draws (+4, +1000, +4505) are unchanged on Switch is an
  assumption. No Switch run has been timed against the plan yet.

```bash
p2live-app.exe --headless clip.mp4 --find 7 --run 85 --category key --console switch
```

**Checked on cmal01 (headless, two results screens):** both rolls decode, the fade to the level
select gives frame 0, the floor card ("Snack Pit / Sublevel 1") gives the level enter, the blue
level select is skipped, and the plan lists 64-bit seeds.

## Parts

| file | what |
|---|---|
| `dshow.rs` | cameras through DirectShow (camera → Sample Grabber as RGB24 → Null Renderer) |
| `capture.rs` | frame sources (camera or video file) and the crop |
| `feed.rs` | finding the game picture (p2seeds' `feed.py`, plus growing out to the darkened edges) |
| `engine.rs` | source → live detector → CaveGen3 drawing, on threads of their own |
| `server.rs`, `overlay.html` | the Browser Source |
| `gui.rs` | the wizard and the main view (egui), and the Challenge Mode view |
| `chengine.rs` | Challenge Mode in the engine: results screens, decoding, the fade, the plan |
| `manip.rs` | CaveGen's manip: menu timing, ranks, option costs, special targets, splits |
| `times.rs`, `data/times_*.json` | the times tables (built from CaveGen3 layouts, 900 numbers each) |
| `rng.rs` | the game's `rand()` per console (GameCube/Wii/Wii U, or Switch) |
| `settings.rs` | profiles |

**Why DirectShow:** the OBS Virtual Camera is a DirectShow filter. Apps that read cameras through
Media Foundation, such as the Windows Camera app (and so Rust's usual camera crates), often don't
list it. OBS, Zoom, Discord and OpenCV use DirectShow, and they do.

**Renderer:** the GUI uses OpenGL (glow). eframe's default wgpu renderer crashed at start on the
dev laptop.

**CaveGen3** comes from GitHub at a pinned revision. Its game data is found in this order:

1. `CAVEGEN3_DATA`;
2. a `cavegen3-data` folder next to the exe (for packaging);
3. the checkout cargo downloaded.

## Testing without the window

```bash
# the engine and the Browser Source on a video (or a camera name): find the game picture for
# --find seconds, then detect for --run seconds
p2live-app.exe --headless clip.mp4 --find 30 --run 150 --category pod
p2live-app.exe --feed video.mp4 30 600     # the game picture found from 30 s starting at 10:00
p2live-app.exe --cameras                   # what DirectShow lists
p2live-app.exe --probe-card clip.mp4 500 760   # Challenge Mode screen tests per frame (blue, black, floor card)
p2live-app.exe --grab "OBS Virtual Camera" 3 frame.png
p2live-app.exe --layout SCx-3 0x5FF0883E scx3.png
```

### Results (2026-11-24)

**Headless run on a 200 s wr17 clip, played at real speed.** The clip's stream layout puts splits
beside the game.
- **Game picture:** found from 60 s of play.
- **HoB 2, 3 and 4:** all equal to the offline seeds, high confidence.
  - Ready 0.98, 0.69 and 0.56 s after the screen settled.
  - Drawn 0.41, 0.06 and 0.08 s after that.
- **The Browser Source** showed each layout with its caption.

**Game picture on nine runs' stream layouts** (`--feed`, 30 s of play):
- Within 2 px of the crop the offline pipeline uses on seven of them.
- On 13_JKira and 05_chemical the top edge came out 14 and 24 px low. The top of the picture
  stayed dark during those 30 s; more play, or a drag in the wizard, fixes it.

**Not tested yet:**
- frames from a real camera or from a running OBS Virtual Camera (it connects at 1280×720 30 fps
  but sends nothing until OBS runs);
- the window itself, by a person.
