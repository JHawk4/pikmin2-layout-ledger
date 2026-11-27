"""Add the layout matcher's Challenge Mode record seeds to the pikmin-wrs site's seeds.json.

    python docs/layout_matcher/site_seeds.py PATH/TO/pikmin-wrs/site/seeds.json

Entries are keyed by pik5 post id (the record run each seed was read from), like the dive reader's
entries from docs/challenge_dive/make_site_seeds.py; a stage listed here replaces that stage's
"unread" note. Run it again after regenerating seeds.json with make_site_seeds.py.
"""
import json
import sys

DOC = "https://github.com/JHawk4/pikmin2-layout-ledger/blob/claude/layout-matcher-f38181/docs/layout-matcher.md"

# (stage, pik5 post, rule, floor-1 layout seed, confirmed)
SEEDS = [
    (208, 19062, 22, "6A0AB9F5", False),
    (210, 17703, 22, "0E95D78F", True),
    (212, 20355, 21, "674C7FD3", False),
    (214, 18924, 22, "246C1C78", False),
    (220, 18495, 21, "5D221DD2", True),
    (224, 17612, 22, "5B21CDB6", False),
]

HOW = {
    True: {"en": "cave layout seen in the video, matched in CaveGen3 (confirmed)",
           "ja": "動画に映る地形をCaveGen3と照合（確認済み）"},
    False: {"en": "cave layout seen in the video, matched in CaveGen3 (strong match, not yet confirmed)",
            "ja": "動画に映る地形をCaveGen3と照合（有力・未確認）"},
}
HOW_SHORT = {"en": "matched to the cave layout seen in the video", "ja": "動画に映る地形と照合"}


def main():
    path = sys.argv[1]
    d = json.load(open(path, encoding="utf8"))
    posts = {post for _, post, _, _, _ in SEEDS}
    d["pikmin2"] = [r for r in d["pikmin2"] if r["post"] not in posts]
    for stage, post, rule, seed, ok in SEEDS:
        d["pikmin2"].append({
            "post": post, "rule": rule, "stage": stage,
            "floors": [{"sublevel": f"CH{stage - 200}-1", "seed": f"0x{seed}"}],
            "how": HOW[ok], "how_short": HOW_SHORT, "method": "layout", "verified": ok, "doc": DOC,
        })
        d.get("unread", {}).pop(str(stage), None)
    d["pikmin2"].sort(key=lambda r: r["stage"])
    d["_doc_layout"] = DOC
    json.dump(d, open(path, "w", encoding="utf8"), indent=1, ensure_ascii=False)
    print(f"{len(SEEDS)} layout-matcher seeds in {path}")


if __name__ == "__main__":
    main()
