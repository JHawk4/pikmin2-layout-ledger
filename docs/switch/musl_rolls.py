"""Decode every Switch Challenge Mode score roll with the musl-style 64-bit LCG and track it.

Per screen: solve the state from the first all-rolling frames' digits (lattice, 24 digits), then
follow the roll frame by frame: each frame's 14 digits are matched at the next stream positions,
allowing for dropped capture frames (the next frame may start 14, 28, ... draws later, plus a few
extra draws). A frame counts as tracked when at least 12 of its readable digits match. Finally the
distance from each screen's state to the next screen's (draws in between) is computed exactly.

    python docs/switch/musl_rolls.py DIGITS.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from musl_letters import advance, distance  # noqa: E402
from rng_candidates import LCG, all_rolling_frames, frame_obs, screen_windows  # noqa: E402

G = LCG("musl", 6364136223846793005, 1, 1 << 64, 49)


def digits_from(s, n):
    out = []
    for _ in range(n):
        out.append((s >> 49) * 9 // 32768 + 1)
        s = (s * G.a + G.c) & ((1 << 64) - 1)
    return out


def main(path):
    screens = json.load(open(path))
    states = []
    for i, sc in enumerate(screens):
        fr = all_rolling_frames(sc)
        found = None
        for s, fit, chk in screen_windows(sc, 3):
            sols = G.solve(fit[:24])
            if sols and len(sols) == 1:
                found = (s, sols[0])
                break
        if not found:
            print(f"{i:>2} frames {sc['first']}-{sc['last']}: no solution", flush=True)
            states.append(None)
            continue
        s_idx, s0 = found
        # s0 = state after the first draw of frame s_idx; track the remaining all-rolling frames
        stream = digits_from(s0, 14 * 4 * len(fr) + 200)
        pos, tracked, total, extra = 0, 0, 0, []
        for t in range(s_idx, len(fr)):
            obs = frame_obs(fr[t], sc["n"], 0)
            if not obs:
                continue
            total += 1
            best = None
            lo = pos if t == s_idx else pos + 1
            for p in range(lo, min(len(stream) - 14, lo + 14 * 4 + 8)):
                m = sum(stream[p + q] == d for q, d in obs)
                if best is None or m > best[0]:
                    best = (m, p)
            if best[0] >= min(12, len(obs) - 1):
                tracked += 1
                if t > s_idx:
                    extra.append(best[1] - pos)
                pos = best[1]
        steps = sorted(set(extra))
        states.append((s0, s_idx))
        print(f"{i:>2} frames {sc['first']}-{sc['last']}: state {s0:#018x}; {tracked}/{total} all-rolling frames tracked;"
              f" draws between tracked frames: {steps}", flush=True)
    print("\ndraws from one screen's roll to the next screen's:")
    prev = None
    for i, st in enumerate(states):
        if st and prev:
            print(f"  screen {prev[2]:>2} -> {i:>2}: {distance(prev[0], st[0]):>22,}")
        if st:
            prev = (st[0], st[1], i)


if __name__ == "__main__":
    main(sys.argv[1])
