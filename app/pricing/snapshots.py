"""Estimate pricing snapshots: normalized JSON + deterministic hashing.

A snapshot captures every effective input (scope, assemblies, rates, sources,
indirects, adjustments, versions, rounding policy). Re-pricing from the snapshot is
independent of the live database, so historical estimates remain reproducible even
after the live cost book changes. Snapshots contain no secrets.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.pricing.engine import PRICING_ENGINE_VERSION, ROUNDING_POLICY

# Keys that must never appear inside a snapshot (defensive secret-stripping).
_FORBIDDEN_KEYS = {"api_key", "openai_api_key", "password", "secret", "token"}


def _strip_secrets(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_secrets(v) for k, v in obj.items()
                if k.lower() not in _FORBIDDEN_KEYS}
    if isinstance(obj, list):
        return [_strip_secrets(v) for v in obj]
    return obj


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a secret-free snapshot with stable engine/rounding metadata."""
    clean = _strip_secrets(snapshot)
    clean.setdefault("pricing_engine_version", PRICING_ENGINE_VERSION)
    clean.setdefault("rounding_policy", ROUNDING_POLICY)
    return clean


def snapshot_json(snapshot: dict[str, Any]) -> str:
    """Deterministic, sorted JSON serialization of a snapshot."""
    return json.dumps(normalize_snapshot(snapshot), sort_keys=True,
                      separators=(",", ":"), default=str)


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(snapshot_json(snapshot).encode("utf-8")).hexdigest()


def validate_snapshot(snapshot: dict[str, Any]) -> list[str]:
    """Basic structural validation of a snapshot; returns a list of error strings."""
    errors: list[str] = []
    for required in ("scope_items", "assemblies", "currency", "pricing_date",
                     "cost_book_version_id"):
        if required not in snapshot:
            errors.append(f"snapshot missing '{required}'")
    if not isinstance(snapshot.get("scope_items", []), list):
        errors.append("scope_items must be a list")
    # No secret keys anywhere.
    def _scan(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in _FORBIDDEN_KEYS:
                    errors.append(f"snapshot contains forbidden key '{k}'")
                _scan(v)
        elif isinstance(obj, list):
            for v in obj:
                _scan(v)
    _scan(snapshot)
    return errors
