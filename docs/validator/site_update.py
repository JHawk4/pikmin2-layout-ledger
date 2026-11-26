"""Add or update a record's floor seeds in pikmin-wrs site/seeds.json (validator only).

    python docs/validator/site_update.py SEEDS.json POST RULE STAGE SUB=SEED[,SUB=SEED...] verified|unsure "VALIDATION NOTE"
           [--method layout|digits] [--rng switch] [--remove SUB,...] [--drop]

Floors are merged into the record's entry (same post), sorted by sublevel. An entry with any
unsure floor is kept as verified: false with the note; a verified entry takes the "confirmed"
wording. --remove drops floors (rejected seeds); --drop removes the whole entry. The stage's
"unread" note is removed while it has seeds.
"""
import json
import re
import sys

HOW = {
    ("layout", True): {"en": "cave layout seen in the video, matched in CaveGen3 (confirmed)",
                       "ja": "動画に映る地形をCaveGen3と照合（確認済み）"},
    ("layout", False): {"en": "cave layout seen in the video, matched in CaveGen3 (strong match, not yet confirmed)",
                        "ja": "動画に映る地形をCaveGen3と照合（有力・未確認）"},
    ("digits", True): {"en": "read from the on-screen digits and confirmed by the cave layout",
                       "ja": "画面の数字から読み取り、地形で確認済み"},
    ("digits", False): {"en": "read from the on-screen digits (not yet confirmed)",
                        "ja": "画面の数字から読み取り（未確認）"},
}
HOW_SHORT = {"layout": {"en": "matched to the cave layout seen in the video", "ja": "動画に映る地形と照合"},
             "digits": {"en": "read from the video's on-screen digits", "ja": "動画の数字から読み取り"}}
DOC = "https://github.com/JHawk4/pikmin2-layout-ledger/blob/claude/layout-matcher-f38181/docs/layout-matcher.md"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def subkey(s):
    m = re.match(r"CH(\d+)-(\d+)", s)
    return (int(m.group(1)), int(m.group(2))) if m else (999, 0)


def main():
    path, post, rule, stage = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    d = json.load(open(path, encoding="utf-8"))
    recs = d["pikmin2"]
    r = next((x for x in recs if x["post"] == post), None)
    if "--drop" in sys.argv:
        d["pikmin2"] = [x for x in recs if x["post"] != post]
    else:
        pairs, verdict, note = sys.argv[5], sys.argv[6], sys.argv[7]
        method = arg("--method", (r or {}).get("method", "layout"))
        if r is None:
            r = {"post": post, "rule": rule, "stage": stage, "floors": []}
            recs.append(r)
        floors = {f["sublevel"]: f for f in r.get("floors", [])}
        for p in [p for p in pairs.split(",") if p]:
            sub, seed = p.split("=")
            seed = seed.upper().replace("0X", "")
            f = {"sublevel": sub, "seed": "0x" + seed}
            if arg("--rng"):
                f["rng"] = arg("--rng")
            f["verified"] = verdict == "verified"
            floors[sub] = f
        for sub in (arg("--remove", "") or "").split(","):
            floors.pop(sub, None)
        r["floors"] = sorted(floors.values(), key=lambda f: subkey(f["sublevel"]))
        ok = all(f.get("verified", r.get("verified", False)) for f in r["floors"])
        r["verified"] = ok
        r["method"] = method
        r["how"] = HOW[(method, ok)]
        r["how_short"] = HOW_SHORT[method]
        r.setdefault("doc", DOC)
        r["validation"] = note
        if not r["floors"]:
            d["pikmin2"] = [x for x in recs if x["post"] != post]
    d["pikmin2"].sort(key=lambda x: x["stage"])
    if any(x["stage"] == stage for x in d["pikmin2"]):
        (d.get("unread") or {}).pop(str(stage), None)
    open(path, "w", encoding="utf-8", newline="\n").write(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    print("ok", post, [f["sublevel"] for f in (r or {}).get("floors", [])])


if __name__ == "__main__":
    main()
