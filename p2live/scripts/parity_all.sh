#!/usr/bin/env bash
# Run the Rust detector over every entry of every run and compare with the Python seeds.
#   p2live/scripts/parity_all.sh OUT_DIR [MAIN_CHECKOUT]
# writes OUT_DIR/<run>.jsonl per run; summarize with parity_summary.py OUT_DIR
set -u
out=${1:?out dir}
main=${2:-$(cd "$(dirname "$0")/../.." && pwd)}
exe="${P2LIVE_EXE:-$(dirname "$0")/../target/release/p2live.exe}"
mkdir -p "$out"
for s in "$main"/data/output/*/seeds.json "$main"/data/output_at/*/seeds.json; do
  run=$(basename "$(dirname "$s")")
  [ -f "$out/$run.done" ] && continue
  rm -f "$out/$run.jsonl"
  "$exe" entries "$s" --root "$main" --jobs "${JOBS:-4}" --out "$out/$run.jsonl" 2>"$out/$run.err" | tee -a "$out/summary.txt"
  touch "$out/$run.done"
done
