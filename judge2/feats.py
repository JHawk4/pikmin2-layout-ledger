"""Feature sets for lin.py: each returns (features, offset) for one variant."""
import json
import model as M

STATIC = {"hiba", "gashiba", "elechiba", "bomb", "rock"}


def chosen(P, prm):
    out = []
    for p in P:
        V = p["J"]["layout"]["variants"]
        out.append(min(V, key=lambda v: M.score(v, prm, p["sub"])) if prm.get("decide") else V[0])
    return out


def base(v, p, cut=10):
    f = {"walking": v["walking"], "carry": v["carry"], "hazard": v["hazard"], "gate": v["gate"], "adj": v["adj"]}
    off = v["poko"] + cut * v["taken"]
    if p["sub"] == "SH-6" and v["water_carry"] > 0 and "bey_goma" not in v["skipped"]:
        off += 100
    return f, off


def per_teki(v, p, min_n=None):
    f, off = base(v, p)
    del f["hazard"]
    for k, s in v["haz_by"].items():
        f["haz:" + k] = s
    return f, off


def classes(v, p):
    f, off = base(v, p)
    hb = v["haz_by"]
    f["hazard"] = sum(s for k, s in hb.items() if k not in ("elechiba", "bomb"))
    f["haz:elechiba"] = hb.get("elechiba", 0.0)
    f["haz:bomb"] = hb.get("bomb", 0.0)
    return f, off


def hole_split(v, p):
    f, off = base(v, p)
    f["walking"] = v["walking"] - v["hole_part"]
    f["hole_part"] = v["hole_part"]
    return f, off


def gate_split(v, p):
    f, off = base(v, p)
    f["gate"] = v["gate"] - v["gate_hole"]
    f["gate_hole"] = v["gate_hole"]
    return f, off


def bug_proxy(v, p):
    f, off = base(v, p)
    f["bug"] = v["bug"]
    return f, off


def carrier(v, p):
    f, off = base(v, p)
    f["carrier_fight"] = v["carrier_fight"]
    return f, off


def water_hole(v, p):
    f, off = base(v, p)
    f["water_hole"] = v["water_hole"] / 100
    return f, off


def hazard_hole(v, p):
    f, off = base(v, p)
    f["hazard_hole"] = v["hazard_hole"]
    return f, off


def hazard_all(v, p):
    """one hazard weight for teki on treasure routes and on the hole route"""
    f, off = base(v, p)
    f["hazard"] = v["hazard"] + v["hazard_hole"]
    return f, off
