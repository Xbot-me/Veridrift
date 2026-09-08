from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from guardrail.models.base import GuardrailModel, VerdictStatus, generate_id
from guardrail.models.environment import Environment
from guardrail.models.measurement import Measurement
from guardrail.models.policy import Policy
from guardrail.models.rule import Finding
from guardrail.models.target import Target
from guardrail.models.verdict import CapacityResult, Verdict
from guardrail.models.workload import AmplificationModel, WorkloadScenario


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunMetadata(GuardrailModel):
    """Metadata regarding a verification run execution."""

    commit_hash: str | None = None
    branch: str | None = None
    application_version: str | None = None
    guardrail_version: str
    ruleset_version: str = "1.0"
    start_time: datetime
    end_time: datetime | None = None
    duration_seconds: float | None = None
    machine_info: dict[str, str] = Field(default_factory=dict)
    container_versions: dict[str, str] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)


class VerificationRun(GuardrailModel):
    """The aggregate record of a verification run."""

    id: str = Field(default_factory=generate_id)
    schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=utc_now)
    target: Target
    environment: Environment
    workload: WorkloadScenario | None = None
    policy: Policy
    static_findings: list[Finding] = Field(default_factory=list)
    runtime_findings: list[Finding] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    verdicts: list[Verdict] = Field(default_factory=list)
    capacity: CapacityResult | None = None
    amplification: list[AmplificationModel] = Field(default_factory=list)
    final_verdict: VerdictStatus = VerdictStatus.PASS
    metadata: RunMetadata
