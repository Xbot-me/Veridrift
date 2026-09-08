"""File-based evidence store for persisting verification run data."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from guardrail.models.evidence import Evidence
from guardrail.models.run import VerificationRun
from guardrail.utils import GuardrailLogger

logger = GuardrailLogger.get_logger("evidence.store")


class EvidenceStore:
    """File-based evidence store for verification runs.

    Stores all evidence, findings, measurements, and run metadata
    in a structured directory hierarchy. Designed for reproducibility —
    every run's complete state can be reconstructed from stored files.

    Directory structure:
        <base_path>/
            <run-id>/
                run.json            # Full VerificationRun
                metadata.json       # Run metadata
                findings/
                    <finding-id>.json
                measurements/
                    <measurement-id>.json
                evidence/
                    <evidence-id>.json
                reports/
                    report.json
                    report.md
                    report.html
    """

    def __init__(self, base_path: str | Path = ".guardrail/runs") -> None:
        """Initialize the evidence store.

        Args:
            base_path: Root directory for storing evidence.
        """
        self.base_path = Path(base_path).resolve()

    def _run_dir(self, run_id: str) -> Path:
        """Get the directory path for a specific run."""
        return self.base_path / run_id

    def _ensure_dir(self, path: Path) -> Path:
        """Ensure a directory exists."""
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_run(self, run: VerificationRun) -> Path:
        """Save a complete verification run to disk.

        Args:
            run: The verification run to persist.

        Returns:
            Path to the saved run directory.
        """
        run_dir = self._ensure_dir(self._run_dir(run.id))

        # Save full run as single JSON
        run_file = run_dir / "run.json"
        run_file.write_text(
            run.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # Save metadata separately for quick access
        metadata_file = run_dir / "metadata.json"
        metadata_file.write_text(
            run.metadata.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # Save individual findings
        findings_dir = self._ensure_dir(run_dir / "findings")
        for finding in [*run.static_findings, *run.runtime_findings]:
            finding_file = findings_dir / f"{finding.id}.json"
            finding_file.write_text(
                finding.model_dump_json(indent=2),
                encoding="utf-8",
            )

        # Save individual measurements
        measurements_dir = self._ensure_dir(run_dir / "measurements")
        for measurement in run.measurements:
            meas_file = measurements_dir / f"{measurement.id}.json"
            meas_file.write_text(
                measurement.model_dump_json(indent=2),
                encoding="utf-8",
            )

        # Save individual evidence records
        evidence_dir = self._ensure_dir(run_dir / "evidence")
        all_evidence: list[Evidence] = []
        for finding in [*run.static_findings, *run.runtime_findings]:
            all_evidence.extend(finding.evidence)
        for ev in all_evidence:
            ev_file = evidence_dir / f"{ev.id}.json"
            ev_file.write_text(
                ev.model_dump_json(indent=2),
                encoding="utf-8",
            )

        # Create reports directory
        self._ensure_dir(run_dir / "reports")

        # Generate cryptographic SHA-256 manifest for all artifacts
        manifest: dict[str, str] = {}
        for p in run_dir.rglob("*"):
            if p.is_file() and p.name != "manifest.json":
                rel_p = str(p.relative_to(run_dir)).replace("\\", "/")
                content_bytes = p.read_bytes()
                manifest[rel_p] = hashlib.sha256(content_bytes).hexdigest()

        manifest_file = run_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        logger.info(
            "Saved verification run %s with %d hashed artifacts to %s",
            run.id,
            len(manifest),
            run_dir,
        )
        return run_dir

    def verify_manifest(self, run_id: str) -> tuple[bool, list[str]]:
        """Verify the integrity of a run against its stored SHA-256 manifest."""
        run_dir = self._run_dir(run_id)
        manifest_file = run_dir / "manifest.json"
        if not manifest_file.exists():
            return False, ["Manifest file not found"]

        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception as e:
            return False, [f"Corrupted manifest: {e}"]

        errors: list[str] = []
        for rel_path, expected_hash in manifest.items():
            target_file = run_dir / Path(rel_path)
            if not target_file.exists():
                errors.append(f"Missing file: {rel_path}")
                continue
            actual_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                errors.append(
                    f"Checksum mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}"
                )

        return len(errors) == 0, errors

    def load_run(self, run_id: str) -> VerificationRun | None:
        """Load a verification run from disk.

        Args:
            run_id: The ID of the run to load.

        Returns:
            The loaded VerificationRun, or None if not found.
        """
        run_file = self._run_dir(run_id) / "run.json"
        if not run_file.exists():
            logger.warning("Run %s not found at %s", run_id, run_file)
            return None

        try:
            data = json.loads(run_file.read_text(encoding="utf-8"))
            return VerificationRun.model_validate(data)
        except Exception:
            logger.exception("Failed to load run %s", run_id)
            return None

    def list_runs(self) -> list[dict[str, Any]]:
        """List all stored verification runs.

        Returns:
            List of run summaries with id, created_at, final_verdict, and target name.
        """
        runs: list[dict[str, Any]] = []

        if not self.base_path.exists():
            return runs

        for run_dir in sorted(self.base_path.iterdir()):
            if not run_dir.is_dir():
                continue
            run_file = run_dir / "run.json"

            if run_file.exists():
                try:
                    data = json.loads(run_file.read_text(encoding="utf-8"))
                    runs.append(
                        {
                            "id": data.get("id", run_dir.name),
                            "created_at": data.get("created_at"),
                            "final_verdict": data.get("final_verdict"),
                            "target_name": data.get("target", {}).get("name", "unknown"),
                            "schema_version": data.get("schema_version"),
                        }
                    )
                except Exception:
                    logger.warning("Could not read run at %s", run_dir)

        return runs

    def delete_run(self, run_id: str) -> bool:
        """Delete a stored verification run.

        Args:
            run_id: The ID of the run to delete.

        Returns:
            True if the run was deleted, False if not found.
        """
        run_dir = self._run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)
            logger.info("Deleted run %s", run_id)
            return True
        return False

    def save_report(self, run_id: str, content: str, format: str = "md") -> Path:
        """Save a report file for a verification run.

        Args:
            run_id: The run ID to save the report for.
            content: Report content.
            format: Report format ('json', 'md', 'html').

        Returns:
            Path to the saved report file.
        """
        reports_dir = self._ensure_dir(self._run_dir(run_id) / "reports")
        report_file = reports_dir / f"report.{format}"
        report_file.write_text(content, encoding="utf-8")
        logger.info("Saved %s report for run %s", format, run_id)
        return report_file

    def get_report_path(self, run_id: str, format: str = "md") -> Path | None:
        """Get the path to a stored report.

        Args:
            run_id: The run ID.
            format: Report format.

        Returns:
            Path to the report file, or None if not found.
        """
        report_file = self._run_dir(run_id) / "reports" / f"report.{format}"
        return report_file if report_file.exists() else None

    # ---------------------------------------------------------------- experiments

    def _experiment_dir(self, experiment_run_id: str) -> Path:
        return self.base_path / "experiments" / experiment_run_id

    def save_experiment(self, experiment_run) -> Path:
        """Persist a controlled experiment run and hash every artifact.

        Artifact layout (all under the existing EvidenceStore manifest scheme):
            experiment.json      # experiment definition + hypothesis + intervention
            preconditions.json   # precondition evaluation results
            control.json         # control condition observations
            treatment.json       # treatment condition observations
            observations/<id>.json
            comparison.json
            conclusion.json
            run.json             # full ExperimentRun (self-contained)
            manifest.json        # SHA-256 of every artifact above
        """
        from guardrail.experiment.models import ExperimentRun

        if not isinstance(experiment_run, ExperimentRun):
            raise TypeError(f"expected ExperimentRun, got {type(experiment_run).__name__}")
        exp_dir = self._ensure_dir(self._experiment_dir(experiment_run.id))

        payloads: dict[str, Any] = {
            "experiment.json": experiment_run.experiment.model_dump_json(indent=2),
            "preconditions.json": (
                "["
                + ", ".join(p.model_dump_json() for p in experiment_run.preconditions)
                + "]"
                if experiment_run.preconditions
                else "[]"
            ),
            "comparison.json": (
                experiment_run.comparison.model_dump_json(indent=2)
                if experiment_run.comparison
                else "null"
            ),
            "conclusion.json": experiment_run.conclusion.model_dump_json(indent=2),
            "run.json": experiment_run.model_dump_json(indent=2),
        }

        for name, content in payloads.items():
            (exp_dir / name).write_text(content, encoding="utf-8")

        obs_dir = self._ensure_dir(exp_dir / "observations")
        for obs in [*experiment_run.control_observations, *experiment_run.treatment_observations]:
            (obs_dir / f"{obs.id}.json").write_text(obs.model_dump_json(indent=2), encoding="utf-8")

        cond_dir = self._ensure_dir(exp_dir / "conditions")
        for label, observations in (
            ("control", experiment_run.control_observations),
            ("treatment", experiment_run.treatment_observations),
        ):
            path = cond_dir / f"{label}.json"
            path.write_text(
                json.dumps(
                    {
                        "condition": label,
                        "count": len(observations),
                        "observation_ids": [o.id for o in observations],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        manifest: dict[str, str] = {}
        for p in exp_dir.rglob("*"):
            if p.is_file() and p.name != "manifest.json":
                rel = str(p.relative_to(exp_dir)).replace("\\", "/")
                manifest[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        (exp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        logger.info(
            "Saved experiment %s with %d hashed artifacts to %s",
            experiment_run.id,
            len(manifest),
            exp_dir,
        )
        return exp_dir

    def load_experiment(self, experiment_run_id: str):
        """Load a persisted ExperimentRun, or None if missing/corrupt."""
        from guardrail.experiment.models import ExperimentRun

        run_file = self._experiment_dir(experiment_run_id) / "run.json"
        if not run_file.exists():
            return None
        try:
            data = json.loads(run_file.read_text(encoding="utf-8"))
            return ExperimentRun.model_validate(data)
        except Exception:
            logger.exception("Failed to load experiment run %s", experiment_run_id)
            return None

    def verify_experiment_manifest(self, experiment_run_id: str) -> tuple[bool, list[str]]:
        exp_dir = self._experiment_dir(experiment_run_id)
        manifest_file = exp_dir / "manifest.json"
        if not manifest_file.exists():
            return False, ["Experiment manifest file not found"]
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception as e:
            return False, [f"Corrupted experiment manifest: {e}"]
        errors: list[str] = []
        for rel_path, expected_hash in manifest.items():
            target_file = exp_dir / Path(rel_path)
            if not target_file.exists():
                errors.append(f"Missing file: {rel_path}")
                continue
            actual = hashlib.sha256(target_file.read_bytes()).hexdigest()
            if actual != expected_hash:
                errors.append(
                    f"Checksum mismatch for {rel_path}: expected {expected_hash}, got {actual}"
                )
        return len(errors) == 0, errors

    def list_experiments(self) -> list[dict[str, Any]]:
        """Summaries of all persisted experiment runs."""
        experiments: list[dict[str, Any]] = []
        root = self.base_path / "experiments"
        if not root.exists():
            return experiments
        for exp_dir in sorted(root.iterdir()):
            if not exp_dir.is_dir():
                continue
            summary: dict[str, Any] = {"id": exp_dir.name}
            for name in ("experiment.json", "conclusion.json"):
                f = exp_dir / name
                if f.exists():
                    try:
                        summary[name.removesuffix(".json")] = json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            experiments.append(summary)
        return experiments
