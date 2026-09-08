from __future__ import annotations

from pydantic import Field

from guardrail.models.base import GuardrailModel, Severity, ThresholdOperator


class PolicyThreshold(GuardrailModel):
    """A metric threshold for production policies.

    ``required`` marks the metric as mandatory evidence: if the run produced no
    measurement for it, the threshold evaluation FAILs instead of being silently
    skipped (verification-integrity guard). Non-required thresholds are evaluated
    only when the metric is present and are acknowledged as known gaps.
    """

    metric: str
    operator: ThresholdOperator
    value: float
    severity: Severity
    description: str = ""
    required: bool = False


class Policy(GuardrailModel):
    """A collection of thresholds dictating production readiness."""

    name: str
    version: str = "1.0"
    description: str = ""
    thresholds: list[PolicyThreshold] = Field(default_factory=list)

    @classmethod
    def default(cls) -> Policy:
        """Create a sensible default production policy."""
        return cls(
            name="default",
            version="1.0",
            description="Default production readiness policy",
            thresholds=[
                PolicyThreshold(
                    metric="p95_latency_ms",
                    operator=ThresholdOperator.LTE,
                    value=500.0,
                    severity=Severity.HIGH,
                    required=True,
                    description="p95 latency must be <= 500ms",
                ),
                PolicyThreshold(
                    metric="p99_latency_ms",
                    operator=ThresholdOperator.LTE,
                    value=1000.0,
                    severity=Severity.HIGH,
                    required=True,
                    description="p99 latency must be <= 1000ms",
                ),
                PolicyThreshold(
                    metric="error_rate",
                    operator=ThresholdOperator.LTE,
                    value=0.01,
                    severity=Severity.CRITICAL,
                    required=True,
                    description="Error rate must be <= 1%",
                ),
                PolicyThreshold(
                    metric="cpu_percent",
                    operator=ThresholdOperator.LTE,
                    value=80.0,
                    severity=Severity.HIGH,
                    required=True,
                    description="CPU usage must be <= 80%",
                ),
                PolicyThreshold(
                    metric="memory_percent",
                    operator=ThresholdOperator.LTE,
                    value=80.0,
                    severity=Severity.HIGH,
                    required=True,
                    description="Memory usage must be <= 80%",
                ),
                PolicyThreshold(
                    metric="db_connection_utilization",
                    operator=ThresholdOperator.LTE,
                    value=0.80,
                    severity=Severity.HIGH,
                    required=False,
                    description=(
                        "DB connection utilization must be <= 80% "
                        "(known instrumentation gap; non-required until measured)"
                    ),
                ),
            ],
        )
