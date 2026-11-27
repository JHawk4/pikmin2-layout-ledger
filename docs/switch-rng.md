# Pikmin 2 on Switch (Pikmin 2 HD): can the letters give seeds, and is the RNG different?

**Update: yes, the RNG is different, and it is now identified: musl libc's 64-bit LCG. With it,
Switch seeds read from video and chain (section 7).** Sections 1–6 below are the first study,
which tested only the GameCube generator.

Nov 2026. Scripts in `docs/switch/`. Videos and outputs are under `data/switch/` (not committed).

## Verdict

**(a) The letters can be read, but they give no seeds.** On Switch the cave name falls exactly as on
GameCube. With the 16:9 calibration fix, the pipeline recognizes the names and fits the falls as
cleanly as on GameCube footage: 0.08–0.09 px residual against 0.07–0.08 px on GC, 13–14 letters per
English name, and the same gravity, scale and timing. Still, not one of 141 recognized Switch entries
gets a high-confidence seed, and none of the low or medium ones chain with a neighbour. On GameCube,
every entry of a run gets a high-confidence seed and they all chain.

**(b) Yes. The letter speeds on Switch do not come from the GameCube/Wii `rand()` stream.** The
measured speeds are clean, evenly spread over [0, 5) like GC's, and come from the same physics. Yet no
state of the GC generator produces them, under any of the draw orders or generator variants tried. On
GC footage the same tests explain every entry, and only with the true model. The test does not depend
on where the RNG state is (it searches all 2^31 states for each entry), so a different seed, reseeding
or extra draws between screens cannot explain the miss. The generator itself, or the way the letters
draw from it, is different. This is independent of the Challenge Mode study, and it agrees with it: I
re-ran that study's reader on its Switch video and got the same result, 0 of 30 score rolls decoded.

Wii New Play Control!, the build the Switch port is based on, does match GC. The sibling Wii session
gets high-confidence GC seeds on Wii story runs. So whatever changed, changed in the Switch port.

## 1. Runs and detection

Pay Off Debt, console Switch, from speedrun.com (`srcom_videos`, 360p 30 fps; YouTube offered no
480p60 H.264 stream for these). The Switch game runs at a locked 30 fps (Digital Foundry), so one
video frame is one game frame, as on GC.

| run | entry screens found | names read | clean letter fits | seeds high / medium / low / none | chained |
|---|---|---|---|---|---|
| tcbtrio, Switch USA (4th, 1:50:52) | 95 candidates | 55 | 52 (median 14 letters) | 0 / 0 / 8 / 47 | 0 |
| Jirazee, Switch USA (7th, 1:58:19) | 82 candidates | 31 | 31 (median 13 letters) | 0 / 0 / 2 / 29 | 0 |
| mercysnow, Switch 2 JPN (1st, 1:46:21) | 92 candidates | 55 | 43 (median 5 characters) | 0 / 7 / 32 / 16 | 0 |
| *GC tcbtrio (same runner), for comparison* | | 52 | 50 (12 letters) | 52 / 0 / 0 / 0 | all |

"Candidates" include many dark cutscenes and menus. Names were read for 55, 31 and 55 entries. A GC
Pay Off Debt run has about 52 entries. Jirazee lost about 20 entries (parts of GK, SCx, SH, FC, SR)
to unrecognized names; I did not chase this, as it does not affect the verdict.

**Change needed:** `calibrate.py` searched English name widths only up to the 4:3 scale. On a 16:9
picture the name is spread by 4/3, so EC scored 0.32 and was rejected. Allowing the 16:9 stretch,
which is the same edit the Wii story session made, gives EC 0.75. That was the only change. The
templates, the fall model and the 30 fps timing all work unchanged.

The Switch runs were processed with `docs/switch/run_fast.py`. This is the normal pipeline with the
seed search capped at 20k lattice nodes, the leave-one-out retries off, and the one-frame timing-step
refits off. Uncapped, one Switch entry ran for more than 30 minutes, because the search retries every
letter subset when nothing fits. The cap cannot hide a GC seed: with 12+ letters the lattice holds
only the true seed and finds it in milliseconds. Section 3 re-searches every clean fit with a 10×
larger budget.

## 2. Letter physics: identical to GameCube

On tcbtrio EC-1 (frame 23300; `docs/switch/probe.py` fits the fall without the seed search):

- **Residual:** 0.085 px over 13 letters, 9–11 frames each.
- **Scale:** s = 0.688 px per game unit against the GC model's H/480 = 0.667. That is +3%, within
  the range seen on GC captures.
- **Gravity:** a free parabola per letter gives 0.997 game units/frame², against 1 on GC. So the
  letters run the same per-frame physics at 30 fps.
- **Timing:** letter *i* of *n* starts *i/n* s after the first, as on GC. A wrong delay schedule would
  ruin the residual.

Across all runs (`docs/switch/summarize.py`):

| run | clean fits | median rms px | letters/entry | share of speeds per fifth of [0,5) | KS distance to uniform |
|---|---|---|---|---|---|
| GC tcbtrio (EN) | 50 | 0.083 | 12 | 0.20 0.20 0.20 0.21 0.19 | 0.023 (n=682) |
| GC kobachi (EN) | 51 | 0.075 | 12 | 0.19 0.21 0.21 0.22 0.17 | 0.035 (n=674) |
| GC kobachi AT (JP) | 109 | 0.071 | 5 | 0.20 0.19 0.20 0.24 0.17 | 0.042 (n=560) |
| **Switch tcbtrio (EN)** | 52 | 0.089 | 14 | 0.24 0.18 0.19 0.21 0.18 | 0.058 (n=739) |
| **Switch Jirazee (EN)** | 31 | 0.085 | 13 | 0.22 0.18 0.22 0.19 0.20 | 0.027 (n=404) |
| **Switch 2 mercysnow (JP)** | 43 | 0.080 | 5 | 0.19 0.21 0.19 0.21 0.19 | 0.042 (n=243) |

The speeds on Switch span 0 to 5 and are uniform, as on GC. The scale (×5/32768) and the general form
`rand × const` are consistent, but the values are not GC `rand()` outputs.

## 3. Why the RNG must differ

Each well-measured letter pins its draw to about 1/30 of the range (±4σ, σ ≈ 0.014). With 12+
letters, the chance that any of the 2^31 states fits them all by accident is about 10^-9. So the true
generator stands out, and a wrong one finds nothing.

**Lattice search, GC LCG and variants** (`docs/switch/variants.py`, all 2^31 states, 200k-node
budget). The hypotheses tested were:

- consecutive draws (the GC model)
- reverse order
- 2, 3 or 4 draws per letter (stride 2–4, with the letter's draw first, or second for stride 2)
- no draw for spaces
- the same with the MSVC and Borland C `rand()` LCGs (consecutive and reverse)

| fits tested | explained by GC consecutive | by any other variant |
|---|---|---|
| GC tcbtrio, 48 clean entries (positive control) | **48 / 48** | 0 (no false hits) |
| Switch tcbtrio, 49 clean entries | 0 | 0 |
| Switch Jirazee, 31 clean entries | 0 | 0 |
| Switch tcbtrio EC-1 probe fit | 0 | 0 |

**Brute force, other generator families** (`docs/switch/brute.py`, on the EC-1 fit, 13 letters,
consecutive and stride 2). The best letter pins its state to a range; every state in that range is
stepped to each other letter's draw.

On a GC entry (EC 15039, control), the GC generator agrees on **13/13** letters and wrong orderings on
7/13. Seven is the chance level: the pivot and 5 pruning letters agree by construction, and 1–2 more
agree by chance among millions of survivors. On Switch EC-1, the best state of every generator agrees
on at most 8/13:

- GC LCG read through bits 16–30, bits 16–31, or the top 23 bits
- MSVC `rand`
- JSystem `TRandom_fast` (top 23 bits)
- the Numerical Recipes LCG
- `minstd_rand0` and `minstd_rand`

None of these is the Switch letter generator, in consecutive or stride-2 order.

**Chaining.** On GC, consecutive entries are close in RNG order: all 51 gaps in GC tcbtrio are under
422k steps (median 64k). The low and medium "seeds" on Switch are chance lattice points. Their mutual
distances are random (10^8–10^9 steps; e.g. mercysnow BK-4 to BK-6 is 717M), and `chain.link`
connects none of them in any run. For comparison, the Japanese GC run kobachi AT has the same ~5
characters per name. Its pre-link fits are similarly weak (0 high), but linking chains 77 entries
and ends with 85 high seeds. Switch mercysnow chains 0.

**What this rules out and what it leaves.** The search covers every state, so the Switch RNG's seed,
position, reseeding, and draws between entries are irrelevant. The fall physics, timing and speed
scale are measured to match. What remains is that the numbers drawn differ. Either `rand()` itself
is replaced, or the letters draw from some other source in a way not covered above, for example a
non-LCG generator such as a host-side one. I can't tell which from video. Wii NPC matches GC, so the
change is specific to the Switch port. Datamining is reported to show CPU code recompiled to run
natively under the "hagi" emulator, as for Super Mario Sunshine in 3D All-Stars. A replaced C-library
`rand` would fit that, but it is a guess.

## 4. Layouts

With no seeds there is no layout to verify. A rough visual check of Switch EC-1 (tcbtrio, frames
23420–25000) is consistent with CaveGen-style generation: the pod in a dead-end cap, a corridor, a
round room holding the hole, and the usual EC-1 treasure. It cannot say whether the generator is
identical. That would need a seed, or a matcher from a layout picture to a seed, which doesn't exist.
If the Switch `rand()` is replaced, layouts would come from a different stream even if the cave
generator code is unchanged, so GC-style seed manipulation would not carry over.

## 5. Challenge Mode claim re-checked

I ran `challenge_results.py` from `claude/challenge-mode-seeds-37abaa` on the same Switch video that
study used (cmal01, tcbtrio Switch USA). All 30 results screens were found and registered (panel
match 0.88–0.89), and **0 of 30** rolls decoded: "no frame solved to a state confirmed by the next
frames". This confirms the earlier result.

One caveat to "its digits read cleanly": final values are mostly right, but not always. For example,
a total of 9707 was read as 9767. The study used GC/Wii U digit templates on the Switch's HD font.
Occasional misreads alone would not stop every roll from decoding, since the reader tolerates a few.
The letter test above does not depend on digit reading at all.

## 6. Public information

A research pass (Nov 2026) found the following:

- **Emulation:** Digital Foundry's analysis, via Nintendo Life, says Pikmin 1 and 2 on Switch use
  the "hybrid emulation" of Super Mario Sunshine's port: Nintendo's "hagi" GC/Wii emulator, with the
  CPU code recompiled to run natively. They run at a locked 30 fps, at 1080p docked and 720p
  handheld. NERD credits itself with the "emulation technology".
- **Base build:** Pikipedia says the port is built from the North American New Play Control! build.
  2-Player Battle now defaults to "unbalanced random generation", so Nintendo did touch some
  randomness-related behaviour. A Sept 2023 update listed "other changes".
- **Seed research:** no public source tests whether Switch layouts match CaveGen seeds, or whether
  seed or Challenge Mode manipulation works on Switch. CaveGen supports only GC regions.

Sources:

- https://www.nintendolife.com/news/2023/07/video-digital-foundrys-technical-analysis-of-pikmin-1plus2-on-switch
- https://www.nerd.nintendo.com/2024/10/24/Pikmin1+2.html
- https://www.pikminwiki.com/Pikmin_2_(Nintendo_Switch)
- https://switchbrew.org/wiki/Super_Mario_3D_All-Stars (the comparison case)

## 7. The Switch generator, recovered from video

**Result: Switch `rand()` is musl libc's.**

```
s = 6364136223846793005 * s + 1   (mod 2^64)
rand() = s >> 33                  (31 bits; the state is advanced first)
randFloat() = rand() / RAND_MAX   (the native RAND_MAX = 2^31 - 1)
```

This is what you get when the game's C source is rebuilt against the Switch SDK's C library: the
`RAND_MAX` macro in `rand.h` takes the native value. As far as the game's arithmetic goes, only the
top bits of the 64-bit state matter. A letter speed is `5 * s / 2^64`, and a Challenge Mode digit is
`floor(9 * (s >> 49) / 32768) + 1`.

It was found by testing candidates against Challenge Mode digits, then confirmed two independent
ways, each with no realistic chance of happening by accident.

### The data

- **Challenge Mode score rolls** (`dump_digits.py`): every frame's digits for all 30 results screens
  of the Switch video (cmal01) and of a Wii U control (cmal04, same runner). Each screen has 40–70
  frames where all 14 digits roll.
  - **Reading looks clean on both:** digits 1–9 each come up 10.4–11.3% of the time, with 39 of
    21,815 Switch slots unreadable.
  - **Every digit is redrawn every frame:** a rolling digit repeats from one frame to the next 12.9%
    of the time on Switch and 12.4% on Wii U.
- **Information per draw:** a digit fixes about 3.2 bits of the generator's output fraction, and a
  letter speed (σ ≈ 0.015 of 5) about 8 bits.

### Test 1: a list of likely generators (`rng_candidates.py`)

Each candidate is solved from a few frames and must then predict the following frames' digits.

- **LCGs:** a lattice search over the whole state, as `challenge_results.py` does for GC. A 64-bit
  LCG takes 24 digits.
- **GF(2)-linear generators:** every output bit is an XOR of state bits. Each digit's certain top
  bits (digits 1–4 mean the top bit is 0, 6–9 that it is 1) give linear equations, and Gaussian
  elimination solves for the state.

**Self-test:** synthetic rolls from each generator are solved exactly, and a GC roll is rejected by
all of them. **Control on real footage:** the GC LCG on the Wii U roll predicts 112 of 112 check
digits.

| family | x = which 15 bits | Switch |
|---|---|---|
| **musl `rand` (64-bit LCG, c = 1)** | **bits 49–63, i.e. `(s >> 33) / 2^31`** | **102/102 check digits, one state** |
| same LCG, other windows (newlib's `rand` returns bits 32–62) | bits 32–46, 33–47, 48–62 | no state fits |
| Knuth MMIX/PCG (same multiplier, other increment) | bits 32–46 | no state fits |
| 32-bit LCGs: GC/MSL, MSVC, Borland, Numerical Recipes, Unreal `FRandomStream`, Delphi, Turbo Pascal, cc65 | bits 0–14, 16–30, 17–31 | no state fits one frame's 13–14 digits, in any of 24 windows |
| VB6 (mod 2^24) | bits 0–14, 8–22, 9–23 | no state fits |
| xorshift128 (= sead::Random), xorshift32, xorshift64, WELL512a | output >> 17, >> 16, & 0x7FFF | inconsistent in all 24 windows, also with 0–40 extra draws per frame (xorshift) |

Java `Random`, Lehmer/minstd and the remaining Knuth windows were not run to completion once musl
had matched.

### Test 2: any 32-bit LCG with unknown constants (`stern.py`)

This was done before the match. It is kept because it answers "could it be an LCG with other
constants?" without guessing the constants, and it shows what letters can do that digits can't.

1. **Differences cancel c.** The state differences y_i = s_{i+1} − s_i satisfy y_{i+1} = a·y_i
   (mod m), with no c.
2. **Find relations.** LLL finds short λ with Σ λ_i y_{i+j} ≡ 0 for every window, using only the
   measured y's (Stern; Frieze–Håstad–Kannan–Lagarias–Shamir).
3. **Find a.** Each λ is a polynomial with root a, lifted bit by bit and voted on.

**Why letters and not digits.** This needs about 31/k + log2 k known bits per output (about 7 for
k = 8). Letters give about 8; digits give only about 1.6. Windows from all of a run's entries share
one lattice, since a is the same everywhere.

| run | model | recovered | entries consistent |
|---|---|---|---|
| GC tcbtrio (control) | x = bits 16–30 | **0x41C64E6D**, blind, 4 votes | 8/8 (runner-up 0/8) |
| GC tcbtrio (control) | x = bits 17–31 (off by one) | 0x41C64E6D, 3 votes | 8/8 |
| Switch tcbtrio | x = bits 0, 4, 8, 12, 15, 16, 17 up | nothing | 0–1/9 (chance) |

So no LCG mod up to 2^32, with any constants, stride or output window, makes the Switch speeds.
That is consistent with the answer: musl's is mod 2^64, outside this test's range.

### Confirmation 1: every Challenge Mode roll decodes and chains (`musl_rolls.py`)

- **All 30 rolls decode.** For all 30 results screens, the state is solved from 24 digits of the
  first frames (one solution each).
- **Every frame is followed.** 1,548 of 1,554 all-rolling frames match at least 12 of their digits
  at the next stream position. Steps of 28 draws are dropped capture frames; steps below 14 are
  frames where digits have started to lock.
- **Consecutive screens chain:** they are **18,142 – 117,472 draws apart** (median 59,168; 29 of 29
  pairs). That is one stage of play plus menus. Two unrelated 64-bit states would be about 10^19
  apart.

### Confirmation 2: story-mode letters give seeds that chain (`musl_letters.py`)

- **Seed search:** a 64-bit lattice over each entry's letter speeds. The per-entry speed offset
  cancels in differences, as in `lattice.search`. Candidates are ranked by chi-square.
- **Chaining:** the exact LCG distance (PCG's advance-distance algorithm) between consecutive
  seeded entries.

| run | clean entries | seeds | consecutive seeded pairs that chain | gaps (draws) |
|---|---|---|---|---|
| tcbtrio (Switch USA) | 52 | 40 | **39 / 39** | 3,024 – 942,595 |
| Jirazee (Switch USA) | 31 | 28 | **19 / 27** (23 entries confirmed by a neighbour) | 2,492 – 1,686,368 |

- **Gaps:** the same scale as GC, where everything is under 422k between sublevels. The 943k gap is
  GK-5 → SCx-1, with a day in between.
- **Jirazee's 8 broken links** all involve one of six weak entries, where the best state is barely
  ahead of the runner-up among 80–1,800 in the box: 11–12 letter BK names, a WFG name read with 13
  of 17 letters, and a GK fit with chi-square 58,604. Chaining from the good neighbours (as
  `chain.py` does) would settle them. The 1.7M gap is GK → SCx, across about 20 entries the
  detector missed in that run.
- **No ambiguity on tcbtrio:** most seeded entries have a single state in the box. Where there are several, the
  runner-up's chi-square is 2–10 times worse.
- **12 tcbtrio entries fail:** "too many states" or "no state" for all 7 SH entries (few letters),
  3 in WFG, 1 in GK and 1 in FC. They can be filled in from their neighbours by chaining, as
  `chain.py` does on GC.
- **Fit quality:** chi-square is about the letter count for short names, but twice that for the
  17–19 letter names (WFG, SCx). So σ is somewhat underestimated on long names; they chain all the
  same.

### What this means

- **Seeds can be read on Switch,** from story letters and from Challenge Mode rolls, with the same
  methods as GC. Only the generator changes.
- **Layouts:** cave generation calls the same `rand()`. So a Switch layout is the GC algorithm
  driven by this generator, with randFloat at 31-bit instead of 15-bit resolution. CaveGen supports
  only the GC generator, so it needs a Switch mode before these seeds give layouts. Not checked
  here.
- **Seeding:** with musl, `srand(x)` sets the state to x − 1. If the port still seeds from a 32-bit
  tick at boot, the start state is below 2^32, and the distance to a run's first seed would be the
  number of draws since boot. Not tested.

## Next steps, if Switch seeds are wanted

1. **Done: a Switch generator mode in the pipeline.** `rng.use("switch")` switches `rng.py` to
   the 64-bit musl LCG (stepping, exact distances, letter speeds), `lattice.search` to a 64-bit
   box (up to 16 letters), and `search_near`, `chain.link` and `layout_seed` follow. Seeds are
   written as 16 hex digits and `seeds.json` records `meta.rng`. `p2seeds analyze --rng switch`
   selects it; `p2seeds run` picks it from the run's platform. Re-searching tcbtrio's saved fits this way
   (`research_switch.py`): 36 high-confidence entries from the letters alone, **51 of 55 after
   `chain.link`**, 46 confirmed by the previous sublevel (largest gap 377,123 draws). Left out:
   2 entries with no seed, 1 medium, 1 low. Tests: `p2seeds/tests/test_switch_rng.py`.
2. **Done: the same mode in CaveGen3** (its branch `claude/switch-rng`): `Generator::Switch` in
   `rng.rs` (`randFloat` = `(f32)rand() / 2^31`, the game's `rand.h` arithmetic with the native
   `RAND_MAX`), `Layout::generate_with`, `cavegen3 ... --rng switch` for pictures and `judge`, and
   `"rng": "switch"` in p2seeds' bridge. p2seeds draws, judges and counts treasures for Switch
   runs when both are built (`cavegen.switch_ready()`); Java CaveGen stays GC only. Every vanilla
   sublevel generates Switch layouts without error. **Not yet checked against the game:** no
   Switch layout has been compared with video. The Challenge Mode floor-1s, or a story sublevel
   with a varied map, are the place to start. One guess to check there: on Switch `(f32)rand()`
   can round to 2^31, so `randInt(n)` can return n (about 1 call in 2^25); CaveGen3 clamps it.
3. **Challenge Mode reader:** decode Switch score rolls in `challenge_results` with the musl
   digit formula (`musl_rolls.py` has it), once that branch is merged.

## Reproduce

```bash
export PYTHONPATH=p2seeds/src          # this checkout's code (the venv's editable install may point elsewhere)
python -m srcom_videos download --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=Switch" \
    --top 10 --region USA --out data/switch/videos --height 480 --fps 60
python docs/switch/run_fast.py data/switch/videos/04_tcbtrio_z194e07m.mp4 data/switch/out/04_tcbtrio
python docs/switch/summarize.py "GC=data/output/12_tcbtrio_y64e4x0m/fits.json" "Switch=data/switch/out/04_tcbtrio/fits.json"
python docs/switch/variants.py data/output/12_tcbtrio_y64e4x0m/fits.json data/switch/out/04_tcbtrio/fits.json
python docs/switch/probe.py data/switch/videos/04_tcbtrio_z194e07m.mp4 34,0,606,320 23300 23420 data/switch/probe_fits.json
python -u docs/switch/brute.py data/switch/probe_fits.json
# section 7 (dump_digits.py needs p2seeds.challenge_results from claude/challenge-mode-seeds-37abaa)
python docs/switch/dump_digits.py cmal01_tcbtrio_switch_usa.mp4 data/switch/digits/cmal01_switch.json
python docs/switch/rng_candidates.py selftest
python docs/switch/rng_candidates.py data/switch/digits/cmal01_switch.json --screens 0,4,5,6,7,9
python docs/switch/rng_candidates.py data/switch/digits/cmal01_switch.json --screens 0,4,5 --windows 2 --only xorshift --gaps 0-40
python docs/switch/musl_rolls.py data/switch/digits/cmal01_switch.json
python docs/switch/musl_letters.py data/switch/out/04_tcbtrio/fits.json
python docs/switch/stern.py data/output/12_tcbtrio_y64e4x0m/fits.json        # GC control: finds 0x41C64E6D
python docs/switch/stern.py data/switch/out/04_tcbtrio/fits.json --lo 16
# the pipeline's Switch mode
python docs/switch/research_switch.py data/switch/out/04_tcbtrio     # saved fits, no video
python -m p2seeds analyze data/switch/videos/04_tcbtrio_z194e07m.mp4 --out data/switch/out/04_tcbtrio_full --rng switch
```
