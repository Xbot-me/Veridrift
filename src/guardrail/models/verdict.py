from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from guardrail.models.base import Confidence, GuardrailModel, ValidityLevel, VerdictStatus
from guardrail.models.policy import PolicyThreshold


def utc_now() -> datetime:
    return datetime.now(UTC)


class Verdict(GuardrailModel):
    """The outcome of evaluating a policy or rule."""

    status: VerdictStatus
    category: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    threshold_breached: PolicyThreshold | None = None
    observed_value: float | None = None
    workload_context: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class CapacityResult(GuardrailModel):
    """The result of capacity planning or load testing."""

    sustainable_rps: float | None = None
    degradation_rps: float | None = None
    failure_rps: float | None = None
    safe_rps: float | None = None
    warning_rps: float | None = None
    primary_bottleneck: str | None = None
    secondary_bottleneck: str | None = None
    confidence: Confidence = Confidence.POSSIBLE
    evidence_ids: list[str] = Field(default_factory=list)
    bottleneck_details: dict[str, Any] = Field(default_factory=dict)
    stages_tested: list[dict[str, Any]] = Field(default_factory=list)
    boundary_definitions: dict[str, str] = Field(default_factory=dict)
    validity: ValidityLevel = ValidityLevel.MEDIUM
    validity_reasons: list[str] = Field(default_factory=list)
