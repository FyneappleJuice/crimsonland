from __future__ import annotations

import json
from pathlib import Path

import pytest

from crimson.library_provenance import (
    load_library_provenance,
    validate_library_provenance,
)


def test_library_provenance_rejects_unknown_source_artifact(tmp_path: Path) -> None:
    payload = load_library_provenance()
    payload["artifacts"][0]["components"][0]["source_artifact"] = "missing-sdk"
    manifest = tmp_path / "library_provenance.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown source artifact"):
        load_library_provenance(manifest)


def test_library_provenance_reports_synced_file_drift(tmp_path: Path) -> None:
    payload = load_library_provenance()
    jpeg = next(source for source in payload["source_artifacts"] if source["id"] == "ijg-libjpeg-6a")
    jpeg["members"][0]["sha256"] = "00" * 32
    manifest = tmp_path / "library_provenance.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_library_provenance(manifest)

    assert any(
        check.artifact == "third_party/headers/jinclude.h"
        and check.kind == "source-member"
        and not check.passed
        for check in report.failed
    )
