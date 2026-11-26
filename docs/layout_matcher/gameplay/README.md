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
