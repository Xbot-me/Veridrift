from __future__ import annotations

from datetime import UTC, datetime

from guardrail.correlation.correlator import (
    ControlledExperimentEvidenceRequired,
    HypothesisCorrelator,
)
from guardrail.models.base import Confidence, HypothesisStatus, RuleCategory, Severity
from guardrail.models.measurement import (
    DatabaseMetrics,
    LatencyDistribution,
    Measurement,
    RequestMetrics,
)
from guardrail.models.rule import Finding
from guardrail.models.verdict import CapacityResult


def _finding(
    rule_id: str,
    rule_name: str,
    category: RuleCategory,
    severity: Severity = Severity.HIGH,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        rule_name=rule_name,
        category=category,
        severity=severity,
        confidence=Confidence.CONFIRMED,
        message=f"{rule_name} risk",
    )


def _measurement(database: bool = False, timeouts: int = 0, total: int = 200) -> Measurement:
    now = datetime.now(UTC)
    return Measurement(
        run_id="run_1",
        timestamp=now,
        request_metrics=RequestMetrics(
            timestamp=now,
            duration_seconds=2.0,
            total_requests=total,
            successful_requests=total - timeouts,
            failed_requests=timeouts,
            timeouts=timeouts,
            requests_per_second=100.0,
            error_rate=0.0,
            latency=LatencyDistribution(p50_ms=250.0, p95_ms=650.0, p99_ms=1200.0),
        ),
        database_metrics=(
            DatabaseMetrics(
                timestamp=now,
                query_count=1000,
                query_rate_per_second=500.0,
                avg_query_latency_ms=12.0,
                active_connections=25,
                max_connections=100,
            )
            if database
            else None
        ),
    )


def _capacity() -> CapacityResult:
    return CapacityResult(
        safe_rps=50.0,
        failure_rps=100.0,
        primary_bottleneck="p95_latency_exceeded",
    )


def test_correlate_no_measurements_leaves_status_untouched():
    correlator = HypothesisCorrelator()
    finding = _finding("DB-002", "Query Inside Loop", RuleCategory.DATABASE)
    res_findings, amplifications = correlator.correlate([finding], [])
    assert len(res_findings) == 1
    # No workload ran: the hypothesis stays DETECTED, never stages upward.
    assert res_findings[0].hypothesis_status == HypothesisStatus.DETECTED
    assert res_findings[0].evidence_summary is None
    assert len(amplifications) == 0


def test_correlate_with_zero_request_measurement_does_not_fabricate_verification():
    correlator = HypothesisCorrelator()
    finding = _finding("DB-002", "Query Inside Loop", RuleCategory.DATABASE)
    zero = _measurement(total=0)
    res_findings, amplifications = correlator.correlate([finding], [zero], exercised_endpoints=["/api/orders"])
    assert res_findings[0].hypothesis_status == HypothesisStatus.DETECTED
    assert len(amplifications) == 0


def test_correlate_never_auto_verifies_cfg():
    correlator = HypothesisCorrelator()
    findings = [
        _finding("CFG-001", "Debug Mode Enabled", RuleCategory.CONFIGURATION),
        _finding("REL-001", "No Circuit Breaker", RuleCategory.RELIABILITY),
        _finding("DB-002", "Query Inside Loop", RuleCategory.DATABASE),
    ]

    measurement = _measurement(database=False)
    updated_findings, amplifications = correlator.correlate(
        findings=findings,
        measurements=[measurement],
        capacity=_capacity(),
        exercised_endpoints=["/api/orders"],
    )

    f_map = {f.rule_id: f for f in updated_findings}
    # Coarse aggregate signals (good p95 etc.) must NOT upgrade anything.
    assert f_map["CFG-001"].hypothesis_status == HypothesisStatus.DETECTED
    assert "NOT claimed as verified" in (f_map["CFG-001"].evidence_summary or "")
    # No mechanism signal for DB (no DB telemetry) -> INCONCLUSIVE.
    assert f_map["DB-002"].hypothesis_status == HypothesisStatus.INCONCLUSIVE
    # No mechanism signal for REL -> INCONCLUSIVE.
    assert f_map["REL-001"].hypothesis_status == HypothesisStatus.INCONCLUSIVE
    # Endpoints exercised are recorded.
    assert f_map["DB-002"].exercised_endpoints == ["/api/orders"]

    # No fabricated amplification models.
    assert len(amplifications) == 0


def test_correlate_observes_db_when_telemetry_exists_but_not_supported():
    correlator = HypothesisCorrelator()
    finding = _finding("DB-002", "Query Inside Loop", RuleCategory.DATABASE)
    measurement = _measurement(database=True)
    updated_findings, amplifications = correlator.correlate(
        findings=[finding],
        measurements=[measurement],
        exercised_endpoints=["/api/orders"],
    )
    f = updated_findings[0]
    assert f.hypothesis_status == HypothesisStatus.OBSERVED
    assert "not isolated" in (f.evidence_summary or "").lower()
    assert len(amplifications) == 0


def test_correlate_observes_net001_only_on_direct_timeout_signal():
    correlator = HypothesisCorrelator()
    no_signal = _finding("NET-001", "Missing Timeout", RuleCategory.NETWORK)
    updated_findings, _ = correlator.correlate([no_signal], [_measurement(timeouts=0)])
    assert updated_findings[0].hypothesis_status == HypothesisStatus.INCONCLUSIVE

    with_signal = _finding("NET-001", "Missing Timeout", RuleCategory.NETWORK)
    updated_findings, _ = correlator.correlate([with_signal], [_measurement(timeouts=12)])
    assert updated_findings[0].hypothesis_status == HypothesisStatus.OBSERVED
    assert "12 request(s) failed" in (updated_findings[0].evidence_summary or "")


def test_correlate_does_not_mutate_input_findings():
    correlator = HypothesisCorrelator()
    finding = _finding("DB-002", "Query Inside Loop", RuleCategory.DATABASE)
    correlator.correlate([finding], [_measurement(timeouts=0)], exercised_endpoints=["/api/orders"])
    assert finding.hypothesis_status == HypothesisStatus.DETECTED
    assert finding.exercised_endpoints == []


def test_supported_unreachable_from_aggregate_latency():
    """Worst-case aggregate latency + telemetry present is still OBSERVED, never SUPPORTED.

    This is the central product boundary: causal conclusion requires a controlled
    experiment, not a bad p95 or existing DB telemetry.
    """
    correlator = HypothesisCorrelator()
    now = datetime.now(UTC)
    finding = _finding("DB-002", "Query Inside Loop", RuleCategory.DATABASE)

    measurement = Measurement(
        run_id="run_1",
        timestamp=now,
        request_metrics=RequestMetrics(
            timestamp=now,
            duration_seconds=5.0,
            total_requests=500,
            successful_requests=300,
            failed_requests=200,
            server_errors=200,
            requests_per_second=100.0,
            error_rate=0.4,
            latency=LatencyDistribution(p50_ms=2000.0, p95_ms=9000.0, p99_ms=15000.0),
        ),
        database_metrics=DatabaseMetrics(
            timestamp=now,
            query_count=500000,
            query_rate_per_second=100000.0,
            avg_query_latency_ms=8000.0,
            active_connections=99,
            max_connections=100,
        ),
    )

    capacity = CapacityResult(
        safe_rps=10.0,
        failure_rps=15.0,
        primary_bottleneck="p95_latency_exceeded",
    )

    updated_findings, _ = correlator.correlate(
        findings=[finding],
        measurements=[measurement],
        capacity=capacity,
        exercised_endpoints=["/api/orders"],
    )
    f = updated_findings[0]
    assert f.hypothesis_status == HypothesisStatus.OBSERVED
    assert f.hypothesis_status not in (HypothesisStatus.SUPPORTED, HypothesisStatus.REFUTED)


def test_no_rule_can_reach_supported_via_correlation():
    """Full catalog sweep: correlation may never emit SUPPORTED/REFUTED."""
    from guardrail.models.base import RuleCategory

    catalog = [
        ("DB-002", RuleCategory.DATABASE, True),
        ("DB-001", RuleCategory.DATABASE, True),
        ("CFG-001", RuleCategory.CONFIGURATION, True),
        ("NET-001", RuleCategory.NETWORK, True),
        ("AMP-001", RuleCategory.AMPLIFICATION, True),
        ("AMP-003", RuleCategory.AMPLIFICATION, True),
        ("CONC-001", RuleCategory.CONCURRENCY, True),
        ("REL-001", RuleCategory.RELIABILITY, True),
        ("RES-001", RuleCategory.RESOURCE, True),
        ("RES-002", RuleCategory.RESOURCE, True),
    ]
    correlator = HypothesisCorrelator()
    findings = [_finding(rule_id, rule_id, cat) for rule_id, cat, _ in catalog]
    # Build DB telemetry so DB rules can reach OBSERVED, worst-case aggregates to
    # tempt SUPPORTED. The correct outcome is: database rules OBSERVED, others
    # INCONCLUSIVE, NONE SUPPORTED/REFUTED.
    now = datetime.now(UTC)
    measurement = Measurement(
        run_id="run_1",
        timestamp=now,
        request_metrics=RequestMetrics(
            timestamp=now,
            duration_seconds=5.0,
            total_requests=500,
            successful_requests=300,
            failed_requests=200,
            server_errors=200,
            timeouts=0,
            requests_per_second=100.0,
            error_rate=0.4,
            latency=LatencyDistribution(p50_ms=2000.0, p95_ms=9000.0, p99_ms=15000.0),
        ),
        database_metrics=DatabaseMetrics(
            timestamp=now,
            query_count=500000,
            query_rate_per_second=100000.0,
            avg_query_latency_ms=8000.0,
            active_connections=99,
            max_connections=100,
        ),
    )
    updated, _ = correlator.correlate(findings, [measurement], exercised_endpoints=["/"])

    assert len(updated) == len(catalog)
    for f in updated:
        assert f.hypothesis_status not in (HypothesisStatus.SUPPORTED, HypothesisStatus.REFUTED), (
            f"{f.rule_id} reached {f.hypothesis_status.value} from aggregate correlation"
        )
    db_statuses = {f.rule_id: f.hypothesis_status for f in updated if f.category == RuleCategory.DATABASE}
    assert set(db_statuses.values()) == {HypothesisStatus.OBSERVED}
    assert updated[0].hypothesis_status == HypothesisStatus.OBSERVED


def test_controlled_outcome_guard_fails_fast():
    """The CDE seam must loudly reject SUPPORTED from non-experiment code paths."""
    from guardrail.correlation.correlator import _controlled_outcome_only

    f = _finding("DB-002", "Query Inside Loop", RuleCategory.DATABASE)
    f.hypothesis_status = HypothesisStatus.SUPPORTED
    try:
        _controlled_outcome_only(f)
        raise AssertionError("SUPPORTED without a controlled experiment must raise")
    except ControlledExperimentEvidenceRequired as exc:
        assert "controlled" in str(exc)
