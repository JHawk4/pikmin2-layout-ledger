# Challenge Mode seeds from video

**Verdict: not feasible with the falling-letter method; feasible a different way, from the
results-screen score roll, for the first floor of every stage after the first.** Floors 2+ of a
stage have no RNG readout in the video. For the run's first stage, the Pikmin dive on the stage
select (§7) recovered the seed in a prototype on one dive; the rest of the menus carry too little (§6).

## 1. What a challenge floor shows on entry

The same floor-title screen opens (cave name + "Sublevel N"), but the name **does not fall**. It
fades in at its final place, red flame particles burn around it, and the letters pulse in size in
place.

![Concrete Maze title, frames 150-310 of the 2-player run](challenge-mode/title-wave.jpg)

Measured on Concrete Maze 1 (frames 150–310, 480p): the letters' bottom edge stays on row 128 from
the first visible frame to the fade-out, and the top edge moves ±5 px with the pulse. A story-mode
title at this size falls about 120 px from the top of the screen.

Decomp (`pikmin2-decomp/src/plugProjectOgawaU/ogObjFloor.cpp`, `ObjFloor::doCreate`): story caves
(`isFLOOR()`) build their title as `TitleMsgDrop`, while challenge ids `c_00`–`c_29` (`isCHALLENGE()`)
build it as `TitleMsgWave` (the enum names in the decomp are swapped). `TitleMsgDrop::init` draws
`randFloat() * 5` per letter; `TitleMsgWave` (`ogTitleMsg.cpp`) never calls `rand()` (a sine wave
plus a `ScaleMgr`). Challenge mode reaches this screen through `VsGame` `LoadState::exec`
(`vsGS_Load.cpp`, `open_Floor` with id `c_%02d`), and the VS-only rule rand (`isVS()`) is skipped.
**So the challenge title carries no RNG information at all.** That is not a detector problem.

## 2. Does the existing detector run on it?

- `p2seeds analyze` on the first 4 minutes of the 2-player GC run finds all 5 title screens as entry
  candidates, but recognizes none of them (best story cave 0.36–0.38).
- `docs/challenge_mode_probe.py` adds the 30 challenge names. Then "Concrete Maze" (CH12) is
  recognized at 0.37 (runner-up "Cave of Pain" 0.28, so the margin is fine; the score is low
  because of the flame glow). The font is the same, so no new templates are needed. 9 of 13 letters
  track, but each moves at most 2–4 px (6.5 for "z") over about 100 frames. `fit` stops with
  "too few letters with a usable fall", as the decomp predicts.
- Both runs were repeated after merging `detection-page-and-tuning` (its new `track.py` pair
  tracking included), with identical results.

## 3. What does carry the RNG: the results-screen score roll

After a stage, `TChallengeResultCounter::update` (`plugProjectMorimuraU/challengeResult2D.cpp`)
rolls four counters: pokos, Pikmin, time bonus and total. Every frame, each digit not yet locked is
`randInt(9) + 1` from the global RNG, ones digit first, in that counter order. One clean frame
shows up to 14 consecutive draws. This is the same signal CaveGen's real-time challenge-mode manip
reads (`Seed.java` `digit_observation`, `sequence_to_seed`; `Manip.java`).

![Solo run, frames 5649 and 5650](challenge-mode/results-digits.jpg)

Read by eye from 480p VODs, then put through `java -cp CaveGen.jar Seed seq2seed`:

| run / frame | digits (draw order) | seed |
|---|---|---|
| 2P GC 6590 | 5817 187 562 6228 | `423CDA79` |
| 2P GC 6589 | 1537 861 333 2557 | its 14 draws sit directly before 6590's, with 1 misread digit |
| 2P GC 13500 / 13506 | 6336… / 6198… | `51D44787` / `5416C4D3`, **84 = 6 × 14 draws apart** |
| solo Wii U 5649 / 5650 | 2586 339 238 6766 / 1311 898 938 8272 | `0F26C79E` / `04047550`, **14 draws apart** |

Later frames, where only the total is still rolling, land in the same stream (4 draws per frame,
then 3, 2 and 1 as digits lock). That pins the draw where the roll ends: about 1090 draws after
`04047550` in the solo run, and about 1195 after `51D44787` in the 2P run.

## 4. Seed → floor-1 layout, checked with CaveGen3

As in CaveGen's manip, the next stage's floor-1 layout seed is
`roll_end + 1004 + k`, where k is the number of slow menu advances between the results fade and
starting the stage. Each advance takes 16–286 frames (`seed_duration`); the first takes
`seed_duration_first`.

Solo run ([tcbtrio, Wii U VC USA, 56:05](https://www.youtube.com/watch?v=0Wa5r0jQBAc)):
- The roll ends at stream index 1090: the last draw is the thousands digit '9' that appears at frame
  5763, and the display never changes after that.
- The stage was started about 120 frames after the results fade (black at 5838, stage fade at about
  5958). The first menu advance would come 192–269 frames after the fade, so k = 0.
- That predicts Cryptic Cavern 1 (CH11-1) = `04047550` + 2094 = **`8F129F12`**.

![Video vs CaveGen3 renders](challenge-mode/ch11-1-verify.jpg)

The video matches the prediction: the pod is alone in its room, and the far room has the doodlebug
high up near the hole and the diamond right of centre, below it, where the player sends Pikmin
(frame 6410). The neighbours differ visibly: +2092 has the diamond top-right by the hole, and +2093
has the doodlebug lower. CH11-1 is a simple floor (two rooms, one teki, one treasure), so this is
consistent evidence rather than proof. A multi-room floor would confirm it better.

Also: the two 2P results screens are only 28,058 draws apart across the 5-floor Cryptic Cavern
stage. Floors 2+ are bounded to a window that small, but the video gives no readout inside it.

## 5. What supporting it would take

1. **New event type**: detect the results screen (blue panel, "Results!") instead of the title.
2. **Digit reader**: about 10 digit templates for the results font. This is a slot-roll font, not
   the HUD digits; `digits.py` is a starting point. Read the four counters per frame, ones digit
   first; locked digits are skipped (not drawn) and must be recognized as locked.
3. **Seed search**: the digit observation is affine in the RNG, like the letters, so `lattice.py`
   can take digit intervals (width 1/9) instead of velocity intervals, or call CaveGen's `seq2seed`.
   Chain consecutive frames (exactly N draws apart) to confirm, as `chain.py` does.
4. **Roll end and menu timing**: track the roll until it locks, measure fade → stage start in game
   frames, and walk `seed_duration` to get k. Then the layout is `end + 1004 + k`.
5. **Cave table**: challenge ids `CH1`–`CH30` (CaveGen3 names them `CH11-1` etc. and generates them;
   `caves.py` needs English names for the stage order and labels, see the probe).
6. **Verification**: compare the landing view (CaveGen3 `--view pod`) with the video, since there is
   no second independent reading of the same seed. The ±2-draw uncertainty at the roll end means a
   few neighbours must be ranked.

Limits:
- No floor 2+ seeds.
- No seed for the run's first stage, which has no preceding results screen.
- 2-player runs are split screen (harder to verify, though the digits read the same).
- The solo run here is the Wii U VC release ("New Play Control!" in its splits). Its roll and
  CaveGen3's `pikmin2` data agreed on this floor.

## 6. RNG on the menus before a stage is picked

The question: can something on the title screen, file select or challenge stage select read the
RNG for the stages the results roll can't cover (the run's first stage, floors 2+)?

**Verdict: no for the title, file select and flash; yes for the dive (see §7, which supersedes the
"not readable" verdict on the dive below).** The menus advance the global RNG, but only two things
there carry real information. The stage-select flash timer gives about 8 bits per flash, and a runner sees 0–1
flashes per visit. The stage-confirm Pikmin dive makes 1000 draws but can't be read at VOD
resolution. Neither pins a seed. The decomp does explain CaveGen's "+1004", which confirms the
menu → floor-1 link used in §4.

### Seeding

`System::construct` calls `srand(OSGetTick())` at power-on (`sysGCU/system.cpp:421`). Nothing
reseeds afterwards: no `srand` on file load, on entering Challenge Mode, or per stage (the only
other `srand` is the memory-card unlock's private LCG, `Dolphin/card/CARDUnlock.c`). So the RNG
carries over through everything since boot, including all gameplay.

### Per screen

| screen | global-RNG draws while showing (decomp) | visible? | verdict |
|---|---|---|---|
| Boot | `srand(OSGetTick())` | no | unknowable |
| Title / Press Start | `ebiScreenPushStart.cpp:142` one `randEbisawaFloat` per loop (picks 1 of 4 screens, 2 bits). Title-scene Pikmin `ebiP2TitlePikmin.cpp:518–541,665`, Chappy `ebiP2TitleChappy.cpp:211–227`, Kogane `ebiP2TitleKogane.cpp:192–204` and `ebiP2Title.cpp:193,548,571,732` draw on spawn and on each AI state change (speeds, wait timers, turn angles) | yes, dozens of small agents on a chaotic simulation | not readable in practice; also not in run footage (see below) |
| Title menu | `ebiScreenTitleMenu.cpp:308`: one draw per highlight cycle, `< 0.2` shows a sparkle (about 0.7 bits) | yes | far too little information |
| File select | none (`ebiFileSelectMgr.cpp`, `ebiScreenFileSelect*.cpp` have no `rand`); Challenge Mode does not go through it | — | nothing to read |
| Challenge stage select, created | `TChallengeSelect::doCreate` (`plugProjectMorimuraU/challengeSelect2D.cpp:1387,1402`): `TChallengePlayModeScreen` ctor 3 draws (`mAngleTimers`, the "Pick one!" swing phases, :680), then `TChallengeScreen` ctor 1 draw (first flash delay `300·r` frames, :518) | swing phase: only during "Pick one!", about 20 frames | not enough |
| Challenge stage select, idle | `TChallengeScreen::update` (:600–620): after each highlight flash, the next delay is `300·(0.9r + 0.1)` frames, one draw per flash. This is exactly CaveGen's `seed_duration` / `seed_duration_first` (`Seed.java:628–635`) | the highlight on the stage panels (`Nhl_00`–`Nhl_14`) | about 8.1 bits per frame-timed flash (270 possible delays); pinning 31 bits needs about 4 consecutive flash gaps, which is 20+ s idle on the menu |
| Stage confirm (dive) | `TChallengeSelect::jumpStart` → `TChallengePiki::jumpStart` (:75–96): 5 colours × 50 Pikmin × 4 `randFloat` (start delay 0–0.1 s, x deviation ±30 units, its sign, y deviation 15–25) = **1000 draws** | in theory | lots of information, but not readable from these videos (below) |

### What the footage shows

- **Neither run shows a title screen or file select.** The solo video opens on "Continue / Give Up"
  from an earlier attempt (frames 0–30) and goes straight to the stage select (frame 100). The 2P
  video opens on the stage select. A run's first stage therefore follows a give-up, after gameplay,
  so the RNG at that point is unknown.
- **Time on the stage select is about 4 s per visit.**
  - Solo, after stage 1: the results fade out at 5838, the menu is visible at 5850, the cursor moves
    and A is pressed at about 5866, "Pick one!" shows 5869–5888, the dive runs 5895–5955, and the
    stage starts at 5964.
  - Solo, run start: menu at 100, "Pick one!" 115–135, dive 136–200.
  - 2P before Snack Pit: menu fades in about 13716, "Pick one!" about 13746–13764, dive 13770–13836.
  - So the panel is on screen for about 45–60 frames before A. The first flash comes `300·r` frames
    after the menu is built, so a typical visit shows 0 flashes, sometimes 1.
- **No flash was seen.** In the 2P Snack Pit visit, the known seed puts the first flash 107 frames
  after the menu was built (about frame 13817, during the dive). No change shows on the flower grid
  in frames 13796–13840, and the solo menu visits show none in the grid-brightness trace. The
  highlight is subtle at 360/480p (the solo VOD is 640×360). Even a visible flash gives one 8-bit
  reading.
- **The dive is not readable.** The Pikmin are about 6 px tall and fly in tight single-file queues
  per colour, overlapping (solo frames 5900–5952, 2P frames 13796–13836). The start delay (≤ 3
  frames) and ±30-unit scatter of one Pikmin can't be separated from its neighbours'. A clean,
  full-resolution capture might do it: 1000 draws ending exactly at floor-1 generation would pin
  the seed with no timing involved. That would be its own research project, and these VODs can't
  support it.

![Solo stage select after stage 1, frames 5840-5968: cursor, "Pick one!", dive](challenge-mode/stage-select.jpg)

![The dive, solo frames 5896-5952](challenge-mode/menu-dive.jpg)

### Menu → floor 1 (this confirms §4)

From the results roll's end L, in order: the menu is built (4 draws: 3 swing phases + first flash
delay), then k flash draws, then the dive (1000). Floor 1 is generated from **L + 4 + k + 1000**,
which is CaveGen's `next_seed(lastReadSeed, 1004)` with timer seed `L + 4`. The CH11-1 check in §4
(k = 0, `8F129F12`) is this chain. One unchecked case: a flash timer that runs out during the dive
(as predicted for the 2P Snack Pit visit) would make its draw after the dive's, if
`TChallengeScreen::update` keeps running in the demo. That would shift floor 1 by +1. Rank ±1
candidates when that happens.

### What stays out of reach

- The run's first stage: it follows a give-up, and the only readout before it is the unreadable
  dive.
- Floors 2+: no menu between floors.

## 7. Reading the seed from the Pikmin dive (prototype: works on one dive)

§6 called the dive unreadable. Closer work shows it can be read, at least for a small dive. On the
solo run's dive into Cryptic Cavern, the seed was recovered from the video **without using the
score roll**, and it is the same seed §4 found and checked against CaveGen3.

### What each draw does on screen

From `TChallengePiki::jumpStart` / `update` (`challengeSelect2D.cpp:75–200`). Pikmin *i* of colour
*c* (red, yellow, blue, white, purple) gets 4 draws:
- launch timer `T0 = 0.1·r₀ − 0.1·i − 0.5·c`
- sideways deviation `dx = 30·r₁`, negated when `r₂ > 0.5`
- hop height `dy = 15 + 10·r₃`

The timer advances 0.15 per frame. While it is in [0, π/2] (about 10.5 frames), the Pikmin hops
sideways: `x = X₀ − dx·sin t`, `y = Y₀ − |dy·sin 2t|`. It then climbs 12 units per frame at
`X₀ − dx` up to y = 100, and arcs to the stage panel.

Only the stage's starting Pikmin are moved and drawn (`mMaxPiki`, at most 50 per colour), but all
5 × 50 × 4 = 1000 draws are made regardless. Cryptic Cavern starts with 5 red and 5 white, so 10
Pikmin are visible.

The draws in game order are: last visible roll digit at s₁₀₈₉, then 5 more draws (s₁₀₉₀–s₁₀₉₄),
then the dive s₁₀₉₅–s₂₀₉₄, and floor 1 is generated from s₂₀₉₄ = `8F129F12`. This matches CaveGen's
`lastRead + 1004` exactly. §6's count of 4 menu draws left out one draw, whose source isn't pinned
down; the high-score slot's `randInt(6)` in `challengeResult2D.cpp` is one possibility.

### Evidence

- **Qualitative.** Each Pikmin uses 4 draws, so shifting the dive start by 4 moves every Pikmin
  over by one. Of offsets +1086…+1101 from `04047550`, only +1095 puts the red group 2 left /
  3 right and the white group 4 left / 1 right, as in the video.
- **Image fit.** The model renders a sprite template (cut from the video) at each simulated
  position, against background-subtracted frames 5893–5911. Scale, group origins, climb length and
  frame phase are fitted per hypothesis, within bounds.
  - +1095 scores 8731.
  - The 16 neighbouring offsets score 10712–15403.
  - 20 random seeds score 10113–13505.

![Simulated positions for +1095 (yellow: red Pikmin, cyan: white) over the video](challenge-mode/dive-fit.jpg)

The climb-and-arc part (from about frame 5905 for red) isn't modelled; only the hop and climb are.

### Seed-free recovery (`docs/challenge_dive/divemeasure.py`)

1. **Geometry**, fixed from the calibration fit: 0.88 × 0.65 px per unit, the red and white group
   origins, and the frame phase. These are properties of the capture layout. The tally icons sit at
   the same place on every stage, so in a run they can come from any dive whose seed the score roll
   already gives. Here they came from this same dive; see caveats.
2. **Measure each Pikmin freely**: launch jitter, signed sideways deviation and hop height, by
   differential evolution against the frames, with identity taken from launch order.
   - Sideways deviations came out within 0.7–3.9 units (red) and 0.1–1.3 units (white) of the truth.
   - All 10 directions were right.
   - Launch jitter and hop height are not measurable at 360p.
3. **Lattice search** over all 2³¹ states (`lattice.box_points`). Each |dx| bounds draw 4i+1 to
   ±4.5 units, and the direction bounds draw 4i+2 to half its range. 15 states satisfy all 20
   constraints (116 s), including the true one.
4. **Rank** the 15 by the image fit with the calibrated geometry. The true state comes first:
   8732, against 9328 for the next. That gives dive start `7CF9494B` and floor-1 layout seed
   **`8F129F12`**, the one verified against CaveGen3 in §4.

Synthetic check: with exact or σ = 1 noisy deviations and ±2.5 units, the lattice leaves about 30
states and the direction signs leave exactly the true one, in under a second.

### Caveats and what's next

- **One dive, one video.** The geometry calibration came from the same dive. A proper test is to
  calibrate on another stage of the run (its seed from the score roll) and recover a different
  dive. The frame phase must also be found per dive (from the first hop frame) instead of fixed.
- **The margin is modest:** 6% to the second candidate. Rendering the remaining candidates' floor 1
  with CaveGen3 and comparing with the landing view would settle close calls.
- **Crowding.** 5 per colour is a small dive. Bigger stages have up to 50 per colour, launched
  0.67 frames apart, so they overlap much more. The first few Pikmin of each colour are still the
  cleanest, and about 10 sideways deviations are enough.
- **2-player runs:** the dive is drawn once (no split screen), so the method should carry over, but
  it is untried.
- **What it adds:** the run's first stage, which follows a give-up and has no score roll before it.
  On later stages it gives an independent check of the roll and pins the ±1 draw. Floors 2+ are
  still out of reach.

## 8. The dive reader at scale: several runners, and the score WRs

§7 worked on one dive. This section turns it into a pipeline
(`p2seeds/src/p2seeds/challenge_dive.py`, scripts in `docs/challenge_dive/`) and tests it across
runners, against the score rolls.

### Pipeline (`challenge_dive.read_dive`)

1. **Menu visits:** frames showing the stage select (blue with pink flowers). One pass takes about
   1.5 minutes per hour of video.
2. **Registration:** a scale-and-shift match of the menu against a reference frame (cmal04 frame
   11792), with separate x and y scales. This places the five tally icons, the 5×6 stage grid and the
   sprite scale on any capture layout (Wii/Wii U 16:9; GC 4:3 to be tested).
3. **Stage:** the panel where the dive lands (its white flower burst). For WR videos the stage comes
   from the record.
4. **Starting Pikmin per colour:** CaveGen3's `challenge_stages.csv`. The dive draws only
   `mPikiCounts[c]` Pikmin per colour, at most 50 (`challengeSelect2D.cpp:2111`).
5. **Observations:** for each frame, the difference from the per-pixel median over the dive (each
   pixel shows a Pikmin only briefly). Frames dominated by the "Pick one!" window are dropped.
6. **Frame phase f0:** a search over the whole menu visit. Motion onset can't be trusted, because
   the "Pick one!" window is still sliding away when the dive starts.
7. **Candidate states:** either all 2³¹ states (numba kernel: about 3.9 s per 16M states for 6
   Pikmin, so about 8 minutes), or, when a later results roll is decoded, only the states whose
   floor-1 seed lies within a window before that roll's first state. Every CMAL stage consumed
   18k–183k draws from the floor-1 seed to the next roll, so a window of 3 million is safe.
8. **Scoring:** a cheap lookup score at each Pikmin's late-hop positions, then a compiled
   full-image loss (half resolution, every other frame, about 30 s per 200k states) on the best
   400k, then the exact image loss on the best 2000.
9. **Geometry refit:** refit scale, origins, frame phase and landing panel on the leader, then
   prune and re-rank again with the refitted geometry. This step matters: a look-alike state (one
   whose 10 Pikmin are all within a few units of the truth) can win with fixed geometry, but the true
   state is the one that lines up exactly once the geometry is refined. On Cryptic Cavern the
   fixed-geometry loss was 21,712 for the impostor against 22,247 for the truth; after refitting it
   is 26,620 against 11,543.
10. **Floor-1 layout seed** = the state after the dive's 1000th draw. Bit 31 never reaches
    `rand()`'s output, so seeds are given in 31 bits.

The dive begins **5 draws after the last draw of the previous score roll**, as defined by the roll
reader's `state_after_last_draw`. That holds for both hand-checked cases (Cryptic Cavern, Snack Pit),
and then the floor-1 seed = that state + 1004, matching CaveGen's constant.

### Score-roll reader (`p2seeds/src/p2seeds/challenge_results.py`)

Built by a helper agent and checked against the hand-read values in §3–§4. On 9 videos it decoded
274 of 306 results screens. Rolls in cmal09 (spark573, Wii) are partly blended frames, so only 14 of
30 decoded. **The Switch release (Pikmin 2 HD) does not use the GameCube/Wii random-number generator
or digit mapping**: its digits read cleanly, but no GC/Wii RNG state explains them under any of the
48 orderings tried. Switch runs are out of scope.

### Cross-check against the rolls (`docs/challenge_dive/crosscheck_cmal.py`)

For each stage between two decoded rolls, the dive is searched using only the **following** roll
(a window of 3M states). The result is then compared with the truth from the **preceding** roll
(its end + 5). The two sources are independent.

CROSSCHECK_TABLE

Per-stage RNG use is consistent between runners
(`p2seeds/src/p2seeds/data/challenge_stage_draws.json`: draws per video frame from the floor-1 seed
to the next roll, 6 CMAL runs). For example, CH6 uses 5.4–7.0, CH11 3.3–4.2 and CH26 8.9–16.6. For
dives with few Pikmin, the window is narrowed to (frames from the dive to the results) × the stage's
rate, ±35%.

### Score WRs (pik5.net, current Pikmin 2 #1s)

WR_TABLE

## 9. Floors after the first (stretch goal): not done, but bounded

No readout on screen carries the RNG between floors: the floor titles are `TitleMsgWave` (§1), and
there is no results roll or menu between floors. What we do know is a window:

- Floor *k* ≥ 2 is generated from a state strictly between floor 1's seed (known from the dive or
  the previous roll) and the first draw of the stage's results roll (known from the roll).
- That window is small:
  - On the CMAL runs, all floors of a stage together consume 18k–183k draws (median about 50k;
    `data/challenge/stage_rates.json`). The 5-floor Cryptic Cavern took 21k–26k draws in every run.
  - On the CH1 score WR the floor-1 seed is about 1.1M draws before the results roll. Score runs
    have far more Pikmin and enemies active per frame.
- Each floor's seed is therefore one of a few tens of thousands (CMAL) to about a million (WR)
  consecutive states. In that range, CaveGen3 can generate every candidate layout in seconds to
  minutes. The floors are also ordered: floor 2's seed < floor 3's < … within the window.

The missing piece is a **layout matcher**: scoring a candidate layout against the video's first
frames on that floor. The landing camera is known (CaveGen3 `landing_corners`, `views.py`: 900
units back, 25° down, 26° field of view; the Olimar landing camera faces a fixed heading of 110°).
That gives a homography from the screen to the floor. So the floor/wall mask visible at landing
could be compared with each candidate's rendered floor (`--view olimar`). I checked the geometry
on Cryptic Cavern 1 but did not build the matcher.

With a matcher the search is small. With 50k candidates per floor on CMAL runs, even a weak matcher
that keeps the top 1% leaves 500 candidates, and the next floor's landing plus the ordering
constraint would narrow those further. That would also settle the dives that can't be pinned down
on their own (2–4 Pikmin, single dense colours), since floor 1's layout can be checked the same way.

## Footage used

- 2P GC USA: [tcbtrio, CurtisDN_ 59:25](https://www.youtube.com/watch?v=GJhM7TEK0bY) (speedrun.com
  "Challenge Mode All Levels", #13), first 8 min and full video at 480p30.
- Solo Wii U VC USA: [tcbtrio 56:05](https://www.youtube.com/watch?v=0Wa5r0jQBAc) (#4), full video
  at 480p30.

Downloads are in `data/challenge/` (gitignored). The CaveGen3 candidate renders are in
`data/challenge/cand*`.
