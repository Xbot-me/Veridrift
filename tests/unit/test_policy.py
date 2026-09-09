"""Unit tests for the policy engine."""

from __future__ import annotations

from datetime import UTC, datetime

from guardrail.models.base import Severity, ThresholdOperator, VerdictStatus
from guardrail.models.measurement import (
    DatabaseMetrics,
    LatencyDistribution,
    Measurement,
    RequestMetrics,
    ResourceMetrics,
)
from guardrail.models.policy import Policy, PolicyThreshold
from guardrail.policy.engine import PolicyEngine


class TestPolicyEngine:
    """Test threshold evaluation logic."""

    def test_passing_measurement(self, sample_measurement: Measurement) -> None:
        """A measurement within thresholds should produce no FAIL verdicts."""
        policy = Policy.default()
        engine = PolicyEngine(policy)
        verdicts = engine.evaluate_measurement(sample_measurement)

        fail_verdicts = [v for v in verdicts if v.status == VerdictStatus.FAIL]
        assert len(fail_verdicts) == 0
        # Default policy: p95 <= 500ms, our sample has 480ms → PASS
        # Error rate <= 1%, our sample has 1% → borderline
        assert not any(
            v.category == "p95_latency_ms" and v.status == VerdictStatus.FAIL for v in verdicts
        )

    def test_failing_latency(self) -> None:
        """A measurement exceeding p95 threshold should produce FAIL."""
        now = datetime.now(UTC)
        measurement = Measurement(
            run_id="test",
            timestamp=now,
            workload_rps=200.0,
            request_metrics=RequestMetrics(
                timestamp=now,
                duration_seconds=300.0,
                total_requests=60000,
                successful_requests=59000,
                failed_requests=1000,
                requests_per_second=200.0,
                error_rate=0.0167,
                latency=LatencyDistribution(
                    p50_ms=200.0,
                    p95_ms=1830.0,  # Way over 500ms threshold
                    p99_ms=4800.0,
                ),
            ),
        )

        policy = Policy.default()
        engine = PolicyEngine(policy)
        verdicts = engine.evaluate_measurement(measurement, "200 RPS for 5 minutes")

        # Should have FAIL for p95 latency
        p95_fails = [v for v in verdicts if v.category == "p95_latency_ms"]
        assert len(p95_fails) > 0
        assert p95_fails[0].status == VerdictStatus.FAIL
        assert p95_fails[0].observed_value == 1830.0
        assert "200 RPS" in (p95_fails[0].workload_context or "")

    def test_failing_cpu(self) -> None:
        """CPU exceeding 80% should produce FAIL."""
        now = datetime.now(UTC)
        measurement = Measurement(
            run_id="test",
            timestamp=now,
            resource_metrics=ResourceMetrics(
                timestamp=now,
                cpu_percent=95.0,
                memory_mb=700.0,
                memory_percent=68.0,
            ),
        )

        policy = Policy.default()
        engine = PolicyEngine(policy)
        verdicts = engine.evaluate_measurement(measurement)

        cpu_verdicts = [v for v in verdicts if v.category == "cpu_percent"]
        assert len(cpu_verdicts) > 0
        assert cpu_verdicts[0].status == VerdictStatus.FAIL
        assert cpu_verdicts[0].observed_value == 95.0

    def test_final_verdict_fail_wins(self) -> None:
        """A single FAIL should make the final verdict FAIL."""
        from guardrail.models.verdict import Verdict

        verdicts = [
            Verdict(status=VerdictStatus.PASS, category="cpu", reason="OK"),
            Verdict(status=VerdictStatus.WARNING, category="memory", reason="High"),
            Verdict(status=VerdictStatus.FAIL, category="latency", reason="Too slow"),
        ]

        policy = Policy.default()
        engine = PolicyEngine(policy)
        final = engine.compute_final_verdict(verdicts)

        assert final == VerdictStatus.FAIL

    def test_final_verdict_warning(self) -> None:
        """Without FAIL, WARNING should be the final verdict."""
        from guardrail.models.verdict import Verdict

        verdicts = [
            Verdict(status=VerdictStatus.PASS, category="cpu", reason="OK"),
            Verdict(status=VerdictStatus.WARNING, category="memory", reason="High"),
        ]

        policy = Policy.default()
        engine = PolicyEngine(policy)
        final = engine.compute_final_verdict(verdicts)

        assert final == VerdictStatus.WARNING

    def test_final_verdict_pass(self) -> None:
        """All PASS should yield PASS."""
        from guardrail.models.verdict import Verdict

        verdicts = [
            Verdict(status=VerdictStatus.PASS, category="cpu", reason="OK"),
            Verdict(status=VerdictStatus.PASS, category="memory", reason="OK"),
        ]

        policy = Policy.default()
        engine = PolicyEngine(policy)
        final = engine.compute_final_verdict(verdicts)

        assert final == VerdictStatus.PASS

    def test_no_verdicts_neutral(self) -> None:
        """Empty verdicts are neutral; orchestrators must append evidence verdicts."""
        policy = Policy.default()
        engine = PolicyEngine(policy)
        final = engine.compute_final_verdict([])

        assert final == VerdictStatus.PASS

    def test_empty_run_is_not_pass_if_evidence_verdict_appended(self) -> None:
        """An empty evidence record consciously expressed as INCONCLUSIVE must win."""
        from guardrail.models.verdict import Verdict

        policy = Policy.default()
        engine = PolicyEngine(policy)
        final = engine.compute_final_verdict(
            [Verdict(status=VerdictStatus.INCONCLUSIVE, category="evidence_sufficiency", reason="unverified")]
        )
        assert final == VerdictStatus.INCONCLUSIVE

    def test_inconclusive_precedes_warning(self) -> None:
        """INCONCLUSIVE must dominate WARNING (but lose to FAIL)."""
        from guardrail.models.verdict import Verdict

        policy = Policy.default()
        engine = PolicyEngine(policy)

        assert (
            engine.compute_final_verdict(
                [
                    Verdict(status=VerdictStatus.PASS, category="cpu", reason="OK"),
                    Verdict(status=VerdictStatus.INCONCLUSIVE, category="evidence", reason="unverified"),
                    Verdict(status=VerdictStatus.WARNING, category="memory", reason="high"),
                ]
            )
            == VerdictStatus.INCONCLUSIVE
        )
        assert (
            engine.compute_final_verdict(
                [
                    Verdict(status=VerdictStatus.FAIL, category="latency", reason="bad"),
                    Verdict(status=VerdictStatus.INCONCLUSIVE, category="evidence", reason="unverified"),
                ]
            )
            == VerdictStatus.FAIL
        )

    def test_static_findings_severity(self) -> None:
        """CRITICAL static findings should produce FAIL verdict."""
        policy = Policy.default()
        engine = PolicyEngine(policy)

        verdicts = engine.evaluate_static_findings_severity(
            {
                Severity.CRITICAL: 2,
                Severity.HIGH: 5,
                Severity.MEDIUM: 3,
            }
        )

        assert any(v.status == VerdictStatus.FAIL for v in verdicts)
        assert any(v.status == VerdictStatus.WARNING for v in verdicts)

    def test_custom_threshold(self) -> None:
        """Custom thresholds should work correctly."""
        now = datetime.now(UTC)
        measurement = Measurement(
            run_id="test",
            timestamp=now,
            database_metrics=DatabaseMetrics(
                timestamp=now,
                query_count=10000,
                query_rate_per_second=2000.0,
                avg_query_latency_ms=50.0,
                active_connections=90,
                max_connections=100,
                connection_utilization=0.90,
            ),
        )

        policy = Policy(
            name="strict",
            thresholds=[
                PolicyThreshold(
                    metric="db_connection_utilization",
                    operator=ThresholdOperator.LTE,
                    value=0.80,
                    severity=Severity.CRITICAL,
                    description="DB connections must be ≤ 80% utilized",
                ),
            ],
        )

        engine = PolicyEngine(policy)
        verdicts = engine.evaluate_measurement(measurement)

        assert len(verdicts) == 1
        assert verdicts[0].status == VerdictStatus.FAIL
        assert verdicts[0].observed_value == 0.90

    def test_missing_required_metric_fails(self) -> None:
        """A required metric that was never measured must FAIL, never silently skip."""
        now = datetime.now(UTC)
        request_only = Measurement(
            run_id="test",
            timestamp=now,
            request_metrics=RequestMetrics(
                timestamp=now,
                duration_seconds=1.0,
                total_requests=100,
                successful_requests=100,
                failed_requests=0,
                requests_per_second=100.0,
                error_rate=0.0,
                latency=LatencyDistribution(p50_ms=30.0, p95_ms=80.0, p99_ms=120.0),
            ),
        )

        policy = Policy.default()
        engine = PolicyEngine(policy)
        verdicts = engine.evaluate_measurement(request_only)

        # cpu_percent and memory_percent are required in the default policy.
        missing = {v.category for v in verdicts if v.category.endswith("_not_measured")}
        assert "cpu_percent_not_measured" in missing
        assert "memory_percent_not_measured" in missing
        assert all(v.status == VerdictStatus.FAIL for v in verdicts if v.category in missing)

    def test_nan_metric_fails(self) -> None:
        """NaN/Inf measurements are invalid evidence and must produce FAIL, never PASS."""
        now = datetime.now(UTC)
        measurement = Measurement(
            run_id="test",
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

        policy = Policy.default()
        engine = PolicyEngine(policy)
        verdicts = engine.evaluate_measurement(measurement)

        assert any(v.status == VerdictStatus.FAIL for v in verdicts)
        assert any(v.category == "invalid_measurement" for v in verdicts)
        final = engine.compute_final_verdict(verdicts)
        assert final == VerdictStatus.FAIL

    def test_zero_request_stage_is_insufficient_data(self) -> None:
        """A workload that produced zero requests can never be a PASS stage."""
        now = datetime.now(UTC)
        zero_stage = Measurement(
            run_id="test",
            timestamp=now,
            workload_rps=10.0,
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

        policy = Policy.default()
        engine = PolicyEngine(policy)
        verdicts = engine.evaluate_measurement(zero_stage)

        assert any(v.category == "insufficient_data" and v.status == VerdictStatus.FAIL for v in verdicts)
        assert engine.compute_final_verdict(verdicts) == VerdictStatus.FAIL

    def test_inconsistent_counters_make_measurement_invalid(self) -> None:
        """successful + failed != total means the evidence was fabricated/currupted."""
        now = datetime.now(UTC)
        bogus = Measurement(
            run_id="test",
            timestamp=now,
            request_metrics=RequestMetrics(
                timestamp=now,
                duration_seconds=1.0,
                total_requests=100,
                successful_requests=99,
                failed_requests=5,
                requests_per_second=105.0,
                error_rate=0.05,
                latency=LatencyDistribution(p50_ms=30.0, p95_ms=80.0, p99_ms=120.0),
            ),
        )

        policy = Policy.default()
        engine = PolicyEngine(policy)
        verdicts = engine.evaluate_measurement(bogus)

        assert any(v.category == "invalid_measurement" and v.status == VerdictStatus.FAIL for v in verdicts)

    def test_refuses_pass_on_known_bad_evidence(self) -> None:
        """Meta-test: deliberately feed Guardrail known-bad evidence; PASS must be refused."""
        policy = Policy.default()
        engine = PolicyEngine(policy)
        now = datetime.now(UTC)

        # A measurement that "looks green" on every trackable axis but hides that
        # CPU telemetry was never captured.
        doctored = Measurement(
            run_id="test",
            timestamp=now,
            request_metrics=RequestMetrics(
                timestamp=now,
                duration_seconds=1.0,
                total_requests=100,
                successful_requests=100,
                failed_requests=0,
                requests_per_second=100.0,
                error_rate=0.0,
                latency=LatencyDistribution(p50_ms=20.0, p95_ms=50.0, p99_ms=80.0),
            ),
        )

        verdicts = engine.evaluate_measurement(doctored)
        assert any(v.category == "cpu_percent_not_measured" for v in verdicts)
        assert engine.compute_final_verdict(verdicts) == VerdictStatus.FAIL

        # A measurement with a NaN error rate is force-rejected even though the
        # remaining axes are green.
        nan_error = Measurement(
            run_id="test",
            timestamp=now,
            request_metrics=RequestMetrics(
                timestamp=now,
                duration_seconds=1.0,
                total_requests=100,
                successful_requests=100,
                failed_requests=0,
                requests_per_second=100.0,
                error_rate=float("inf"),
                latency=LatencyDistribution(p50_ms=20.0, p95_ms=50.0, p99_ms=80.0),
            ),
        )
        v2 = engine.evaluate_measurement(nan_error)
        assert any(v.category == "invalid_measurement" for v in v2)
        assert engine.compute_final_verdict(v2) == VerdictStatus.FAIL
