from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from guardrail.correlation.correlator import (
    ControlledExperimentEvidenceRequired,
    _controlled_outcome_only,
)
from guardrail.evidence.store import EvidenceStore
from guardrail.experiment.engine import (
    ControlledExperimentEngine,
    apply_experiment_conclusion,
    transition_finding,
)
from guardrail.experiment.models import (
    Experiment,
    ExperimentRun,
    ExperimentValidity,
    ExperimentWorkload,
    Intervention,
    PreconditionCheck,
)
from guardrail.experiment.providers import (
    StaticMeasurementProvider,
)
from guardrail.experiment.registry import db002_experiment
from guardrail.models.base import (
    Confidence,
    HypothesisStatus,
    RuleCategory,
    Severity,
)
from guardrail.models.measurement import (
    DatabaseMetrics,
    LatencyDistribution,
    Measurement,
    RequestMetrics,
    ResourceMetrics,
)
from guardrail.models.rule import Finding


def _now() -> datetime:
    return datetime.now(UTC)


def _measurement(
    total: int,
    rps: float,
    p95: float = 300.0,
    p99: float = 600.0,
    db: bool = True,
    query_count: int | None = None,
    query_rate: float | None = None,
    query_latency: float | None = None,
    cpu: float = 40.0,
) -> Measurement:
    from guardrail.models.base import generate_id

    now = _now()
    return Measurement(
        id=generate_id(),
        run_id="exp-test",
        timestamp=now,
        workload_rps=rps,
        request_metrics=RequestMetrics(
            timestamp=now,
            duration_seconds=2.0,
            total_requests=total,
            successful_requests=total,
            failed_requests=0,
            requests_per_second=rps,
            error_rate=0.0,
            latency=LatencyDistribution(p50_ms=p95 * 0.5, p95_ms=p95, p99_ms=p99),
        ),
        resource_metrics=ResourceMetrics(timestamp=now, cpu_percent=cpu, memory_mb=500.0),
        database_metrics=(
            DatabaseMetrics(
                timestamp=now,
                query_count=query_count if query_count is not None else total * 10,
                query_rate_per_second=query_rate if query_rate is not None else rps * 10,
                avg_query_latency_ms=query_latency if query_latency is not None else 8.0,
                active_connections=25,
                max_connections=100,
                connection_utilization=0.25,
            )
            if db
            else None
        ),
    )


def _workload(rps: float = 100.0) -> ExperimentWorkload:
    return ExperimentWorkload(
        endpoint="/api/orders", target_rps=rps, duration_seconds=2.0, concurrency=50
    )


def _finding(rule_id: str = "DB-002") -> Finding:
    return Finding(
        rule_id=rule_id,
        rule_name="Query Inside Loop (N+1)",
        category=RuleCategory.DATABASE,
        severity=Severity.HIGH,
        confidence=Confidence.CONFIRMED,
        message="query inside loop",
    )


def _run_experiment(
    control: list[Measurement],
    treatment: list[Measurement],
    experiment: Experiment | None = None,
    preconditions: list[PreconditionCheck] | None = None,
    intervention: Intervention | None = None,
    workload: ExperimentWorkload | None = None,
) -> ExperimentRun:
    engine = ControlledExperimentEngine()
    experiment = experiment or db002_experiment()
    provider = StaticMeasurementProvider(
        control_measurements=control,
        treatment_measurements=treatment,
        preconditions=preconditions,
        intervention_result=intervention,
    )
    return engine.run_experiment(experiment, provider, workload=workload)


# ---------------------------------------------------------------------------
# Structural & causal safety
# ---------------------------------------------------------------------------


def test_correlator_cannot_reach_supported_even_with_experiment_id():
    """A finding that legitimately holds SUPPORTED still cannot flow out of
    the correlator: SUPPORTED/REFUTED are ONLY produced by the experiment engine
    as a dedicated pathway, never recomputed by observational correlation."""

    f = _finding()
    f.hypothesis_status = HypothesisStatus.SUPPORTED
    f.controlled_experiment_id = "EXP-DB-002-x"
    with pytest.raises(ControlledExperimentEvidenceRequired):
        _controlled_outcome_only(f)


def test_no_causal_outcome_from_aggregate_latency_only():
    """Causal safety: a controlled experiment whose treatment shows latency
    improvement but whose mechanism metric is NOT measured must be INCONCLUSIVE,
    never SUPPORTED — causality runs through the mechanism, not the symptom."""
    control = [_measurement(total=200, rps=100.0, p95=2000.0)]
    treatment = [_measurement(total=200, rps=100.0, p95=150.0, db=False)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status == "INCONCLUSIVE"
    assert run.conclusion.validity == ExperimentValidity.INSUFFICIENT_DATA
    assert "not measured" in run.conclusion.reasons[0]


# ---------------------------------------------------------------------------
# Known-positive / known-negative
# ---------------------------------------------------------------------------


def test_valid_experiment_supports_known_positive():
    control = [_measurement(total=200, rps=100.0, p95=300.0, query_count=2000, query_latency=8.0)]
    treatment = [_measurement(total=200, rps=100.0, p95=150.0, query_count=600, query_latency=4.0)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status == "SUPPORTED"
    assert run.conclusion.validity == ExperimentValidity.VALID
    qpr = next(m for m in run.comparison.metrics if m.metric == "db_queries_per_request")
    assert qpr.meets_prediction is True
    assert qpr.control_median == 10.0 and qpr.treatment_median == 3.0


def test_known_negative_refutes():
    """Intervention applied but the mechanism metric moved OPPOSITE the
    predicted direction (treatment increased queries/request)."""
    control = [_measurement(total=200, rps=100.0, query_count=600, query_latency=4.0)]
    treatment = [_measurement(total=200, rps=100.0, query_count=2000, query_latency=8.0)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status == "REFUTED"
    assert run.conclusion.validity == ExperimentValidity.VALID


def test_flat_mechanism_refutes_when_configured():
    """refute_on_flat_mechanism: controlled intervention applied, mechanism
    measured but did not move in the predicted direction -> REFUTED."""
    control = [_measurement(total=200, rps=100.0, query_count=2000)]
    treatment = [_measurement(total=200, rps=100.0, query_count=2000)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status == "REFUTED"
    assert "mechanism" in run.conclusion.reasons[0].lower()
    assert "did not move" in run.conclusion.reasons[0] or "none moved" in run.conclusion.reasons[0]


# ---------------------------------------------------------------------------
# Insufficient data
# ---------------------------------------------------------------------------


def test_missing_db_telemetry_is_inconclusive():
    control = [_measurement(total=200, rps=100.0, db=False)]
    treatment = [_measurement(total=200, rps=100.0, db=False)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status == "INCONCLUSIVE"
    assert run.conclusion.validity == ExperimentValidity.INSUFFICIENT_DATA
    assert "db_queries_per_request" in run.conclusion.reasons[0]


def test_zero_request_control_is_inconclusive():
    control = [_measurement(total=0, rps=0.0)]
    treatment = [_measurement(total=200, rps=100.0)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status == "INCONCLUSIVE"
    assert run.conclusion.validity == ExperimentValidity.INSUFFICIENT_DATA
    assert "zero requests" in run.conclusion.reasons[0]


def test_workload_mismatch_is_inconclusive():
    control = [_measurement(total=200, rps=100.0, query_count=2000)]
    treatment = [_measurement(total=80, rps=40.0, query_count=600)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status == "INCONCLUSIVE"
    assert run.conclusion.validity == ExperimentValidity.INSUFFICIENT_DATA
    assert "not comparable" in run.conclusion.reasons[0] or "ratio" in run.conclusion.reasons[0]


def test_workload_definitions_must_match():
    """Control and treatment must use the SAME workload definition key."""
    c = [_measurement(total=200, rps=100.0)]
    t = [_measurement(total=200, rps=100.0)]
    run = _run_experiment(c, t, workload=_workload(100.0))
    for obs in run.control_observations + run.treatment_observations:
        assert obs.workload_definition_key == run.workload.key()


def test_missing_intervention_is_inconclusive():
    engine = ControlledExperimentEngine()
    experiment = db002_experiment()
    provider = StaticMeasurementProvider(
        control_measurements=[_measurement(total=200, rps=100.0)],
        treatment_measurements=[_measurement(total=200, rps=100.0)],
        intervention_result=Intervention(
            id="INT-DB-002",
            description="x",
            applied=False,
            failure_reason="treatment variant unavailable",
        ),
    )
    run = engine.run_experiment(experiment, provider, workload=_workload())
    assert run.conclusion.status == "INCONCLUSIVE"
    assert run.conclusion.validity == ExperimentValidity.INVALID


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------


def test_precondition_failure_is_inconclusive_and_does_not_run():
    engine = ControlledExperimentEngine()
    experiment = db002_experiment()
    calls: list[str] = []

    class NoRunProvider(StaticMeasurementProvider):
        def run_condition(self, condition, workload, repetition, run_id):
            calls.append(condition.value)
            return super().run_condition(condition, workload, repetition, run_id)

    provider = NoRunProvider(
        control_measurements=[_measurement(total=200, rps=100.0)],
        treatment_measurements=[_measurement(total=200, rps=100.0)],
        preconditions=[
            PreconditionCheck(
                precondition_id="PRECOND-DB-TELEMETRY",
                description="db telemetry",
                satisfied=False,
                detail="not instrumented",
            )
        ],
    )
    run = engine.run_experiment(experiment, provider, workload=_workload())
    assert run.conclusion.status == "INCONCLUSIVE"
    assert run.conclusion.validity == ExperimentValidity.INSUFFICIENT_DATA
    assert calls == []


# ---------------------------------------------------------------------------
# Adversarial false-causality
# ---------------------------------------------------------------------------


def test_adversarial_mechanism_unchanged_latency_spiked_not_supported():
    control = [_measurement(total=200, rps=100.0, p95=200.0, query_count=2000)]
    treatment = [_measurement(total=200, rps=100.0, p95=2000.0, query_count=2000)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status != "SUPPORTED"


def test_adversarial_amplification_reduced_but_latency_only_modest_is_supported():
    """Section 22 case B: 50->5 queries/request with only a modest latency
    change (2000 -> 1900) is SUPPORTED for the query-amplification reduction."""
    control = [_measurement(total=200, rps=100.0, p95=2000.0, query_count=10000)]
    treatment = [_measurement(total=200, rps=100.0, p95=1900.0, query_count=1000)]
    run = _run_experiment(control, treatment)
    assert run.conclusion.status == "SUPPORTED"
    assert run.conclusion.validity == ExperimentValidity.VALID


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_finding_requires_controlled_experiment_id_for_causal_outcomes():
    with pytest.raises(ValidationError):
        Finding(
            rule_id="DB-002",
            rule_name="N+1",
            category=RuleCategory.DATABASE,
            severity=Severity.HIGH,
            confidence=Confidence.CONFIRMED,
            message="x",
            hypothesis_status=HypothesisStatus.SUPPORTED,
        )


def test_transition_finding_requires_valid_supported_experiment():
    run = _run_experiment(
        [_measurement(total=200, rps=100.0, db=False)],
        [_measurement(total=200, rps=100.0, db=False)],
    )
    f = _finding()
    with pytest.raises(ValueError):
        transition_finding(f, run, "SUPPORTED")


def test_transition_finding_only_for_matching_rule():
    run = _run_experiment(
        [_measurement(total=200, rps=100.0)],
        [_measurement(total=200, rps=100.0, query_count=600)],
    )
    f = _finding(rule_id="AMP-001")
    with pytest.raises(ValueError):
        transition_finding(f, run, "SUPPORTED")


def test_transition_finding_sets_controlled_provenance():
    run = _run_experiment(
        [_measurement(total=200, rps=100.0, query_count=2000)],
        [_measurement(total=200, rps=100.0, query_count=600)],
    )
    f = transition_finding(_finding(), run, "SUPPORTED")
    assert f.hypothesis_status == HypothesisStatus.SUPPORTED
    assert f.controlled_experiment_id == run.id
    rediscovered = Finding.model_validate(f.model_dump())
    assert rediscovered.hypothesis_status == HypothesisStatus.SUPPORTED
    assert rediscovered.controlled_experiment_id == run.id


def test_apply_experiment_conclusion_requires_valid_experiment():
    run = _run_experiment(
        [_measurement(total=200, rps=100.0, db=False)],
        [_measurement(total=200, rps=100.0, db=False)],
    )
    with pytest.raises(ValueError):
        apply_experiment_conclusion(run)


def test_apply_experiment_conclusion_returns_status():
    run = _run_experiment(
        [_measurement(total=200, rps=100.0, query_count=2000)],
        [_measurement(total=200, rps=100.0, query_count=600)],
    )
    assert apply_experiment_conclusion(run) == "SUPPORTED"


# ---------------------------------------------------------------------------
# Determinism & persistence
# ---------------------------------------------------------------------------


def test_determinism_same_measurements_same_conclusion():
    control = [_measurement(total=200, rps=100.0, query_count=2000)]
    treatment = [_measurement(total=200, rps=100.0, query_count=600)]
    a = _run_experiment(control, treatment)
    b = _run_experiment(control, treatment)
    assert a.conclusion.status == b.conclusion.status == "SUPPORTED"
    for ma, mb in zip(a.comparison.metrics, b.comparison.metrics, strict=True):
        assert ma.control_median == mb.control_median
        assert ma.treatment_median == mb.treatment_median
        assert ma.relative_change == mb.relative_change


def test_experiment_store_persists_all_artifacts(tmp_path):

    store = EvidenceStore(base_path=str(tmp_path))
    engine = ControlledExperimentEngine(store=store)
    run = engine.run_experiment(
        db002_experiment(),
        StaticMeasurementProvider(
            control_measurements=[_measurement(total=200, rps=100.0, query_count=2000)],
            treatment_measurements=[_measurement(total=200, rps=100.0, query_count=600)],
        ),
        workload=_workload(),
    )
    exp_dir = tmp_path / "experiments" / run.id
    for name in (
        "experiment.json",
        "preconditions.json",
        "comparison.json",
        "conclusion.json",
        "run.json",
        "manifest.json",
    ):
        assert (exp_dir / name).exists(), name
    assert (exp_dir / "observations").is_dir()
    assert (exp_dir / "conditions" / "control.json").exists()
    valid, errors = store.verify_experiment_manifest(run.id)
    assert valid, errors
    loaded = store.load_experiment(run.id)
    assert loaded is not None
    assert loaded.conclusion.status == "SUPPORTED"
    assert loaded.conclusion.experiment_id == run.experiment.id


def test_store_refuses_unprovenanced_causal_finding(
    tmp_path, sample_target, sample_environment, sample_policy
):
    """Persistence boundary: SUPPORTED/REFUTED findings without controlled
    experiment provenance cannot be written to the evidence store (defense-in-
    depth below the Finding constructor guard, covering attribute mutation)."""
    from datetime import UTC, datetime

    from guardrail.models.run import RunMetadata, VerificationRun

    store = EvidenceStore(base_path=str(tmp_path))
    run = VerificationRun(
        target=sample_target,
        environment=sample_environment,
        policy=sample_policy,
        static_findings=[_finding()],
        runtime_findings=[],
        measurements=[],
        verdicts=[],
        metadata=RunMetadata(
            guardrail_version="0.1.0",
            start_time=datetime.now(UTC),
        ),
    )
    run.static_findings[0].hypothesis_status = HypothesisStatus.SUPPORTED
    with pytest.raises(ValueError, match="SUPPORTED/REFUTED is only reachable"):
        store.save_run(run)


def test_experiment_store_provenance_links_conclusion_to_observations():
    run = _run_experiment(
        [_measurement(total=200, rps=100.0, query_count=2000)],
        [_measurement(total=200, rps=100.0, query_count=600)],
    )
    assert run.conclusion.evidence_observation_ids
    assert set(run.conclusion.evidence_observation_ids) == {
        o.id for o in [*run.control_observations, *run.treatment_observations]
    }
    assert run.comparison.control_observation_ids == [run.control_observations[0].id]
    assert run.comparison.treatment_observation_ids == [run.treatment_observations[0].id]
