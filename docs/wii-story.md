# Story seeds from Wii runs

Question: can the seed pipeline read story-mode RNG seeds from the falling
cave-name letters in Wii (New Play Control!) Pikmin 2 runs, the way it does for
GameCube runs?

## Verdict: works with changes, and how well depends on the console

- **Real Wii: works.** The letter physics, the RNG and the draws per letter
  match GameCube exactly. With the changes on this branch, kobachi's real-Wii
  Pay Off Debt run gave **55 high seeds**, about every sublevel entry in the
  run. Every one of the 54 consecutive pairs chains forward by a plausible
  number of RNG draws.
- **Wii U Virtual Console: partly.** The seeds read are just as good: high
  confidence and chained. But the Wii U loads sublevels so quickly that on most
  short loads the title card is cut to black before the letters land, or never
  shown at all. Those entries simply carry no seed. JHawk4's run gave 43 high
  seeds and Sbudiver's 33. mercysnow's Japanese run gave almost nothing usable
  (table below).

Two layouts checked by eye against the video, by rendering the seed with
CaveGen3:
- Sbudiver EC 2, layout `0x4B76F429`: the ship at the end of a corridor, with the
  Spherical Atlas and pellet posies beside it.
- kobachi WFG 1, `0x34759EF6`: the ship in the round landing room, with a
  corridor north to a junction.

## Runs tested

All four are Pay Off Debt runs with Console (PoD) = Wii on speedrun.com. The
`platform` field tells real Wii from Wii U VC. All were downloaded at
640x360, 30 fps.

| Run | Platform | Entry candidates | Names read | High | Medium | Low | Failed | Consecutive seeds that chain |
|---|---|---|---|---|---|---|---|---|
| kobachi (RAUD8byyQyc) | Wii, USA | 114 | 56 | **55** | 0 | 0 | 1 (fit) | 54 / 54 |
| JHawk4 (cVXsxZHt1G0) | Wii U VC, USA | 110 | 43 | **43** | 0 | 0 | 0 | 42 / 42 |
| Sbudiver (WNylfiIY_AQ) | Wii U VC, USA | 121 | 41 | **33** | 3 | 0 | 5 (fit) | 34 of 35 high/medium seeds fit one chain (GK 5 medium is wrong) |
| mercysnow (7NzYrkLascs) | Wii U VC, JPN | 130 | 21 | 0 | 3 | 14 | 4 (fit) | 2 / 16 (only SCx 3 to 6, both medium; the low seeds are wrong) |

- **Entry candidates** are the dark screens the detector flags. Most of the ones
  not read are fades with no title on them: deaths, menus, cutscenes, and Wii U
  entries whose title never showed.
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
   - JHawk4's BK 3 and mercysnow's HoB/WFG entries go from black straight into
     the sublevel.

   No reading can recover a seed that isn't on screen. Kobachi's real Wii
   loads slowly enough that every title lands.

## Main failure causes, in order

1. **(Wii U VC) No title, or the title is cut off before the letters land.**
   This accounts for nearly all the missing sublevels in the three Wii U runs.
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

## What it would take to add Wii runs to the site

- Download Wii PoD runs:
  `python -m srcom_videos download --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=Wii" ...`
  Keep `platform` from the run so real Wii and Wii U VC can be labelled (and
  their coverage explained).
- Run `p2seeds analyze` as for GameCube (English runs; hold back Japanese Wii runs until cause 2 is fixed). Wide feeds are detected from the feed
  shape, so no flag is needed. Japanese runs need region JPN, as on GameCube.
- Layouts render with the existing CaveGen3 builds; the judge and the layout
  spread work on the seeds unchanged.
- Decide how to show Wii U VC runs: whole runs will have gaps, so per-sublevel
  stats are fine but "whole run" views should say how many entries had no title.
- Optional, bigger: fit seeds from letters that are still falling when the title
  cuts out (Wii U VC). This would need calibration from the route plus geometry
  from another entry in the same video.

## Files

- Code: `p2seeds/src/p2seeds/{events,analyze,calibrate,debug}.py`
- Tests: `p2seeds/tests/test_wii.py`
- Data (not committed): `data/wii_story/`
  - `videos/` with its `manifest.json`;
  - `logs/` (per-run logs) and `out/` (seeds);
  - `verify/` (CaveGen renders next to video frames);
  - `chainchk.py` (chaining check from a log).
