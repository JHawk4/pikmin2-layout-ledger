"""Load in-sample (or OOS) plays joined with judge2 layout dumps."""
import json
from pathlib import Path
import numpy as np
import evalkit as ek

HERE = Path(__file__).resolve().parent
_J = None


def judged():
    global _J
    if _J is None:
        _J = json.loads((HERE / "data" / "judged.json").read_text(encoding="utf-8"))
    return _J


def plays(side="in", valid_only=None):
    J = judged()
    P = ek.load_plays(side, valid_only)
    for p in P:
        p["J"] = J[f'{p["run"]}|{p["frame"]}']
    return P
