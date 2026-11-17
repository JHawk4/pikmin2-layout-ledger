"""Print one sublevel's in-sample plays: outcome vs prediction residuals and layout parts."""
import sys, json
import common, evalkit as ek, model as M, numpy as np

sub = sys.argv[1]
prm = json.load(open(common.HERE / "data" / (sys.argv[2] if len(sys.argv) > 2 else "params_soft5.json")))
P = common.plays("in"); fe = ek.FE(P)
m = ek.metrics(P, M.preds(P, prm), fe=fe, by_sub=False)
m0 = ek.metrics(P, [p["judge"] for p in P], fe=fe, by_sub=False)
for k, p in enumerate(P):
    if p["sub"] != sub:
        continue
    v = p["J"]["layout"]["variants"][0]; L = p["J"]["layout"]
    tr = " ".join(f"{t['name']}[d{t['dist']:.0f} off{t['off_hole']:.0f} g{len(t['gates'])}{' w'+str(round(t['cross'])) if t['cross'] else ''}{' by '+t['carried_by'] if t['carried_by'] else ''}]" for t in L["treasures"] if t["kind"] == "counted")
    print(f"{p['runner'][:9]:9s} {p['layout_seed']} y{m['yr'][k]:+6.1f} new{m['xr'][k]:+6.1f} old{m0['xr'][k]:+6.1f} pk{p['pokos']:4d} | w{v['walking']:4.0f} c{v['carry']:4.0f} h{v['hazard']:4.0f} g{v['gate']:3.0f} a{v['adj']:3.0f} bug{v['bug']:3.0f} | hole d{L['hole']['dist']:.0f} g{len(L['hole']['gates'])} | {tr}")
