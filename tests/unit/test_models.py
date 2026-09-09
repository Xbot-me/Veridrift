"""Unit tests for core data models."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from guardrail.models.base import (
    Confidence,
    EvidenceType,
    RuleCategory,
    Severity,
    ThresholdOperator,
    TrafficPattern,
    VerdictStatus,
    generate_id,
)
from guardrail.models.environment import (
    ContainerConfig,
    Environment,
    ResourceLimits,
)
from guardrail.models.measurement import (
    LatencyDistribution,
    Measurement,
    MeasurementValidity,
    RequestMetrics,
)
from guardrail.models.policy import Policy, PolicyThreshold
from guardrail.models.rule import Finding
from guardrail.models.run import VerificationRun
from guardrail.models.target import Target
from guardrail.models.verdict import Verdict
from guardrail.models.workload import AmplificationModel, WorkloadScenario, WorkloadStage


class TestEnums:
    """Test that all enums have correct values."""

    def test_severity_values(self) -> None:
        assert Severity.CRITICAL.value in ("critical", "CRITICAL")
        assert Severity.HIGH.value in ("high", "HIGH")
        assert Severity.MEDIUM.value in ("medium", "MEDIUM")
        assert Severity.LOW.value in ("low", "LOW")
        assert Severity.INFO.value in ("info", "INFO")
        assert len(Severity) == 5

    def test_confidence_values(self) -> None:
        assert Confidence.CONFIRMED.value in ("confirmed", "CONFIRMED")
        assert Confidence.LIKELY.value in ("likely", "LIKELY")
        assert Confidence.POSSIBLE.value in ("possible", "POSSIBLE")
        assert len(Confidence) == 3

    def test_verdict_status_values(self) -> None:
        assert VerdictStatus.PASS.value in ("pass", "PASS")
        assert VerdictStatus.WARNING.value in ("warning", "WARNING")
        assert VerdictStatus.FAIL.value in ("fail", "FAIL")
        assert len(VerdictStatus) == 4

    def test_evidence_type_values(self) -> None:
        assert EvidenceType.STATIC.value in ("static", "STATIC")
        assert EvidenceType.EMPIRICAL.value in ("empirical", "EMPIRICAL")
        assert EvidenceType.ESTIMATED.value in ("estimated", "ESTIMATED")

    def test_traffic_pattern_values(self) -> None:
        patterns = [p.value.lower() for p in TrafficPattern]
        assert "constant" in patterns
        assert "ramp" in patterns
        assert "burst" in patterns
        assert "spike" in patterns

    def test_rule_category_values(self) -> None:
        categories = [c.value.lower() for c in RuleCategory]
        assert "database" in categories
        assert "network" in categories
        assert "concurrency" in categories


class TestGenerateId:
    """Test ID generation."""

    def test_generates_unique_ids(self) -> None:
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100

    def test_id_is_string(self) -> None:
        assert isinstance(generate_id(), str)

    def test_id_is_nonempty(self) -> None:
        assert len(generate_id()) > 0


class TestTarget:
    """Test Target model."""

    def test_create_target(self, sample_target: Target) -> None:
        assert sample_target.name == "test-app"
        assert "python" in sample_target.languages
        assert "flask" in sample_target.frameworks
        assert len(sample_target.services) == 1
        assert len(sample_target.dependencies) == 1

    def test_target_serialization(self, sample_target: Target) -> None:
        json_str = sample_target.model_dump_json()
        data = json.loads(json_str)
        assert data["name"] == "test-app"
        assert "python" in data["languages"]

    def test_target_round_trip(self, sample_target: Target) -> None:
        json_str = sample_target.model_dump_json()
        restored = Target.model_validate_json(json_str)
        assert restored.name == sample_target.name
        assert restored.languages == sample_target.languages


class TestEnvironment:
    """Test Environment model."""

    def test_default_environment(self) -> None:
        env = Environment()
        assert env.name == "default"
        assert env.network_isolation is True
        assert env.cleanup_on_exit is True

    def test_resource_limits(self) -> None:
        limits = ResourceLimits(cpu_cores=4.0, memory_mb=2048, pids_limit=512)
        assert limits.cpu_cores == 4.0
        assert limits.memory_mb == 2048

    def test_container_config(self) -> None:
        config = ContainerConfig(
            image="postgres",
            tag="16",
            ports={5432: 5432},
            environment={"POSTGRES_PASSWORD": "test"},
        )
        assert config.image == "postgres"
        assert config.tag == "16"


class TestPolicy:
    """Test Policy model."""

    def test_default_policy(self) -> None:
        policy = Policy.default()
        assert policy.name == "default"
        assert len(policy.thresholds) >= 4

    def test_threshold_check(self) -> None:
        threshold = PolicyThreshold(
            metric="p95_latency_ms",
            operator=ThresholdOperator.LTE,
            value=500.0,
            severity=Severity.HIGH,
        )
        assert threshold.metric == "p95_latency_ms"
        assert threshold.value == 500.0


class TestFinding:
    """Test Finding model."""

    def test_create_finding(self, sample_finding: Finding) -> None:
        assert sample_finding.rule_id == "DB-001"
        assert sample_finding.severity == Severity.HIGH
        assert sample_finding.confidence == Confidence.LIKELY
        assert sample_finding.file_path == "app.py"
        assert sample_finding.line_number == 42

    def test_finding_has_evidence(self, sample_finding: Finding) -> None:
        assert len(sample_finding.evidence) > 0
        evidence = sample_finding.evidence[0]
        assert evidence.type == EvidenceType.STATIC

    def test_finding_serialization(self, sample_finding: Finding) -> None:
        json_str = sample_finding.model_dump_json()
        restored = Finding.model_validate_json(json_str)
        assert restored.rule_id == sample_finding.rule_id


class TestMeasurement:
    """Test Measurement model."""

    def test_create_measurement(self, sample_measurement: Measurement) -> None:
        assert sample_measurement.workload_rps == 100.0
        assert sample_measurement.request_metrics is not None
        assert sample_measurement.resource_metrics is not None
        assert sample_measurement.database_metrics is not None

    def test_latency_distribution(self, sample_measurement: Measurement) -> None:
        latency = sample_measurement.request_metrics.latency
        assert latency.p50_ms < latency.p95_ms
        assert latency.p95_ms < latency.p99_ms

    def test_valid_measurement(self, sample_measurement: Measurement) -> None:
        assert sample_measurement.validity == MeasurementValidity.VALID
        assert sample_measurement.validity_reasons == []

    def test_empty_measurement_is_insufficient_data(self) -> None:
        empty = Measurement(run_id="r", timestamp=datetime.now(UTC))
        assert empty.validity == MeasurementValidity.INSUFFICIENT_DATA

    def test_zero_request_measurement_is_insufficient_data(self) -> None:
        now = datetime.now(UTC)
        zero = Measurement(
            run_id="r",
            timestamp=now,
            request_metrics=RequestMetrics(
                timestamp=now,
                duration_seconds=1.0,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                requests_per_second=0.0,
                error_rate=0.0,
                latency=LatencyDistribution(p50_ms=0.0, p95_ms=0.0, p99_ms=0.0),
            ),
        )
        assert zero.validity == MeasurementValidity.INSUFFICIENT_DATA

    def test_inconsistent_counters_are_invalid(self) -> None:
        now = datetime.now(UTC)
        bogus = Measurement(
            run_id="r",
            timestamp=now,
            request_metrics=RequestMetrics(
                timestamp=now,
                duration_seconds=1.0,
                total_requests=100,
                successful_requests=99,
                failed_requests=5,
                requests_per_second=104.0,
                error_rate=0.05,
                latency=LatencyDistribution(p50_ms=30.0, p95_ms=80.0, p99_ms=120.0),
            ),
        )
        assert bogus.validity == MeasurementValidity.INVALID
        assert any("successful + failed" in r for r in bogus.validity_reasons)

    def test_nan_metric_is_invalid(self) -> None:
        now = datetime.now(UTC)
        nan_measurement = Measurement(
            run_id="r",
            timestamp=now,
            request_metrics=RequestMetrics(
                timestamp=now,
                duration_seconds=1.0,
                total_requests=100,
                successful_requests=100,
                failed_requests=0,
                requests_per_second=100.0,
                error_rate=float("nan"),
                latency=LatencyDistribution(p50_ms=30.0, p95_ms=80.0, p99_ms=120.0),
            ),
        )
        assert nan_measurement.validity == MeasurementValidity.INVALID

    def test_measurement_serialization(self, sample_measurement: Measurement) -> None:
        json_str = sample_measurement.model_dump_json()
        data = json.loads(json_str)
        assert "request_metrics" in data
        assert "resource_metrics" in data


class TestVerdict:
    """Test Verdict model."""

    def test_create_verdict(self, sample_verdict: Verdict) -> None:
        assert sample_verdict.status == VerdictStatus.WARNING
        assert sample_verdict.observed_value == 480.0

    def test_verdict_serialization(self, sample_verdict: Verdict) -> None:
        json_str = sample_verdict.model_dump_json()
        restored = Verdict.model_validate_json(json_str)
        assert restored.status == sample_verdict.status


class TestVerificationRun:
    """Test the top-level VerificationRun model."""

    def test_create_run(self, sample_run: VerificationRun) -> None:
        assert sample_run.schema_version == "1.0"
        assert sample_run.final_verdict == VerdictStatus.WARNING
        assert len(sample_run.static_findings) == 1
        assert len(sample_run.measurements) == 1
        assert len(sample_run.verdicts) == 1

    def test_run_serialization_round_trip(self, sample_run: VerificationRun) -> None:
        json_str = sample_run.model_dump_json()
        restored = VerificationRun.model_validate_json(json_str)
        assert restored.id == sample_run.id
        assert restored.final_verdict == sample_run.final_verdict
        assert restored.target.name == sample_run.target.name
        assert len(restored.static_findings) == len(sample_run.static_findings)

    def test_run_metadata(self, sample_run: VerificationRun) -> None:
        meta = sample_run.metadata
        assert meta.guardrail_version == "0.1.0"
        assert meta.duration_seconds == 312.5

    def test_run_has_id(self, sample_run: VerificationRun) -> None:
        assert sample_run.id is not None
        assert len(sample_run.id) > 0


class TestWorkload:
    """Test Workload models."""

    def test_workload_scenario(self) -> None:
        scenario = WorkloadScenario(
            name="ramp-test",
            pattern=TrafficPattern.RAMP,
            stages=[
                WorkloadStage(duration_seconds=60, target_rps=10),
                WorkloadStage(duration_seconds=60, target_rps=50),
                WorkloadStage(duration_seconds=60, target_rps=100),
            ],
        )
        assert len(scenario.stages) == 3
        assert scenario.pattern == TrafficPattern.RAMP

    def test_amplification_model(self) -> None:
        amp = AmplificationModel(
            source="polling",
            client_count=500,
            interval_seconds=5.0,
            db_queries_per_request=15,
            theoretical_rps=100.0,
            theoretical_db_qps=1500.0,
        )
        assert amp.theoretical_rps == 100.0
        assert amp.theoretical_db_qps == 1500.0
