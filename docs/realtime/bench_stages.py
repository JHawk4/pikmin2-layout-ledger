"""Min-of-3 timing of each stage on a settled entry (robust to a busy machine). See docs/realtime-obs.md.

    python docs/realtime/bench_stages.py data/output/RUN FRAME [FRAME ...]
"""
import json, sys, time
from pathlib import Path
import numpy as np
from p2seeds.story import analyze, lattice
from p2seeds.story.calibrate import calibrate
from p2seeds.caves import CAVES
from p2seeds.feed import Feed
from p2seeds.story.fit import fit
from p2seeds.story.track import track_all
from p2seeds.video import Video


def best(fn, n=3):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); out = fn(); ts.append(time.perf_counter() - t)
    return out, min(ts)


run = Path(sys.argv[1]); d = json.loads((run / "seeds.json").read_text())
feed = Feed(*d["meta"]["feed"])
pod = [c for c in CAVES if c.cavegen in analyze.POD_CAVES and c.lang == "en"]
with Video(d["meta"]["video"]) as v:
    for f in map(int, sys.argv[2:]):
        frames = [feed.crop(g) for g in v.frames(f - 300, f + 40)]
        a, b = analyze.entry_runs(frames)[-1]
        k = max(a, b - 3)
        cal_all, t_all = best(lambda: calibrate(frames[k]))
        cal, t_pod = best(lambda: calibrate(frames[k], caves=pod))
        clip = frames[a - analyze.FALL_LEAD: a + analyze.FALL_TAIL]
        (fall, times), t_gt = best(lambda: analyze.game_times(clip))
        raw, t_trk = best(lambda: track_all(fall, cal))
        from dataclasses import replace
        tracks = [replace(t, frames=analyze.to_time(t.frames, times)) for t in raw]
        fr, t_fit = best(lambda: fit(tracks, cal.cave.num_chars, s_guess=feed.height / 480))
        c, t_srch = best(lambda: lattice.search(fr.v, fr.sigma))
        _, t_chk = best(lambda: [analyze.is_entry_screen(x) for x in frames[:60]])
        print(json.dumps(dict(frame=f, cave=cal.cave.cavegen, feed=f"{feed.width}x{feed.height}",
              calibrate_all=round(t_all, 3), calibrate_pod=round(t_pod, 3), game_times=round(t_gt, 3),
              track=round(t_trk, 3), fit=round(t_fit, 3), lattice=round(t_srch, 4),
              check_ms=round(1000 * t_chk / 60, 2), letters=int(np.sum(np.isfinite(fr.v))),
              seed=f"0x{c[0].letter_seed:08X}" if c else None, frames_after_land=analyze.FALL_TAIL,
              settled_s=round((b - a) / v.fps, 2))), flush=True)
