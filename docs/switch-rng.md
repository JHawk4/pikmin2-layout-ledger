# Pikmin 2 on Switch (Pikmin 2 HD): can the letters give seeds, and is the RNG different?

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

## Next steps, if Switch seeds are ever wanted

1. Fit more Switch letter speeds and look for structure directly. For example, test whether
   consecutive speeds are linearly related mod 5, as for any LCG read through its high bits, or try
   a small-state search over xorshift and Mersenne Twister outputs with tempering.
2. Get the Switch `rand` from the game's code (a datamine of the recompiled module) instead of from
   video.

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
```
