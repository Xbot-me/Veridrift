"""Deterministic extraction of mechanism-specific metrics from a Measurement.

The metric vocabulary used by experiment expectations must map to the actual
Measurement structure. Extractors here are the only place this mapping lives;
an unknown metric is NOT_MEASURED, never fabricated nor defaulted to zero.
"""

from __future__ import annotations

import math

from guardrail.models.measurement import DatabaseMetrics, RequestMetrics, ResourceMetrics


class MetricValue:
    """Result of extracting one metric from a measurement."""

    __slots__ = ("measured", "reason", "value")

    def __init__(
        self, value: float | None, measured: bool = True, reason: str | None = None
    ) -> None:
        self.value = value
        self.measured = measured
        self.reason = reason


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value))


def extract_metric(
    metric: str,
    request_metrics: RequestMetrics | None,
    resource_metrics: ResourceMetrics | None,
    database_metrics: DatabaseMetrics | None,
) -> MetricValue:
    """Extract a metric by name.

    Returns MetricValue with measured=False (never a fabricated zero) when the
    underlying telemetry is absent. Derived metrics (db_queries_per_request)
    return NOT_MEASURED when the denominator or numerator is missing or zero.
    """
    if metric == "db_queries_per_request":
        if database_metrics is None or request_metrics is None:
            return MetricValue(None, False, reason="db telemetry is not instrumented")
        successful = request_metrics.successful_requests
        if successful <= 0:
            return MetricValue(None, False, reason="no successful requests to normalize against")
        return MetricValue(database_metrics.query_count / successful, measured=True)
    if metric == "db_queries_per_second":
        if database_metrics is None:
            return MetricValue(None, False, reason="db telemetry is not instrumented")
        return MetricValue(
            database_metrics.query_rate_per_second,
            measured=_finite(database_metrics.query_rate_per_second),
        )
    if metric == "db_query_latency_ms":
        if database_metrics is None:
            return MetricValue(None, False, reason="db telemetry is not instrumented")
        return MetricValue(
            database_metrics.avg_query_latency_ms,
            measured=_finite(database_metrics.avg_query_latency_ms),
        )
    if metric == "db_connection_utilization":
        if database_metrics is None:
            return MetricValue(None, False, reason="db telemetry is not instrumented")
        return MetricValue(
            database_metrics.connection_utilization,
            measured=_finite(database_metrics.connection_utilization),
        )
    if metric == "p95_latency_ms":
        if request_metrics is None:
            return MetricValue(None, False, reason="no request metrics")
        return MetricValue(
            request_metrics.latency.p95_ms, measured=_finite(request_metrics.latency.p95_ms)
        )
    if metric == "p99_latency_ms":
        if request_metrics is None:
            return MetricValue(None, False, reason="no request metrics")
        return MetricValue(
            request_metrics.latency.p99_ms, measured=_finite(request_metrics.latency.p99_ms)
        )
    if metric == "cpu_percent":
        if resource_metrics is None:
            return MetricValue(None, False, reason="no resource metrics")
        return MetricValue(
            resource_metrics.cpu_percent, measured=_finite(resource_metrics.cpu_percent)
        )
    if metric == "error_rate":
        if request_metrics is None:
            return MetricValue(None, False, reason="no request metrics")
        return MetricValue(request_metrics.error_rate, measured=_finite(request_metrics.error_rate))
    if metric == "requests_per_second":
        if request_metrics is None:
            return MetricValue(None, False, reason="no request metrics")
        return MetricValue(
            request_metrics.requests_per_second,
            measured=_finite(request_metrics.requests_per_second),
        )
    return MetricValue(None, False, reason=f"no extractor registered for metric '{metric}'")
