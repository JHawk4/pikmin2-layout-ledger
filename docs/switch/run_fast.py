"""Run the story pipeline on a Switch video with a capped seed search.

On Switch no seed fits, so the normal search retries every leave-one/two-out subset with big
node budgets and one entry screen takes many minutes. This caps the lattice budget, skips the
retries and keeps everything else (calibration, tracking, fit, timing variants) unchanged, so
the fits are recorded (fits.json) and can be tested against RNG variants offline.

    python docs/switch/run_fast.py VIDEO OUT_DIR
"""

import sys
from pathlib import Path

from p2seeds.story import analyze, lattice
from p2seeds import cli

_orig = lattice.search


def _capped(*a, **kw):
    kw["max_nodes"] = min(kw.get("max_nodes", 20_000), 20_000)
    return _orig(*a, **kw)


lattice.search = _capped
_search = analyze._search
analyze._search = lambda f, search_kw=None, retries=True: _search(f, search_kw, retries=False)
# the one-frame timing-step refits each search again (up to 40 per variant); off, as they only
# rescue seeds on captures with a dropped frame
analyze._fit_with_step = lambda *a, **k: []

if __name__ == "__main__":
    video, out = sys.argv[1], Path(sys.argv[2])
    cli.run_video(video, out, render=False)
