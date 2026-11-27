"""Dump every frame's digit readings of each Challenge Mode results screen, without decoding.

challenge_results.py decodes the roll with the GameCube RNG and keeps only final values when that
fails (as it does on every Switch screen). This keeps the raw readings so other generators can be
tested against them (see rng_candidates.py).

Needs p2seeds.challenge.results from branch claude/challenge-mode-seeds-37abaa on PYTHONPATH.

    python docs/switch/dump_digits.py VIDEO OUT.json

Output: a list of screens; each has the layout (digits per counter, in draw order pokos, pikmin,
time, total) and per frame: video index, dup flag (pixel-identical to the previous frame) and,
per counter, [digit, score, margin] from the ones digit up.
"""

from __future__ import annotations

import json
import sys

from p2seeds.challenge.results import COUNTERS, choose_layout, iter_screens, process_run, read_frame


def main(video: str, out: str) -> None:
    screens = []
    cache: dict = {}
    for buf in iter_screens(video, progress=lambda i, n: print(f"  frame {i}/{n}", file=sys.stderr, flush=True)):
        sc = process_run(buf, cache)
        if sc is None:
            continue
        sample = sc.canons[: max(3, len(sc.canons) // 2)]
        lay = choose_layout(sample[:: max(1, len(sample) // 8)][:8])
        frames = []
        for fr, cv in zip(sc.frames, sc.canons):
            r = read_frame(cv, lay)
            frames.append(dict(i=fr.index, dup=fr.dup,
                               d={c: [[int(d), round(float(v), 3), round(float(m), 3)] for d, v, m in r[c]]
                                  for c in COUNTERS}))
        screens.append(dict(first=sc.first_frame, last=sc.last_frame, n=lay.n, squeeze=lay.squeeze, frames=frames))
        print(f"screen {len(screens)}: frames {sc.first_frame}-{sc.last_frame} layout {lay.n}", file=sys.stderr, flush=True)
    json.dump(screens, open(out, "w"), indent=0)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
