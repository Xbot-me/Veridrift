from __future__ import annotations

import json
from pathlib import Path

from guardrail.evidence.store import EvidenceStore
from guardrail.models.run import VerificationRun


def test_manifest_generation_and_integrity_check(sample_run: VerificationRun, tmp_path: Path):
    store = EvidenceStore(base_path=tmp_path)
    run_dir = store.save_run(sample_run)

    manifest_file = run_dir / "manifest.json"
    assert manifest_file.exists()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert len(manifest) > 0
    assert "run.json" in manifest
    assert "metadata.json" in manifest

    # Verification should pass
    valid, errors = store.verify_manifest(sample_run.id)
    assert valid is True
    assert len(errors) == 0


def test_manifest_detects_tampering(sample_run: VerificationRun, tmp_path: Path):
    store = EvidenceStore(base_path=tmp_path)
    run_dir = store.save_run(sample_run)

    # Tamper with run.json
    run_file = run_dir / "run.json"
    content = run_file.read_text(encoding="utf-8")
    run_file.write_text(content + "   ", encoding="utf-8")

    # Verification must fail
    valid, errors = store.verify_manifest(sample_run.id)
    assert valid is False
    assert any("Checksum mismatch" in e and "run.json" in e for e in errors)


def test_manifest_detects_deleted_file(sample_run: VerificationRun, tmp_path: Path):
    store = EvidenceStore(base_path=tmp_path)
    run_dir = store.save_run(sample_run)

    # Delete metadata.json
    meta_file = run_dir / "metadata.json"
    meta_file.unlink()

    # Verification must fail
    valid, errors = store.verify_manifest(sample_run.id)
    assert valid is False
    assert any("Missing file" in e and "metadata.json" in e for e in errors)
