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
   3. **Category** (Pay Off Debt or All Treasures) **and game language** (or detect
      automatically).
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

## Challenge Mode (attk, key, cmat, 700k)

Pick a Challenge Mode category in setup; step 4 then waits for a results screen instead of a cave.
These modes are CaveGen's real-time manip (`Manip.java`, `Seed.java`), ported:

1. **The score roll.** On each results screen the score digits roll from the global RNG
   (`randInt(9) + 1` per unlocked digit per frame). `p2live::challenge` reads the roll to its end.
   - It is a port of `p2seeds/challenge_results.py` from the challenge-mode-seeds branch.
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
     layout against the level's average and the volatility of the floors after it. CaveGen's
     times table adds the expected cost of the levels still to play.
     - Those tables are 4 GiB each and take about 2 days to build.
     - Give the path in Manip settings. One is at
       `C:\Users\Jordan\Desktop\Hack\CaveGen\files\times_table_key.txt`.
     - Without a table, levels are ranked greedily and the app says so.
     - 700k is scored with the attk judge, since CaveGen's own 700k judge was never finished.
3. **When to press A.** Each option shows the level, the menu moves from the cursor (U/D/L/R) and a
   countdown to its window.
   - Frame 0 is the "Don't Save" press. It is placed `seconds of delay` (CaveGen's 2.0 s) before
     the last black frame of the fade to the level select.
   - That fade is found in the captured frames, so the countdown is synced to the video, not to
     the PC clock as CaveGen's was.
   - Getting the seed before the target means the delay is too high; after it, too low.
4. **Played levels.** When the next results screen comes, the option that was picked in the list
   (the top one unless you clicked another) is marked played, and the cursor moves to it. Click
   the level grid to fix it: a level the runner played without a plan (the run's first) is marked
   by a click.

**What it does not do:**
- **Levels:** no detection of the level-enter card (the played level comes from the picked
  option) and no plan before a run's first level (no roll precedes it).
- **CaveGen extras:** no special targets (`@CH…`), no title-loop tracking, no splits and delta.
- **Timing:** the frame tables are CaveGen's, for GameCube at 30 fps. Its per-level "frames from A
  to the level" are its own rough estimates. Pikmin 2 HD (Switch) uses another RNG and is not
  supported.

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
| `manip.rs` | CaveGen's manip: menu timing, ranks, option costs, times tables |
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
