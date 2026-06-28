"""Deterministic extraction result cache (cost control).

Cache reuse requires an exact match on project, the set of source page checksums,
trade code, provider, model, prompt version, trade-schema version, and
provider-schema version. Any change to source content or versions yields a new key,
so the cache self-invalidates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtractionCacheKey:
    project_id: str
    trade_code: str
    provider: str
    model: str
    prompt_version: str
    trade_schema_version: str
    provider_schema_version: str
    page_checksums: tuple[str, ...]

    def digest(self) -> str:
        payload = json.dumps(
            {
                "project_id": self.project_id,
                "trade_code": self.trade_code,
                "provider": self.provider,
                "model": self.model,
                "prompt_version": self.prompt_version,
                "trade_schema_version": self.trade_schema_version,
                "provider_schema_version": self.provider_schema_version,
                "page_checksums": sorted(self.page_checksums),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ExtractionCache:
    """Process-local cache of raw provider responses keyed by content + versions."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def clear(self) -> None:
        self._store.clear()

    def get(self, key: ExtractionCacheKey) -> dict[str, Any] | None:
        return self._store.get(key.digest())

    def set(self, key: ExtractionCacheKey, value: dict[str, Any]) -> None:
        self._store[key.digest()] = value


extraction_cache = ExtractionCache()
