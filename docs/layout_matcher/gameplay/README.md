# Gameplay-frame layout checks (Challenge Mode records)

Gorei_50 and most Wii record runners play with the overhead camera, and it keeps the pod's heading
(screen up = the pod's `ahead`, right = `side`). A zoomed-out gameplay frame early in the stage then shows
most treasures before they are moved, so they can be read like the fly-over, without calibration.

Run from the worktree root. Set `P2SEEDS_LAYOUTMATCH` to a built layoutmatch.exe.
The scripts that read the record videos (sheet, grab, dark) default to the judge2 worktree's
`data/challenge/wr/`.

- `sheet.py VIDEO OUT START STEP [N COLS W]`: contact sheet with frame numbers. `grab.py VIDEO OUTDIR F...`: single frames.
- `dark.py VIDEO`: black stretches (floor transitions; the floor title follows).
- `fam.py SUB SEED [R]`: a seed's neighbours +-R draws, and how many objects each shares with it.
- `scan.py SUB END COUNT OBS.json OUT.bin`: layoutmatch scan over k draws before END; survivors per
  observation and the seeds passing all / all-but-one.
- `afit.py SUB PTS.json SEED...`: per seed, assigns each marked pixel to the nearest object of its type and
  fits a homography (pod frame -> pixels); prints the RMS. The seed whose objects all fit wins; this separates
  seeds that pass the coarse scan.
- `ovl.py SUB FRAME OUT CX CY SCALE SEED...`: draws seeds' objects on a frame with a simple top-down mapping.

Worked example (CH16 record, `obs/ch16_wr_*`): 7 cookies read off frame 770 -> scan k 0-1M -> the dive read +1
(785B61C7, k = 23,692) is the only rate-plausible seed with 6/7, and fits at RMS 23 px against >= 40 px for
every seed passing 7/7 (all at implausible draw rates).

## simfit (free-camera fit, no calibration)

`simfit.py SUB PTS.json (--seeds A,B | --end HEX --lo K --hi K) [--comedown ZOOM,TURN] [--scale lo,hi] [--tol px]`
marks typed objects on one frame (1280x720 pixels; `gridf.py VIDEO FRAME OUT` draws a labelled grid; "pod" is a valid
name). Per seed it tries every assignment of the two rarest marks, solves rotation/scale/shift, refines by least squares
and counts marks within `--tol` of an object of their kind. With `--comedown` the marks are first unprojected through
CaveGen3's comedown camera, so the fit only absorbs the comedown's zoom/turn/shift error. `--save` keeps every seed with
`--min-save` inliers (to intersect with another frame via `--seeds`); `--overlay FRAME,OUT` draws the best seed.
`where.py SUB PTS SEED X,Y...` says what a fitted seed has at other pixels.

- Gorei's overhead camera is ~0.9 px per game unit at 1280x720 (CH12-1, CH12-3, CH18: 0.83-0.94), so `--scale 0.7,1.15`.
- Checks: CH12-1's known seed wins on a gameplay frame (7/7 marks, next 4/7) and on its comedown (9/10, next 7/10).
- Result: CH12-2 of the CH12 record = 661950CA, 35/35 comedown plant marks at 10.8 px RMS (next 15/35); verified.
- Speed: ~60 seeds/s with 4 processes (`SIMFIT_PROCS`); dumping the layouts dominates. Use the Rust `scan.py` first
  when the camera can be guessed (pod-facing, scale 0.9), then simfit the survivors.
- Pitfalls: low-variation floors (CH12-3: 18 seeds share the pod room) need objects far from the pod; white balls in
  CH18's pipe ends are not eggs.

## rotscan (fast scan when the camera has been turned)

`rotscan.py SUB END_HEX COUNT PTS.json OUT.json [--rot-step 10] [--scales 0.8,1.0,1.2] [--tol 0.18] [--need N]`

Rotates/scales the marks about the "pod" mark for every camera turn and scale, runs the Rust `lm.scan` (~24 s per
1M seeds per pass) and keeps seeds with >= N marks. Feed OUT.json's seeds to simfit, which is stricter.
- CH12-3: picked 3998412E (k 33,120 before roll 0072844E) from the 18 candidates, using chess pieces on frames 4320 and 4440.
- CH18-1, frame 640 (pod, figwort, pipe treasure, egg, flame): 108 seeds out of 1M at 4/4, but the best simfit is 4/5
  with objects on empty floor. Those marks are not enough (or one is misread); more marks needed (see validator's typed_fit.py).
- Interpreter: use the main checkout's `.venv/Scripts/python.exe` and set `P2SEEDS_LAYOUTMATCH`; bare `python` here is
  an old interpreter.
