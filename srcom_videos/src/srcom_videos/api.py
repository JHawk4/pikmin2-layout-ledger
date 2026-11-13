"""Minimal read-only client for the speedrun.com REST API (v1).

Requests are rate limited (the API allows 100/minute), retried with backoff on
throttling or server errors, and cached on disk so repeated runs are offline.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://www.speedrun.com/api/v1"
DEFAULT_USER_AGENT = "srcom-videos/0.1 (research tool)"


class SrcomError(RuntimeError):
    pass


class SrcomClient:
    def __init__(
        self,
        cache_dir: str | Path | None = None,
        cache_ttl: float = 24 * 3600,
        min_interval: float = 0.7,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = 4,
        session: requests.Session | None = None,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_ttl = cache_ttl
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._last_request = 0.0

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        """GET `path` (relative to the API root) and return the decoded JSON."""
        url = path if path.startswith("http") else f"{BASE_URL}/{path.lstrip('/')}"
        params = {k: v for k, v in (params or {}).items() if v is not None}

        cache_file = self._cache_file(url, params)
        if cache_file and cache_file.exists():
            if time.time() - cache_file.stat().st_mtime < self.cache_ttl:
                return json.loads(cache_file.read_text(encoding="utf-8"))

        data = self._fetch(url, params)
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data), encoding="utf-8")
        return data

    def get_data(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.get(path, params)["data"]

    def _cache_file(self, url: str, params: dict) -> Path | None:
        if not self.cache_dir:
            return None
        key = url + "?" + json.dumps(params, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def _fetch(self, url: str, params: dict) -> dict:
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.time()
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise SrcomError(f"request failed: {url}: {exc}") from exc
            else:
                if resp.status_code == 200:
                    return resp.json()
                retryable = resp.status_code in (420, 429) or resp.status_code >= 500
                if not retryable or attempt == self.max_retries:
                    raise SrcomError(f"HTTP {resp.status_code} for {resp.url}: {resp.text[:200]}")
            time.sleep(delay)
            delay *= 2
        raise SrcomError(f"request failed: {url}")
