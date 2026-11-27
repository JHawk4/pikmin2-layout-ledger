"""Read every Challenge Mode results-screen score roll in a video and print the RNG states.

    python docs/challenge_dive/read_results.py VIDEO [--frames] [--out FILE.json] [--start F --end F]

Prints a JSON list, one entry per results screen: first/last frame, the anchor frame and the
state of its first draw, the per-frame states (with --frames), the index and state of the last
draw of the roll, and a consistency note. See p2seeds/challenge_results.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# use this checkout's p2seeds (the editable install may point at another checkout)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "p2seeds" / "src"))

from p2seeds.challenge_results import read_results  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--frames", action="store_true", help="include the per-frame states")
    ap.add_argument("--out", help="also write the JSON here")
    ap.add_argument("--start", type=int, default=0, help="first video frame to scan")
    ap.add_argument("--end", type=int, help="stop scanning at this video frame")
    a = ap.parse_args()
    t = time.time()
    res = read_results(a.video, keep_frames=a.frames, start=a.start, end=a.end,
                       progress=lambda i, n: print(f"  frame {i}/{n}", file=sys.stderr, flush=True))
    summary = dict(video=Path(a.video).name, seconds=round(time.time() - t, 1), screens=len(res),
                   decoded=sum(1 for r in res if r.get("decoded")), results=res)
    text = json.dumps(summary, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text)


if __name__ == "__main__":
    main()
