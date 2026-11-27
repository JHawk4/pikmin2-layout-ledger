"""Re-read only the results screens a previous read_results.py run could not decode.

    python docs/wii/reread_failed.py VIDEO OLD.json NEW.json

Each failed screen is re-read on its own frame range (with blended-capture support), and the
merged list (old decoded entries kept) is written to NEW.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "p2seeds" / "src"))

from p2seeds.challenge_results import read_results  # noqa: E402


def main() -> None:
    video, old_path, new_path = sys.argv[1:4]
    old = json.load(open(old_path))
    done = {}
    if Path(new_path).exists():           # resume: keep screens already re-read
        done = {r["first_frame"]: r for r in json.load(open(new_path))["results"] if r.get("reread")}
    out = []
    for r in old["results"]:
        if r.get("decoded"):
            out.append(r)
            continue
        if r["first_frame"] in done:
            out.append(done[r["first_frame"]])
            continue
        t = time.time()
        res = read_results(video, start=max(0, r["first_frame"] - 30), end=r["last_frame"] + 30)
        new = res[0] if res else dict(r, note="screen not found again")
        new["reread"] = True
        print(r["first_frame"], new.get("decoded"), new.get("blended"), new.get("blend_gain"),
              new.get("note"), f"{time.time() - t:.0f}s", flush=True)
        out.append(new)
        Path(new_path).write_text(json.dumps(dict(old, results=out, decoded=sum(1 for x in out if x.get("decoded"))), indent=1))
    Path(new_path).write_text(json.dumps(dict(old, results=out, decoded=sum(1 for x in out if x.get("decoded"))), indent=1))


if __name__ == "__main__":
    main()
