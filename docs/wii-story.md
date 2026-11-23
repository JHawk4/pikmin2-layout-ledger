# Story seeds from Wii runs

Question: can the seed pipeline read story-mode RNG seeds from the falling
cave-name letters in Wii (New Play Control!) Pikmin 2 runs, the way it does for
GameCube runs?

## Verdict: works with changes, and how well depends on the console

- **Real Wii: works.** The letter physics, the RNG and the draws per letter
  match GameCube exactly. kobachi's, s0rcius's and kiiltomaeki's real-Wii Pay
  Off Debt runs gave **55, 55 and 56 high seeds**, about every sublevel entry.
  Every consecutive pair chains forward by a plausible number of RNG draws.
- **Wii U Virtual Console: mostly.** The seeds read are just as good: high
  confidence and chained. But the Wii U loads sublevels so quickly that on
  short loads the title is shown over a bright picture, cut to black before
  the letters land, or skipped. Two later fixes recover many of these
  (see "Second pass" below). JHawk4's run now gives 49 high seeds,
  CurtisDN_'s 43, HeartPiece's (PAL) 39 and Sbudiver's 37.
- **Japanese Wii: not yet.** mercysnow's run gives wrong seeds, so it is held
  back from the site.

Two layouts checked by eye against the video, by rendering the seed with
CaveGen3:
- Sbudiver EC 2, layout `0x4B76F429`: the ship at the end of a corridor, with the
  Spherical Atlas and pellet posies beside it.
- kobachi WFG 1, `0x34759EF6`: the ship in the round landing room, with a
  corridor north to a junction.

## Runs tested

All are Pay Off Debt runs with Console (PoD) = Wii on speedrun.com: the eight
with a YouTube video (ranks 1-8; ranks 9 and below have no usable video). The
`platform` field tells real Wii from Wii U VC. All were downloaded at 360p,
30 fps. Counts are after the second pass.

| Run | Platform | High | Medium | Low | Consecutive seeds that chain |
|---|---|---|---|---|---|
| kobachi (RAUD8byyQyc) | Wii, USA | **55** | 0 | 0 | 54 / 54 |
| s0rcius | Wii, EUR | **55** | 0 | 0 | 54 / 54 |
| kiiltomaeki | Wii, EUR | **56** | 0 | 0 | 54 / 55 (FC 4 entered twice, after a reset; both chain to their neighbours) |
| JHawk4 (cVXsxZHt1G0) | Wii U VC, USA | **49** (was 43) | 0 | 0 | 48 / 48 |
| CurtisDN_ | Wii U VC, USA | **43** | 0 | 0 | 42 / 42 |
| HeartPiece | Wii U VC, EUR (PAL) | **39** | 2 | 0 | all but SH 2 (medium, wrong) |
| Sbudiver (WNylfiIY_AQ) | Wii U VC, USA | **37** (was 33) | 3 | 0 | all but GK 5 (medium, wrong) |
| mercysnow (7NzYrkLascs) | Wii U VC, JPN | 0 | 3 | 14 | 2 / 16: wrong, held back from the site |

- **Chaining**: from each seed to the next, the RNG must step forward by fewer
  than 2^22 draws. Real chains step forward 2.6k–580k draws: about 7 per frame
  in early sublevels and 20–50 per frame later. That is the same pace as
  GameCube runs, so the Wii game draws from the same RNG in the same way.
- Before these changes, the stock pipeline read only 6 seeds from Sbudiver's
  run, all in SCx. The long loads there hold the title for about 16 frames.

## What differs on Wii, and what changed

1. **16:9 stretch.** The whole 4:3 picture is stretched horizontally to 16:9,
   glyphs included. English names used to be fitted with the horizontal scale
   capped at the vertical one, so no cave scored above about 0.3. Now
   `calibrate` starts the horizontal scale at sy × 1.33 on wide feeds, and Wii
   names score 0.42–0.51 with a clear margin.
2. **The title fades about 10–15 frames after the last letter lands.**
   GameCube holds it much longer. Changes:
   - `events.normalize` rescales fading frames to full brightness.
   - On wide feeds, entry detection runs on normalized frames, with a finer
     scan step. The settled run only needs 3 frames instead of 6
     (`analyze.entry_runs_for`).
   - The cave is identified on several fading frames, keeping the best
     (`analyze.calibrate_fading`). All caves are checked on one frame and only
     the top two on the others, to keep it fast.
3. **Sublevel digit.** On the fading frames, a speck to the right of the digit
   was being read as the number. `digit_crop` now ignores groups shorter than
   0.4 of the line height.
4. **The same on Wii:**
   - entry-screen design (swirl and bubbles), font, and letter fall physics;
   - the RNG and the draws per letter;
   - the step from letter seed to layout seed (+ number of characters);
   - CaveGen layouts. No Wii-specific cave files turned up; CaveGen has an
     unused `wii` flag, and the rendered layouts match the video.
5. **Wii U VC only: the title is often not shown.** Examples:
   - Sbudiver's EC 1, entered from the surface, has no title at all.
   - In JHawk4's run, HoB 1 shows the name for about 40 frames and cuts to
     black while the letters are still in the air (frame 38918).
   - mercysnow's HoB/WFG entries go from black straight into
     the sublevel.

   No reading can recover a seed that isn't on screen. Kobachi's real Wii
   loads slowly enough that every title lands. (JHawk4's BK 3, first thought
   missing, had its title over a bright picture; the second pass reads it.)

## Main failure causes, in order

1. **(Wii U VC) No title, or the title is cut off before the letters land.**
   This accounts for nearly all the missing sublevels in the Wii U runs.
   A partial fall could still be fitted in principle: the letters are visible
   for about 20–40 frames, and the name could be inferred from the route. But
   the pipeline calibrates on a settled frame, so that is a larger project.
2. **(mercysnow, Japanese) Few titles, and the Japanese ones that do appear
   give wrong seeds.** The 14 low seeds do not chain, so they are wrong. Only
   two medium SCx seeds agree with each other. The Japanese fit (glyph pitch
   free, glyphs at their natural size) does not track the stretched Japanese
   letters well. This needs its own look, with letter boxes from `p2seeds debug`
   on a Japanese Wii entry.
3. **Slow runs.** Calibration on several fading frames costs about 10 s per
   entry on a busy machine. A full run takes roughly 1–2 hours. That is
   acceptable for a batch job.
4. **Rare misreads at medium**, e.g. Sbudiver GK 5 medium `0x54AA0501`, which
   does not chain (SH 1 chains straight from GK 4). The usual chain-based
   demotion handles them like on GameCube.

## Second pass: titles over a bright picture, and titles cut short

Looking at the Wii U sublevels still missing:

1. **A bright picture behind the title.** On quick loads the Wii U shows the
   title over the last gameplay frame (Pikmin, a light burst, flowers), not
   black. The entry-screen test required the top-middle and bottom bands to be
   almost black (under 0.5% bright pixels), so these were not entry screens at
   all. On fading frames it now allows 1.5% (`events.FADE_OUTSIDE`): gameplay
   HUD fills 20-35% of a row there, so this does not let gameplay through.
2. **The title cut short.** When the last letters have not landed, the cave
   name scores lower and the margin over the runner-up is small. On wide
   feeds, a rejected entry is now accepted as the cave just before or after it
   in the run, at score 0.40 and margin 0.02 (`analyze.rescue_caves`). A wrong
   guess fails the fit or the chain. JHawk4's HoB 2 and HoB 3 came back this
   way and chain to HoB 4.

Still missing: titles that are never shown, titles cut off very early, and
entries from the surface.

## On the site

Wii runs are a separate tab, **Pay Off Debt (Wii)**, under `wii/` (next to
`at/` for All Treasures), with their own runs, layouts, pokos and detection
pages. To rebuild:

```
python -m srcom_videos download --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=Wii" --top 8 --out data/wii_story/videos --height 480 --fps 30 --manifest ...
p2seeds batch --manifest ... --out data/output_wii --kind pod
p2seeds details data/output_wii/<run>        # each run's detection page
p2seeds site --root data/output_wii
p2seeds publish --root data/output --at-root data/output_at --wii-root data/output_wii
```

`data/output_wii/section.txt` holds `wii`, which tells the pages which tab
they belong to.

The tab shows only runs within 10 minutes of the Wii world record (1:38:29):
Sbudiver, kobachi and JHawk4. CurtisDN_, HeartPiece, s0rcius and kiiltomaeki
were analysed (numbers above) but are held back in `data/wii_story/held/`.
mercysnow's Japanese run is left out until the Japanese fit is fixed.

## Layouts checked against the comedown

For every high seed in the three runs on the site, the picture behind the
title was set beside CaveGen3's comedown render of the predicted layout
(`cavegen3 <sublevel> <seed> --view comedown --screen 16:9`). The comedown
is the game's still, nearly top-down shot of the pod's surroundings; its
framing matches the render, with the pod in the same screen position. Each
pair was compared for room outlines, corridor directions, holes and objects.

| Run | Entries | Match | Mismatch | Can't tell |
|---|---|---|---|---|
| JHawk4 (Wii U VC) | 49 | 23 | 0 | 26 |
| Sbudiver (Wii U VC) | 39 | 16 | 0 | 23 |
| kobachi (Wii) | 55 | 7 | 0 | 48 |

No layout disagrees with the video. Examples of matches: FC 3 (maze corridors
and rectangular holes line up), BK 3 (room arms and three objects at the
predicted spots), HoB 1 (the loop corridor's dark middle beside the pod).

Most "can't tell" pictures are black or show something else behind the title:
- On Wii U VC the title often sits over the previous sublevel's last frame
  (Olimar, flowers) instead of the comedown.
- On a real Wii the comedown shows 6-28 frames after the letters land and is
  lit only by the pod's own light (plus a flower-petal overlay), so little of
  the floor shows.
- Glutton's Kitchen's floor is lit everywhere, so no outlines stand out.

The chain check covers these entries: every high seed chains to its
neighbours, which a wrong seed does with a chance of about 1 in 1000.

Tool (not committed): `data/wii_story/comedown_sheets.py RUN_DIR OUT_DIR`.

## Still open

- Japanese Wii titles: 神 and 所 are not tracked, and only 3 of 5 letters
  fit. This needs a look with letter boxes from `p2seeds debug`.
- Fitting letters still falling when the title cuts out (Wii U VC). This needs
  calibration from the route plus geometry from another entry in the same video.

## Files

- Code: `p2seeds/src/p2seeds/{events,analyze,calibrate,debug}.py`
- Tests: `p2seeds/tests/test_wii.py`
- Data (not committed): `data/wii_story/`
  - `videos/` with its `manifest.json`;
  - `logs/` (per-run logs) and `out/` (seeds);
  - `verify/` (CaveGen renders next to video frames);
  - `chainchk.py` (chaining check from a log).
