#!/bin/sh
# Build p2seeds-cg3's layoutmatch binary into data/build/cg3lm/release/layoutmatch.exe.
# The crate finds CaveGen3 at ../../../cavegen3 (Desktop/Claude/cavegen3 from the main checkout).
# From a worktree that path doesn't resolve, so the crate is copied to a staging folder three
# levels below Desktop/Claude (the main checkout's data/cg3lm) and built from there.
set -e
HERE=$(cd "$(dirname "$0")/../.." && pwd)
MAIN=$(git -C "$HERE" worktree list --porcelain | sed -n '1s/^worktree //p')
STAGE="$MAIN/data/cg3lm"
mkdir -p "$STAGE"
cp -r "$HERE/p2seeds/cg3/Cargo.toml" "$HERE/p2seeds/cg3/Cargo.lock" "$HERE/p2seeds/cg3/src" "$STAGE/"
cd "$STAGE" && cargo build --release --bin layoutmatch --target-dir "$HERE/data/build/cg3lm"
