"""Validator bookkeeping for the shared seed-hunt folder: set a board row's status and append a verdict.

    python docs/validator/board.py SUBLEVEL SEED verified|rejected|unsure "CHECKS" [--post P] [--files a,b] [--note "board note"]

Re-reads board.md right before writing and changes only the row of SUBLEVEL (status, seed, owner,
note), so edits by other sessions in between are kept.
"""
import datetime
import json
import os
import sys

HUNT = os.environ.get("CH_SEED_HUNT", r"C:\Users\Jordan\Desktop\Claude\ch-seed-hunt")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    sub, seed, verdict, checks = sys.argv[1:5]
    seed = seed.upper().replace("0X", "")
    note = arg("--note", checks[:160])
    files = [f for f in (arg("--files", "") or "").split(",") if f]
    path = os.path.join(HUNT, "board.md")
    lines = open(path, encoding="utf-8").read().split("\n")
    post = arg("--post")
    hit = None
    for i, ln in enumerate(lines):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 8 and cells[3] == sub and (post is None or cells[0] == post):
            post = post or cells[0]
            cells[4], cells[5], cells[6], cells[7] = f"{verdict} (validator)", seed, "validator", note.replace("|", "/")
            lines[i] = "| " + " | ".join(cells) + " |"
            hit = i
    if hit is None:
        sys.exit(f"no board row for {sub}")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    rec = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "validator": "hunt-validator",
           "post": int(post), "sublevel": sub, "seed": seed, "verdict": verdict, "checks": checks, "files": files}
    with open(os.path.join(HUNT, "verdicts.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("board row", hit, "->", verdict)


if __name__ == "__main__":
    main()
