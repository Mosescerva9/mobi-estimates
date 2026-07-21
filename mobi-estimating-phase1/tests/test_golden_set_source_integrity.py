"""Golden Set source-registry and tracked-artifact integrity checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "data" / "golden_set"
GOLDEN_V2_ROOT = Path(__file__).resolve().parents[1] / "data" / "golden_set_v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_registered_golden_set_artifacts_match_source_and_manifest_hashes():
    sources = json.loads((GOLDEN_ROOT / "sources.json").read_text(encoding="utf-8"))["records"]
    source_by_path = {row["document_path"]: row for row in sources}

    checked = 0
    for manifest_name in ("manifest.real-v1.json", "manifest.release-v1.json"):
        manifest = json.loads((GOLDEN_ROOT / manifest_name).read_text(encoding="utf-8"))["projects"]
        for project in manifest:
            paths = project.get("document_paths") or []
            expected_by_path = project.get("document_sha256s") or {}
            if not expected_by_path and len(paths) == 1 and project.get("document_sha256"):
                expected_by_path = {paths[0]: project["document_sha256"]}
            assert set(expected_by_path) == set(paths), project["project_id"]
            for relative_path in paths:
                source = source_by_path[relative_path]
                expected = expected_by_path[relative_path]
                artifact = GOLDEN_ROOT / relative_path
                actual = _sha256(artifact)
                assert source["project_id"] == project["project_id"]
                assert source["sha256"] == expected
                assert actual == expected
                checked += 1

    assert checked > 0


def test_v2_excluded_misattributed_sources_are_not_evaluation_inputs():
    sources = json.loads((GOLDEN_V2_ROOT / "sources.v2.json").read_text(encoding="utf-8"))["sources"]
    manifest = json.loads((GOLDEN_V2_ROOT / "manifest.real-v2.json").read_text(encoding="utf-8"))["projects"]
    evaluated_paths = {
        path
        for project in manifest
        for path in (project.get("document_paths") or [])
    }

    excluded = [row for row in sources if row.get("excluded_from_golden_set") is True]
    assert excluded
    for source in excluded:
        assert source["local_path"] not in evaluated_paths
        assert source["kind"] == "excluded_misattributed_artifact"
