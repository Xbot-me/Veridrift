"""Registered controlled experiments (Milestone 7).

DB-002 is the first concrete experiment: the N+1 / query-in-loop hypothesis.
The mechanism metric queried is db_queries_per_request (derived from measured
query_count / successful_requests). DB telemetry is NOT currently instrumented
by any runtime provider, so a real DB-002 run legitimately concludes
INCONCLUSIVE — the engine is honest about missing instrumentation.

Mechanism vs corroborating (evidence criteria, configurable, deterministic):
  * mechanism      db_queries_per_request        decrease >= 50%  (REQUIRED)
  * corroborating  db_queries_per_second         decrease >= 30%
  * corroborating  db_query_latency_ms           decrease >= 30%
  * corroborating  p95_latency_ms                decrease >= 30%  (symptom, not cause)
"""

from __future__ import annotations

from guardrail.experiment.models import (
    EffectDirection,
    EvidenceExpectation,
    Experiment,
    ExperimentWorkload,
    Hypothesis,
    Intervention,
    Precondition,
)
from guardrail.models.base import RuleCategory

DB002_EXPERIMENT_ID = "EXP-DB-002"

DB002_HYPOTHESIS = Hypothesis(
    id="H-DB-002",
    statement=(
        "Executing a database query inside a per-item loop (N+1 pattern) amplifies "
        "database queries per successful request at the target endpoint, increasing "
        "query and response latency under concurrent load."
    ),
    finding_id="DB-002",
    category=RuleCategory.DATABASE,
    target_endpoint="/api/orders",
    preconditions=[
        Precondition(
            id="PRECOND-APP-HEALTHY",
            description="Application must be healthy and reachable before the experiment.",
            check="app_healthy",
        ),
        Precondition(
            id="PRECOND-DB-TELEMETRY",
            description=(
                "Database telemetry (db_queries_per_request) must be instrumented; "
                "otherwise the mechanism cannot be measured and causality cannot be claimed."
            ),
            check="db_telemetry_available",
        ),
    ],
)

DB002_EXPERIMENT = Experiment(
    id=DB002_EXPERIMENT_ID,
    hypothesis=DB002_HYPOTHESIS,
    interventions=[
        Intervention(
            id="INT-DB-002",
            description="Hoist the database query out of the per-item loop (batch fetch).",
            change_description=(
                "Replace the per-item query with a single batched query so that "
                "db_queries_per_request drops by roughly 1/N."
            ),
        )
    ],
    expectations=[
        EvidenceExpectation(
            metric="db_queries_per_request",
            direction=EffectDirection.DECREASE,
            min_relative_change=0.5,
            role="mechanism",
            required=True,
        ),
        EvidenceExpectation(
            metric="db_queries_per_second",
            direction=EffectDirection.DECREASE,
            min_relative_change=0.3,
            role="corroborating",
            required=False,
        ),
        EvidenceExpectation(
            metric="db_query_latency_ms",
            direction=EffectDirection.DECREASE,
            min_relative_change=0.3,
            role="corroborating",
            required=False,
        ),
        EvidenceExpectation(
            metric="p95_latency_ms",
            direction=EffectDirection.DECREASE,
            min_relative_change=0.3,
            role="corroborating",
            required=False,
        ),
    ],
    default_workload=ExperimentWorkload(
        endpoint="/api/orders",
        method="GET",
        target_rps=30.0,
        duration_seconds=5.0,
        concurrency=50,
    ),
    repetitions=1,
    workload_tolerance=0.2,
    refute_on_flat_mechanism=True,
)


def registered_experiments() -> dict[str, Experiment]:
    return {DB002_EXPERIMENT_ID: DB002_EXPERIMENT}


def db002_experiment() -> Experiment:
    return DB002_EXPERIMENT