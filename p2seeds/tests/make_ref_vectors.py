"""Regenerate tests/data/seed_ref.json from CaveGen's Java code (needs vendor/CaveGen and a JDK)."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
CAVEGEN = ROOT / "vendor" / "CaveGen"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sources = sorted(CAVEGEN.glob("*.java")) + [HERE / "java" / "RefVectors.java"]
        subprocess.run(["javac", "-nowarn", "-encoding", "UTF-8", "-d", str(tmp), *map(str, sources)],
                       check=True, capture_output=True)
        out = subprocess.run(["java", "-cp", str(tmp), "RefVectors"], check=True, capture_output=True, text=True).stdout
    dest = HERE / "data" / "seed_ref.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(out)
    print(f"wrote {dest}", file=sys.stderr)


if __name__ == "__main__":
    if not shutil.which("javac"):
        sys.exit("javac not found")
    main()
