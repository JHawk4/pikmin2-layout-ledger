# Challenge Mode record seed hunt: finder tools (CH21–CH30)

Small tools used by hunt-finder-3. They sit on top of `docs/challenge_dive/` (dive reader,
results-roll reader) and `docs/layout_matcher/` (layoutmatch, comedown camera, pointscan).
Set `P2SEEDS_LAYOUTMATCH` to a built `layoutmatch.exe` when this checkout has none.

| tool | what it does |
|---|---|
| `wr_anchored.py CH SPAN` | the current grey dive reader on a record video, searching only states whose floor-1 seed lies within SPAN draws before the stage's results roll; prints the top candidates' floor-1 layout seeds. Runs at below-normal priority. |
| `variation.py SUB ...` | how much a sublevel varies, in the pod's frame: entropy of the whole layout and per object kind over N random seeds. Used to mark `skipped-low-variation` floors (CH30-4: every seed gives the same layout). |
| `hdframe.py VIDEO OUT FRAMES` | frames from an HD (1080p60/720p30) copy, cropped to the game area and scaled to 1280x720 (the size the comedown camera and pointscan use); `--sheet` for contact sheets. |
| `zoomgrid.py FRAME BOX OUT` | brightened, enlarged crop with a pixel grid labelled in source coordinates, for reading marks. |
| `rect.py FRAME H.json OUT` | rectify a frame to the pod's frame given a homography (or `--fit` one from hand pairs); `--seed` draws a layout on it. |
| `fit_cd.py SUB MARKS.json` | fit the comedown camera (zoom, turn, shift) by snapping marked objects to a sublevel's possible spots (`spots.py`). Works only with enough marks on discrete spots. |
| `hfit.py SUB OBS.json SEEDS` | per candidate seed, RANSAC homography from its objects to marks on any frame; reports marks explained. Weak alone: any seed fits 4 marks exactly, and fixed objects make random seeds fit more. |
| `overlay_pairs.py FRAME SUB SEED PAIRS OUT` | draw a seed's objects through a homography from a few hand pairs. |
| `specificity.py SUB END COUNT OBS.json` | how many seeds in a window share a set of observations (alone and together), to say how specific a matched candidate is. |

Fix on the roll reader (`p2seeds/challenge/results.py`, `process_run`): a results screen was
registered from its middle frame only; on the CH27 record that frame scored 0.79 (< 0.80) while
the rest of the roll scored 0.85–0.94, so the screen was dropped. It now tries frames across the
run and keeps the best registration. CH27's roll then decodes (9780 + 500 + 120 = 10,400, the
record's score).

Notes from the hunt:
- Gorei_50's comedown camera from the CH10 record (`comedown.ZOOM` 1.576, `TURN` −6.17) also
  lines up on CH29 and CH26 floor 1 in his other records.
- HD copies (yt-dlp `-f 299` or `bv*[height<=1080]`) make plants readable that are a few pixels
  at 360p; HD frame numbers at 60 fps are twice the 360p 30 fps numbers.
