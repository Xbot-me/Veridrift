"""Policy engine for evaluating measurements against hard thresholds.

The policy engine is the final arbiter. It takes measurements and applies
deterministic threshold rules to produce PASS/WARNING/FAIL verdicts.
An LLM is never allowed to override these verdicts.
"""

from __future__ import annotations

import math
from typing import Any

from guardrail.models.base import (
    Severity,
    ThresholdOperator,
    VerdictStatus,
)
from guardrail.models.measurement import (
    DatabaseMetrics,
    Measurement,
    MeasurementValidity,
    RequestMetrics,
    ResourceMetrics,
)
from guardrail.models.policy import Policy
from guardrail.models.verdict import Verdict
from guardrail.utils import GuardrailLogger

logger = GuardrailLogger.get_logger("policy.engine")


def _check_threshold(operator: ThresholdOperator, observed: float, limit: float) -> bool:
    """Check if an observed value breaches a threshold.

    Returns True if the threshold is BREACHED (i.e., the value is bad).
    Non-finite values are always treated as breached: garbage must not PASS.
    """
    if observed is not None and not math.isfinite(observed):
        return True
    if operator == ThresholdOperator.LTE:
        return observed > limit
    elif operator == ThresholdOperator.LT:
        return observed >= limit
    elif operator == ThresholdOperator.GTE:
        return observed < limit
    elif operator == ThresholdOperator.GT:
        return observed <= limit
    elif operator == ThresholdOperator.EQ:
        return observed != limit
    return False


def _extract_metric_value(
    metric_name: str,
    request_metrics: RequestMetrics | None,
    resource_metrics: ResourceMetrics | None,
    database_metrics: DatabaseMetrics | None,
) -> float | None:
    """Extract a metric value by name from measurement data."""
    metric_map: dict[str, Any] = {}

    if request_metrics:
        metric_map.update(
            {
                "p50_latency_ms": request_metrics.latency.p50_ms,
                "p95_latency_ms": request_metrics.latency.p95_ms,
                "p99_latency_ms": request_metrics.latency.p99_ms,
                "error_rate": request_metrics.error_rate,
                "client_error_rate": request_metrics.client_error_rate,
                "requests_per_second": request_metrics.requests_per_second,
                "total_requests": float(request_metrics.total_requests),
                "failed_requests": float(request_metrics.failed_requests),
            }
        )
        if request_metrics.latency.p75_ms is not None:
            metric_map["p75_latency_ms"] = request_metrics.latency.p75_ms
        if request_metrics.latency.p90_ms is not None:
            metric_map["p90_latency_ms"] = request_metrics.latency.p90_ms

    if resource_metrics:
        metric_map.update(
            {
                "cpu_percent": resource_metrics.cpu_percent,
                "memory_mb": resource_metrics.memory_mb,
                "memory_percent": resource_metrics.memory_percent,
                "network_rx_bytes": float(resource_metrics.network_rx_bytes),
                "network_tx_bytes": float(resource_metrics.network_tx_bytes),
                "active_connections": float(resource_metrics.active_connections or 0),
                "open_file_descriptors": float(resource_metrics.open_file_descriptors or 0),
            }
        )

    if database_metrics:
        metric_map.update(
            {
                "db_query_count": float(database_metrics.query_count),
                "db_query_rate": database_metrics.query_rate_per_second,
                "db_avg_query_latency_ms": database_metrics.avg_query_latency_ms,
                "db_active_connections": float(database_metrics.active_connections),
                "db_connection_utilization": database_metrics.connection_utilization or 0.0,
                "db_cache_hit_ratio": database_metrics.cache_hit_ratio or 0.0,
                "db_cpu_percent": database_metrics.cpu_percent or 0.0,
            }
        )
        if database_metrics.max_query_latency_ms is not None:
            metric_map["db_max_query_latency_ms"] = database_metrics.max_query_latency_ms

    return metric_map.get(metric_name)


class PolicyEngine:
    """Evaluates measurements against policy thresholds.

    The policy engine is deterministic. Given the same measurements and policy,
    it will always produce the same verdicts. No LLM involvement.
    """

    def __init__(self, policy: Policy) -> None:
        """Initialize with a policy definition.

        Args:
            policy: The policy containing thresholds to evaluate against.
        """
        self.policy = policy

    def evaluate_measurement(
        self,
        measurement: Measurement,
        workload_context: str = "",
    ) -> list[Verdict]:
        """Evaluate a single measurement against all policy thresholds.

        Args:
            measurement: The measurement to evaluate.
            workload_context: Human-readable description of the workload.

        Returns:
            List of verdicts (one per breached threshold, plus an overall).
        """
        verdicts: list[Verdict] = []

        if measurement.validity == MeasurementValidity.INSUFFICIENT_DATA:
            reasons = "; ".join(measurement.validity_reasons) or "no usable samples"
            verdicts.append(
                Verdict(
                    status=VerdictStatus.FAIL,
                    category="insufficient_data",
                    reason=f"Insufficient data to assess policy: {reasons}",
                    evidence_ids=[measurement.id],
                    workload_context=workload_context,
                )
            )
            return verdicts

        if measurement.validity == MeasurementValidity.INVALID:
            reasons = "; ".join(measurement.validity_reasons) or "malformed measurements"
            verdicts.append(
                Verdict(
                    status=VerdictStatus.FAIL,
                    category="invalid_measurement",
                    reason=f"Measurement rejected as invalid evidence: {reasons}",
                    evidence_ids=[measurement.id],
                    workload_context=workload_context,
                )
            )
            logger.error(
                "Invalid measurement %s rejected: %s", measurement.id, "; ".join(measurement.validity_reasons)
            )
            return verdicts

        for threshold in self.policy.thresholds:
            observed = _extract_metric_value(
                threshold.metric,
                measurement.request_metrics,
                measurement.resource_metrics,
                measurement.database_metrics,
            )

            if observed is None:
                if threshold.required:
                    verdicts.append(
                        Verdict(
                            status=VerdictStatus.FAIL,
                            category=f"{threshold.metric}_not_measured",
                            reason=(
                                f"Required metric '{threshold.metric}' was not measured; "
                                "PASS cannot be granted without it."
                            ),
                            evidence_ids=[measurement.id],
                            threshold_breached=threshold,
                            workload_context=workload_context,
                        )
                    )
                    logger.warning(
                        "Required metric %s missing → FAIL (%s)", threshold.metric, threshold.description
                    )
                continue

            breached = _check_threshold(threshold.operator, observed, threshold.value)

            if breached:
                severity_to_status = {
                    Severity.CRITICAL: VerdictStatus.FAIL,
                    Severity.HIGH: VerdictStatus.FAIL,
                    Severity.MEDIUM: VerdictStatus.WARNING,
                    Severity.LOW: VerdictStatus.WARNING,
                    Severity.INFO: VerdictStatus.PASS,
                }
                status = severity_to_status.get(threshold.severity, VerdictStatus.FAIL)

                verdict = Verdict(
                    status=status,
                    category=threshold.metric,
                    reason=(
                        f"{threshold.description or threshold.metric} breached. "
                        f"Observed: {observed:.4g}, "
                        f"Threshold: {threshold.operator.value} {threshold.value:.4g}"
                    ),
                    evidence_ids=[measurement.id],
                    threshold_breached=threshold,
                    observed_value=observed,
                    workload_context=workload_context,
                )
                verdicts.append(verdict)
                logger.info(
                    "Threshold breached: %s = %.4g (limit: %s %s) → %s",
                    threshold.metric,
                    observed,
                    threshold.operator.value,
                    threshold.value,
                    status.value,
                )

        return verdicts

    def evaluate_all_measurements(
        self,
        measurements: list[Measurement],
        workload_context: str = "",
    ) -> list[Verdict]:
        """Evaluate all measurements and return all verdicts.

        Args:
            measurements: List of measurements to evaluate.
            workload_context: Human-readable workload description.

        Returns:
            Combined list of all verdicts.
        """
        all_verdicts: list[Verdict] = []
        for measurement in measurements:
            verdicts = self.evaluate_measurement(measurement, workload_context)
            all_verdicts.extend(verdicts)
        return all_verdicts

    def compute_final_verdict(self, verdicts: list[Verdict]) -> VerdictStatus:
        """Compute the overall final verdict from individual verdicts.

        Precedence (worst wins): FAIL > INCONCLUSIVE > WARNING > PASS.

        An empty verdict list is treated as neutral PASS only in the sense that
        nothing was evaluated; orchestrators that want evidence-sufficiency to be
        part of the verdict MUST append explicit INCONCLUSIVE verdicts (e.g.
        ``Verdict(status=INCONCLUSIVE, category="evidence_sufficiency", ...)``).
        A single FAIL makes the entire run FAIL.
        """
        if not verdicts:
            return VerdictStatus.PASS

        if any(v.status == VerdictStatus.FAIL for v in verdicts):
            return VerdictStatus.FAIL
        if any(v.status == VerdictStatus.INCONCLUSIVE for v in verdicts):
            return VerdictStatus.INCONCLUSIVE
        if any(v.status == VerdictStatus.WARNING for v in verdicts):
            return VerdictStatus.WARNING
        return VerdictStatus.PASS

    def evaluate_static_findings_severity(
        self,
        findings_by_severity: dict[Severity, int],
    ) -> list[Verdict]:
        """Generate verdicts based on static finding severity counts.

        Args:
            findings_by_severity: Count of findings per severity level.

        Returns:
            Verdicts for static analysis results.
        """
        verdicts: list[Verdict] = []

        critical_count = findings_by_severity.get(Severity.CRITICAL, 0)
        high_count = findings_by_severity.get(Severity.HIGH, 0)

        if critical_count > 0:
            verdicts.append(
                Verdict(
                    status=VerdictStatus.FAIL,
                    category="static_analysis",
                    reason=f"{critical_count} CRITICAL static finding(s) detected.",
                    observed_value=float(critical_count),
                )
            )

        if high_count > 0:
            verdicts.append(
                Verdict(
                    status=VerdictStatus.WARNING,
                    category="static_analysis",
                    reason=f"{high_count} HIGH severity static finding(s) detected.",
                    observed_value=float(high_count),
                )
            )

        return verdicts
