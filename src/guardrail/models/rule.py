from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field, model_validator

from guardrail.models.base import (
    Confidence,
    GuardrailModel,
    HypothesisStatus,
    RuleCategory,
    Severity,
    generate_id,
)
from guardrail.models.evidence import Evidence


def utc_now() -> datetime:
    return datetime.now(UTC)


class Rule(GuardrailModel):
    """Definition of a guardrail rule."""

    id: str
    category: RuleCategory
    severity: Severity
    name: str
    description: str
    detection_logic: str = ""
    languages: list[str] = Field(default_factory=list)
    version: str = "1.0"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class Finding(GuardrailModel):
    """An instance of a rule violation or warning."""

    id: str = Field(default_factory=generate_id)
    rule_id: str
    rule_name: str
    category: RuleCategory
    severity: Severity
    confidence: Confidence
    message: str
    file_path: str | None = None
    line_number: int | None = None
    end_line_number: int | None = None
    code_snippet: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    recommendation: str | None = None
    potential_consequence: str | None = None
    hypothesized_risk: str | None = None
    hypothesis_status: HypothesisStatus = HypothesisStatus.DETECTED
    controlled_experiment_id: str | None = None
    condition_confirmed: bool = True
    exercised_endpoints: list[str] = Field(default_factory=list)
    evidence_summary: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _require_controlled_provenance_for_causal_outcomes(self) -> Finding:
        """SUPPORTED/REFUTED are casual outcomes: they are only valid when
        backed by an actual Controlled Experiment result (Milestone 7).

        A finding that claims SUPPORTED/REFUTED must reference the experiment
        that produced it. Synthetic or hand-crafted causal outcomes without a
        ``controlled_experiment_id`` are structurally rejected so that old
        fabricated evidence cannot be re-imported or re-serialized.
        """
        if (
            self.hypothesis_status
            in (
                HypothesisStatus.SUPPORTED,
                HypothesisStatus.REFUTED,
            )
            and not self.controlled_experiment_id
        ):
            raise ValueError(
                f"{self.rule_id} claims {self.hypothesis_status.value} without a "
                "controlled_experiment_id. SUPPORTED/REFUTED require a valid "
                "Controlled Experiment result; observational correlation can only "
                "reach DETECTED/EXERCISED/OBSERVED/INCONCLUSIVE."
            )
        return self
