"""A JSON record of which runs were fetched, from where, and where they landed on disk."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Run


class Manifest:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        if self.path.exists():
            self.entries = json.loads(self.path.read_text(encoding="utf-8")).get("runs", {})

    def update(self, run: Run, **fields) -> dict:
        entry = self.entries.setdefault(run.id, {})
        entry["run"] = run.to_dict()
        entry.update(fields)
        self.save()
        return entry

    def run(self, run_id: str) -> Run:
        return Run.from_dict(self.entries[run_id]["run"])

    def __iter__(self):
        return iter(self.entries.items())

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"runs": self.entries}, indent=2), encoding="utf-8")
        tmp.replace(self.path)
