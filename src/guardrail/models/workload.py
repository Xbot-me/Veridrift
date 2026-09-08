from __future__ import annotations

from typing import Any

from pydantic import Field

from guardrail.models.base import GuardrailModel, TrafficPattern


class WorkloadStage(GuardrailModel):
    """A distinct stage in a workload scenario."""

    duration_seconds: float
    target_rps: float | None = None
    concurrent_users: int | None = None
    ramp_to_rps: float | None = None
    ramp_to_users: int | None = None


class WorkloadScenario(GuardrailModel):
    """A traffic workload scenario."""

    name: str
    description: str = ""
    pattern: TrafficPattern
    stages: list[WorkloadStage] = Field(default_factory=list)
    protocol: str = "http"
    target_url: str | None = None
    endpoints: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] | None = None
    timeout_seconds: float = 30.0


class AmplificationModel(GuardrailModel):
    """Model for calculating traffic amplification."""

    source: str
    client_count: int
    interval_seconds: float | None = None
    requests_per_trigger: int = 1
    db_queries_per_request: int = 0
    theoretical_rps: float = 0.0
    theoretical_db_qps: float = 0.0
    measured_rps: float | None = None
    measured_db_qps: float | None = None
    amplification_factor: float | None = None
