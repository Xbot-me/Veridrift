from __future__ import annotations

import math
from datetime import datetime
from enum import Enum

from pydantic import Field, model_validator

from guardrail.models.base import GuardrailModel, generate_id


class MeasurementValidity(str, Enum):
    """Validity of a measurement as evidence for verdicts.

    * VALID               -- measurement is structurally sound and usable as evidence.
    * INSUFFICIENT_DATA   -- measurement exists but carries no usable sample
                             (e.g. zero requests were offered).
    * INVALID             -- measurement is structurally malformed (NaN/Inf/negative
                             rates, inconsistent counters) and must NOT be trusted.
    """

    VALID = "VALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID = "INVALID"


class MetricSample(GuardrailModel):
    """A specific sample of a metric."""

    timestamp: datetime
    metric: str
    value: float
    unit: str = ""
    labels: dict[str, str] = Field(default_factory=dict)


class LatencyDistribution(GuardrailModel):
    """Distribution of latencies for a request."""

    p50_ms: float
    p75_ms: float | None = None
    p90_ms: float | None = None
    p95_ms: float
    p99_ms: float
    min_ms: float | None = None
    max_ms: float | None = None
    mean_ms: float | None = None
    stddev_ms: float | None = None


class LoadAccounting(GuardrailModel):
    """Detailed load generation and delivery accounting."""

    target_rps: float
    offered_rps: float
    achieved_rps: float
    successful_rps: float
    failed_rps: float
    delivery_ratio: float
    is_saturated: bool = False
    saturation_reason: str | None = None


class RequestMetrics(GuardrailModel):
    """Metrics related to HTTP or generic requests.

    Error taxonomy:
      * *client_errors*   -- HTTP 4xx responses (client-side contract failures).
      * *server_errors*   -- HTTP 5xx responses (server-side failures).
      * *network_errors*  -- transport-level failures (connect refused, DNS, resets).
      * *timeouts*        -- request deadlines exceeded.
      * *error_rate*      -- production-meaningful failure rate:
                             (server_errors + network_errors + timeouts) / total.
      * *client_error_rate* -- share of 4xx responses over total; informational and
                             intentionally excluded from ``error_rate`` (a 404 does
                             NOT mean the service is failing).
    """

    timestamp: datetime
    duration_seconds: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    client_errors: int = 0
    server_errors: int = 0
    network_errors: int = 0
    timeouts: int = 0
    requests_per_second: float
    error_rate: float
    client_error_rate: float = 0.0
    latency: LatencyDistribution
    status_codes: dict[int, int] = Field(default_factory=dict)
    load_accounting: LoadAccounting | None = None


class ResourceMetrics(GuardrailModel):
    """Metrics regarding hardware or system resources."""

    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    memory_percent: float | None = None
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0
    disk_read_bytes: int = 0
    disk_write_bytes: int = 0
    open_file_descriptors: int | None = None
    active_connections: int | None = None
    process_count: int | None = None


class DatabaseMetrics(GuardrailModel):
    """Database-specific metrics."""

    timestamp: datetime
    query_count: int
    query_rate_per_second: float
    avg_query_latency_ms: float
    max_query_latency_ms: float | None = None
    active_connections: int
    max_connections: int | None = None
    connection_utilization: float | None = None
    cache_hit_ratio: float | None = None
    cpu_percent: float | None = None
    slowest_queries: list[str] = Field(default_factory=list)


class Measurement(GuardrailModel):
    """A complete measurement record from a run."""

    id: str = Field(default_factory=generate_id)
    run_id: str
    timestamp: datetime
    workload_rps: float | None = None
    request_metrics: RequestMetrics | None = None
    resource_metrics: ResourceMetrics | None = None
    database_metrics: DatabaseMetrics | None = None
    custom_metrics: list[MetricSample] = Field(default_factory=list)
    validity: MeasurementValidity = MeasurementValidity.VALID
    validity_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_measurement(self) -> Measurement:
        """Derive structural validity; never trust a malformed sample."""
        reasons: list[str] = []
        if self.request_metrics is None and self.resource_metrics is None and self.database_metrics is None:
            self.validity = MeasurementValidity.INSUFFICIENT_DATA
            reasons.append("measurement carries no usable metric samples")
            self.validity_reasons = reasons
            return self

        if self.request_metrics is not None and self.request_metrics.total_requests == 0:
            self.validity = MeasurementValidity.INSUFFICIENT_DATA
            reasons.append("workload produced zero requests; no evidence to assess")
            self.validity_reasons = reasons
            return self

        def _non_finite(value: int | float | None) -> bool:
            return value is not None and not math.isfinite(float(value))

        bad: list[str] = []
        rm = self.request_metrics
        if rm is not None:
            if rm.total_requests < 0 or rm.successful_requests < 0 or rm.failed_requests < 0:
                bad.append("request counters are negative")
            if rm.successful_requests + rm.failed_requests != rm.total_requests:
                bad.append("successful + failed != total_requests")
            for name, value in (
                ("requests_per_second", rm.requests_per_second),
                ("error_rate", rm.error_rate),
                ("client_error_rate", rm.client_error_rate),
            ):
                if _non_finite(value):
                    bad.append(f"{name} is NaN/Inf")
            for name, value in (
                ("cpu_percent", self.resource_metrics.cpu_percent if self.resource_metrics else None),
                ("memory_percent", self.resource_metrics.memory_percent if self.resource_metrics else None),
                ("connection_utilization", self.database_metrics.connection_utilization if self.database_metrics else None),
                ("query_rate_per_second", self.database_metrics.query_rate_per_second if self.database_metrics else None),
            ):
                if _non_finite(value):
                    bad.append(f"{name} is NaN/Inf")

        if bad:
            self.validity = MeasurementValidity.INVALID
            reasons = bad
        else:
            self.validity = MeasurementValidity.VALID
            reasons = []
        self.validity_reasons = reasons
        return self
