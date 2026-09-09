from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from guardrail.capacity.engine import CapacityDiscoveryEngine
from guardrail.models.measurement import (
    LatencyDistribution,
    Measurement,
    RequestMetrics,
    ResourceMetrics,
)
from guardrail.models.policy import Policy
from guardrail.models.target import Target
from guardrail.runtime.adapter import RuntimeInstance


def test_bottleneck_identification_latency():
    engine = CapacityDiscoveryEngine(runtime=MagicMock())
    measurement = Measurement(
        run_id="r1",
        timestamp=datetime.now(UTC),
        request_metrics=RequestMetrics(
            timestamp=datetime.now(UTC),
            duration_seconds=1.0,
            total_requests=100,
            successful_requests=100,
            failed_requests=0,
            requests_per_second=100.0,
            error_rate=0.0,
            latency=LatencyDistribution(p50_ms=200.0, p95_ms=800.0, p99_ms=1200.0),
        ),
        resource_metrics=ResourceMetrics(
            timestamp=datetime.now(UTC),
            cpu_percent=30.0,
            memory_mb=100.0,
        ),
    )
    primary, _secondary, details = engine._identify_bottlenecks(measurement)
    assert primary == "p95_latency_exceeded"
    assert "p95_latency_ms" in details


def test_bottleneck_identification_error_rate():
    engine = CapacityDiscoveryEngine(runtime=MagicMock())
    measurement = Measurement(
        run_id="r1",
        timestamp=datetime.now(UTC),
        request_metrics=RequestMetrics(
            timestamp=datetime.now(UTC),
            duration_seconds=1.0,
            total_requests=100,
            successful_requests=80,
            failed_requests=20,
            requests_per_second=100.0,
            error_rate=0.20,
            latency=LatencyDistribution(p50_ms=50.0, p95_ms=100.0, p99_ms=150.0),
        ),
        resource_metrics=ResourceMetrics(
            timestamp=datetime.now(UTC),
            cpu_percent=40.0,
            memory_mb=120.0,
        ),
    )
    primary, _secondary, _details = engine._identify_bottlenecks(measurement)
    assert primary == "error_rate_spike"


def test_capacity_discovery_flow_with_refinement():
    mock_runtime = MagicMock()
    mock_runtime.get_metrics.return_value = ResourceMetrics(
        timestamp=datetime.now(UTC),
        cpu_percent=25.0,
        memory_mb=64.0,
        memory_percent=10.0,
    )

    mock_generator = MagicMock()

    # Define response behavior: pass at 10 and 25, fail at 50
    def mock_generate(target_url, target_rps, duration_seconds):
        error_rate = 0.0 if target_rps <= 25.0 else 0.5
        latency_p95 = 50.0 if target_rps <= 25.0 else 2000.0
        total = int(target_rps * duration_seconds)
        successful = int(total * (1.0 - error_rate))
        return RequestMetrics(
            timestamp=datetime.now(UTC),
            duration_seconds=duration_seconds,
            total_requests=total,
            successful_requests=successful,
            failed_requests=total - successful,  # counters must stay consistent
            requests_per_second=target_rps,
            error_rate=error_rate,
            latency=LatencyDistribution(
                p50_ms=latency_p95 / 2, p95_ms=latency_p95, p99_ms=latency_p95 * 1.2
            ),
        )

    mock_generator.generate.side_effect = mock_generate

    engine = CapacityDiscoveryEngine(
        runtime=mock_runtime,
        policy=Policy.default(),
        generator=mock_generator,
    )

    instance = RuntimeInstance(
        instance_id="test_inst",
        target=Target(path=".", name="test_app", languages=["python"], frameworks=[]),
        host="127.0.0.1",
        port=8080,
        base_url="http://127.0.0.1:8080",
    )

    cap_res, measurements, verdicts = engine.discover_capacity(
        instance=instance,
        endpoint_path="/api/test",
        initial_stages=[10.0, 25.0, 50.0],
        stage_duration_seconds=0.1,
        refine_iterations=2,
    )

    assert cap_res.safe_rps is not None
    assert cap_res.safe_rps >= 25.0
    assert cap_res.failure_rps is not None
    assert cap_res.failure_rps <= 50.0
    assert len(measurements) >= 3
    assert len(verdicts) > 0
