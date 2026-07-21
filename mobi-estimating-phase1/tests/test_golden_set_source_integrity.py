"""Golden Set source-registry and tracked-artifact integrity checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "data" / "golden_set"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_registered_golden_set_artifacts_match_source_and_manifest_hashes():
    sources = json.loads((GOLDEN_ROOT / "sources.json").read_text(encoding="utf-8"))["records"]
    source_by_project = {row["project_id"]: row for row in sources}
    manifest = json.loads((GOLDEN_ROOT / "manifest.real-v1.json").read_text(encoding="utf-8"))["projects"]

    checked = 0
    for project in manifest:
        expected = project.get("document_sha256")
        if not expected:
            continue
        source = source_by_project[project["project_id"]]
        paths = project.get("document_paths") or []
        assert len(paths) == 1, project["project_id"]
        artifact = GOLDEN_ROOT / paths[0]
        actual = _sha256(artifact)
        assert source["document_path"] == paths[0]
        assert source["sha256"] == expected
        assert actual == expected
        checked += 1

    assert checked > 0
