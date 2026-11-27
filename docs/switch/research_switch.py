"""Re-search a run's saved letter fits (fits.json) with the Switch generator, through the
pipeline's own per-entry search (analyze._search: lattice + leave-out retries + confidence) and
chain.link, without re-reading the video. Prints each entry and the summary that `p2seeds
analyze --rng switch` would end with, and writes OUT/fits_switch.json.

    python docs/switch/research_switch.py data/switch/out/04_tcbtrio
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "p2seeds" / "src"))
from p2seeds.story import analyze, chain, letters_model
from p2seeds import rng  # noqa: E402


def main(out_dir):
    out_dir = Path(out_dir)
    rng.use("switch")
    results = chain.load(out_dir / "fits.json")
    for r in results:
        r.letter_seed = r.layout_seed = None
        r.candidates, r.confidence = [], "none"
        r.note = ", ".join(x for x in (r.note or "").split(", ") if x and x != "no seed matches")  # GC verdict
        if r.fit is None:
            continue
        cands, conf = analyze._search(r.fit)
        r.candidates, r.confidence = cands, conf
        if cands:
            r.letter_seed = cands[0].letter_seed
            r.layout_seed = letters_model.layout_seed(r.letter_seed, r.num_chars)
        print(f"{r.settled_frame:>7} {r.cave_id or '-':<4} {r.sublevel!s:<2} {conf:<6} {rng.seed_hex(r.layout_seed) or '-'}", flush=True)
    before = Counter(r.confidence for r in results)
    chain.link(results)
    after = Counter(r.confidence for r in results)
    print("\nper-entry search:", dict(before))
    print("after chain.link:", dict(after))
    linked = [r.chain_dist for r in results if r.chain_dist is not None]
    print(f"entries confirmed by the previous one (chain_dist): {len(linked)}, max {max(linked) if linked else '-'}")
    for r in results:
        print(f"  {r.settled_frame:>7} {r.cave_id or '-':<4} {r.sublevel!s:<2} {r.confidence:<6} "
              f"{rng.seed_hex(r.layout_seed) or '-':<20} {r.chain_dist if r.chain_dist is not None else ''} {r.note}")
    chain.dump(results, out_dir / "fits_switch.json")


if __name__ == "__main__":
    main(sys.argv[1])
