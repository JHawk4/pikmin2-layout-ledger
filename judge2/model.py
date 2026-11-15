"""judge2 model: prediction for a play from its layout's take/skip variants.

score(variant) = w_walk*walking + w_carry*carry + w_haz*hazard + w_gate*gate + w_opt*optional
               + poko + w_bug*bug_term + w_adj*adj + cut*taken + water rule
prediction     = min over variants (the runner takes or skips each counted treasure),
                 or the all-taken variant when `decide` is off. With temp T > 0 it is the
                 average over variants weighted by exp(-score/T) (an uncertain choice).
The poko term keeps weight 1: the outcome counts pokos at exactly 2 per second.
bug_term: the old judge's bug-poko credit is -bug (pokos/2 the outcome never counts);
w_bug multiplies that credit (1 = old judge, 0 = no credit).
"""
import numpy as np

OLD = dict(w_walk=1, w_carry=1, w_haz=1, w_gate=1, w_opt=1, w_bug=1, w_adj=1, cut=10, decide=False,
           lens_water=None, scale=1.0, shrink=None)


def score(v, prm, sub):
    s = (prm["w_walk"] * v["walking"] + prm["w_carry"] * v["carry"] + prm["w_haz"] * v["hazard"]
         + prm["w_gate"] * v["gate"] + prm["w_opt"] * v["optional"] + v["poko"] - prm["w_bug"] * v["bug"]
         + prm["w_adj"] * v["adj"] + prm["cut"] * v["taken"])
    lw = prm.get("lens_water")
    if lw is not None and sub == "SH-6" and v["water_carry"] > 0 and "bey_goma" not in v["skipped"]:
        s += lw
    return s


def predict(p, prm):
    V = p["J"]["layout"]["variants"]
    if prm.get("decide"):
        sc = np.array([score(v, prm, p["sub"]) for v in V])
        T = prm.get("temp") or 0.0
        if T > 0:
            # the runner's choice is uncertain: weight each choice by exp(-score/T)
            w = np.exp(-(sc - sc.min()) / T)
            s = float(w @ sc / w.sum())
        else:
            s = float(sc.min())
    else:
        s = score(V[0], prm, p["sub"])
    return prm.get("scale", 1.0) * s


def preds(P, prm):
    return np.array([predict(p, prm) for p in P])
