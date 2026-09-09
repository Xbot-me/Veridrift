"""Data models for the Controlled Experiment Engine.

Evidence ladder (Milestone 6 + Milestone 7):
    DETECTED -> EXERCISED -> OBSERVED -> SUPPORTED | REFUTED

SUPPORTED/REFUTED are ONLY produced by a Controlled Experiment: a hypothesis is
tested by comparing a CONTROL condition (application as-is) against a TREATMENT
condition (application with an explicit intervention applied) under an equivalent
workload. Every comparison and conclusion below is deterministic — no LLM, no
statistical significance inventions, no fabricated data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from guardrail.models.base import GuardrailModel, RuleCategory, generate_id
from guardrail.models.measurement import Measurement


def utc_now() -> datetime:
    return datetime.now(UTC)


class ConditionKind(str, Enum):
    """The two arms of a controlled experiment."""

    CONTROL = "CONTROL"
    TREATMENT = "TREATMENT"


class EffectDirection(str, Enum):
    """Predicted direction of a metric under the intervention."""

    INCREASE = "increase"
    DECREASE = "decrease"


class ExperimentValidity(str, Enum):
    """Structural validity of an experiment's evidence.

    * VALID             -- both conditions exercised, intervention applied,
                            workload was equivalent, and required mechanism
                            metrics were measured.
    * INSUFFICIENT_DATA -- the experiment ran but could not support or refute
                            causality (zero requests, missing mechanism telemetry,
                            workload mismatch, control value zero, too few samples).
    * INVALID           -- the experiment was structurally broken (intervention
                            not applied, malformed measurements).
    """

    VALID = "VALID"
    INVALID = "INVALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Hypothesis(GuardrailModel):
    """A falsifiable claim about a mechanism that a finding's risk depends on."""

    id: str
    statement: str
    finding_id: str
    category: RuleCategory
    target_endpoint: str
    preconditions: list[Precondition] = Field(default_factory=list)


class Precondition(GuardrailModel):
    """A condition that must hold before an experiment is meaningful.

    ``check`` is a symbolic name that the runtime provider resolves against the
    real system (e.g. ``db_telemetry_available``). It is descriptive, not code.
    """

    id: str
    description: str
    check: str = ""


class PreconditionCheck(GuardrailModel):
    """The result of evaluating a precondition against the real system."""

    precondition_id: str
    description: str
    satisfied: bool
    detail: str = ""


class Intervention(GuardrailModel):
    """The explicit, minimal difference between control and treatment."""

    id: str
    description: str
    change_description: str = ""
    applied: bool = False
    failure_reason: str | None = None


class ExperimentWorkload(GuardrailModel):
    """The workload definition applied to BOTH control and treatment.

    Workload equivalence is structural: control and treatment must use the same
    definition (endpoint, method, payload, headers, target RPS, duration,
    concurrency). The delivered load is then compared after the fact; a material
    difference below target makes the comparison INSUFFICIENT_DATA.
    """

    endpoint: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] | None = None
    target_rps: float
    duration_seconds: float
    concurrency: int = 50
    definition_key: str = ""

    def key(self) -> str:
        """Stable identity of the workload definition (parity invariant)."""
        if self.definition_key:
            return self.definition_key
        import json

        return json.dumps(
            {
                "endpoint": self.endpoint,
                "method": self.method,
                "headers": sorted(self.headers.items()),
                "payload": self.payload,
                "target_rps": self.target_rps,
                "duration_seconds": self.duration_seconds,
                "concurrency": self.concurrency,
            },
            sort_keys=True,
            default=str,
        )


class EvidenceExpectation(GuardrailModel):
    """A single expected effect: mechanism metric vs corroborating symptom.

    * mechanism metrics   -- must move in the predicted direction to SUPPORT.
    * corroborating metrics -- cannot cause SUPPORT alone; a strong contrary
                              movement can REFUTE (contradicts the hypothesis).
    """

    metric: str
    direction: EffectDirection
    min_relative_change: float = 0.5
    role: str = "mechanism"  # "mechanism" | "corroborating"
    required: bool = True


class Experiment(GuardrailModel):
    """Definition of a controlled experiment for a hypothesis."""

    id: str
    hypothesis: Hypothesis
    interventions: list[Intervention] = Field(default_factory=list)
    expectations: list[EvidenceExpectation] = Field(default_factory=list)
    default_workload: ExperimentWorkload | None = None
    repetitions: int = 1
    workload_tolerance: float = 0.2
    refute_on_flat_mechanism: bool = False


class Observation(GuardrailModel):
    """A single measured condition run (control or treatment, one repetition)."""

    id: str = Field(default_factory=generate_id)
    experiment_run_id: str = ""
    condition: ConditionKind
    repetition: int
    measurement: Measurement
    workload_definition_key: str = ""
    delivered_requests: int = 0
    achieved_rps: float = 0.0
    offered_rps: float = 0.0

    @property
    def delivered_ratio(self) -> float:
        if self.offered_rps <= 0:
            return 0.0
        return self.achieved_rps / self.offered_rps


class MetricComparison(GuardrailModel):
    """Deterministic comparison of one metric between control and treatment."""

    metric: str
    role: str
    measured: bool
    not_measured_reason: str | None = None
    control_samples: list[float] = Field(default_factory=list)
    treatment_samples: list[float] = Field(default_factory=list)
    control_median: float | None = None
    treatment_median: float | None = None
    relative_change: float | None = None
    predicted_direction: str | None = None
    min_relative_change: float | None = None
    meets_prediction: bool | None = None
    contradicts: bool | None = None


class Comparison(GuardrailModel):
    """Aggregate comparison of control vs treatment across repetitions."""

    experiment_id: str
    control_observation_ids: list[str] = Field(default_factory=list)
    treatment_observation_ids: list[str] = Field(default_factory=list)
    samples_per_condition: int = 0
    workload_equivalent: bool = False
    workload_equivalence_reason: str = ""
    control_achieved_rps: list[float] = Field(default_factory=list)
    treatment_achieved_rps: list[float] = Field(default_factory=list)
    metrics: list[MetricComparison] = Field(default_factory=list)


class ExperimentConclusion(GuardrailModel):
    """The deterministic verdict of a controlled experiment."""

    status: str  # SUPPORTED | REFUTED | INCONCLUSIVE
    validity: ExperimentValidity = ExperimentValidity.INSUFFICIENT_DATA
    reasons: list[str] = Field(default_factory=list)
    evidence_observation_ids: list[str] = Field(default_factory=list)
    metric_summary: list[MetricComparison] = Field(default_factory=list)
    experiment_id: str = ""
    hypothesis_id: str = ""
    decided_at: datetime = Field(default_factory=utc_now)


class ExperimentRun(GuardrailModel):
    """A complete controlled experiment execution: inputs, process and outcome."""

    id: str = Field(default_factory=generate_id)
    experiment: Experiment
    workload: ExperimentWorkload
    preconditions: list[PreconditionCheck] = Field(default_factory=list)
    intervention: Intervention | None = None
    control_observations: list[Observation] = Field(default_factory=list)
    treatment_observations: list[Observation] = Field(default_factory=list)
    comparison: Comparison | None = None
    conclusion: ExperimentConclusion
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
