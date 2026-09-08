from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from guardrail.models.base import Confidence, VerdictStatus
from guardrail.models.measurement import Measurement
from guardrail.models.policy import Policy
from guardrail.models.verdict import CapacityResult, Verdict
from guardrail.policy.engine import PolicyEngine
from guardrail.runtime.adapter import RuntimeAdapter, RuntimeInstance
from guardrail.workload.generator import HttpWorkloadGenerator

logger = logging.getLogger(__name__)


class CapacityDiscoveryEngine:
    """
    Automated empirical capacity discovery engine.
    Executes a multi-phase load ramp and binary search boundary refinement
    to discover the exact safe operating threshold and primary bottleneck.
    """

    def __init__(
        self,
        runtime: RuntimeAdapter,
        policy: Policy | None = None,
        generator: HttpWorkloadGenerator | None = None,
    ) -> None:
        self.runtime = runtime
        self.policy = policy or Policy.default()
        self.policy_engine = PolicyEngine(self.policy)
        self.generator = generator or HttpWorkloadGenerator()

    def discover_capacity(
        self,
        instance: RuntimeInstance,
        endpoint_path: str = "/",
        initial_stages: list[float] | None = None,
        stage_duration_seconds: float = 3.0,
        refine_iterations: int = 2,
        on_stage_complete: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[CapacityResult, list[Measurement], list[Verdict]]:
        """
        Execute capacity discovery against the running instance.

        Args:
            instance: The running application instance.
            endpoint_path: Target endpoint path to test.
            initial_stages: RPS tiers for geometric ramp (default: [10, 25, 50, 100, 200]).
            stage_duration_seconds: Duration for each load test stage.
            refine_iterations: Number of binary search refinement steps.
            on_stage_complete: Optional callback invoked after each stage.

        Returns:
            Tuple of (CapacityResult, list of all Measurements, list of all Verdicts).
        """
        stages = initial_stages or [10.0, 25.0, 50.0, 100.0, 200.0]
        url = f"{instance.base_url}{endpoint_path}"

        measurements: list[Measurement] = []
        all_verdicts: list[Verdict] = []
        stage_records: list[dict[str, Any]] = []

        highest_pass_rps: float | None = None
        highest_warning_rps: float | None = None
        lowest_fail_rps: float | None = None
        failing_measurement: Measurement | None = None

        logger.info("Beginning Phase 1: Geometric traffic ramp on %s", url)

        # --- Phase 1: Geometric Load Ramp ---
        for target_rps in stages:
            stage_data = self._run_single_stage(
                instance=instance,
                url=url,
                target_rps=target_rps,
                duration=stage_duration_seconds,
            )
            measurement = stage_data["measurement"]
            verdicts = stage_data["verdicts"]
            verdict_status = stage_data["status"]

            measurements.append(measurement)
            all_verdicts.extend(verdicts)
            stage_records.append(stage_data["summary"])

            if on_stage_complete:
                on_stage_complete(stage_data["summary"])

            if verdict_status in (VerdictStatus.PASS, VerdictStatus.INCONCLUSIVE):
                # INCONCLUSIVE at the stage level means a valid workload sustained
                # with zero threshold breaches (evidence sufficiency is a run-level
                # concern, evaluated separately). For the capacity boundary this
                # counts as "the target survived this load".
                highest_pass_rps = target_rps
            elif verdict_status == VerdictStatus.WARNING:
                highest_warning_rps = target_rps
            elif verdict_status == VerdictStatus.FAIL:
                lowest_fail_rps = target_rps
                failing_measurement = measurement
                break  # Reached failure boundary, stop initial ramp

        # --- Phase 2: Binary Search Boundary Refinement ---
        if lowest_fail_rps is not None and refine_iterations > 0:
            low = highest_pass_rps or (highest_warning_rps or 5.0)
            high = lowest_fail_rps

            logger.info(
                "Beginning Phase 2: Binary search boundary refinement between %.1f and %.1f RPS",
                low,
                high,
            )

            for _ in range(refine_iterations):
                if high - low <= 5.0:
                    break  # Sufficiently refined

                mid_rps = round((low + high) / 2.0, 1)
                stage_data = self._run_single_stage(
                    instance=instance,
                    url=url,
                    target_rps=mid_rps,
                    duration=stage_duration_seconds,
                )
                measurement = stage_data["measurement"]
                verdicts = stage_data["verdicts"]
                verdict_status = stage_data["status"]

                measurements.append(measurement)
                all_verdicts.extend(verdicts)
                stage_records.append(stage_data["summary"])

                if on_stage_complete:
                    on_stage_complete(stage_data["summary"])

                if verdict_status in (
                    VerdictStatus.PASS,
                    VerdictStatus.WARNING,
                    VerdictStatus.INCONCLUSIVE,
                ):
                    low = mid_rps
                    if verdict_status in (VerdictStatus.PASS, VerdictStatus.INCONCLUSIVE):
                        highest_pass_rps = max(highest_pass_rps or 0.0, mid_rps)
                    else:
                        highest_warning_rps = max(highest_warning_rps or 0.0, mid_rps)
                else:
                    high = mid_rps
                    lowest_fail_rps = min(lowest_fail_rps, mid_rps)
                    failing_measurement = measurement

        # --- Phase 3: Bottleneck Identification ---
        primary_bottleneck, secondary_bottleneck, details = self._identify_bottlenecks(
            failing_measurement or (measurements[-1] if measurements else None)
        )

        # Derive final safe capacity
        safe_capacity = highest_pass_rps or (stages[0] if not lowest_fail_rps else 0.0)

        capacity_result = CapacityResult(
            safe_rps=safe_capacity,
            warning_rps=highest_warning_rps,
            failure_rps=lowest_fail_rps,
            primary_bottleneck=primary_bottleneck,
            secondary_bottleneck=secondary_bottleneck,
            confidence=Confidence.CONFIRMED if lowest_fail_rps is not None else Confidence.LIKELY,
            evidence_ids=[m.id for m in measurements],
            bottleneck_details=details,
            stages_tested=stage_records,
        )

        return capacity_result, measurements, all_verdicts

    def _run_single_stage(
        self,
        instance: RuntimeInstance,
        url: str,
        target_rps: float,
        duration: float,
    ) -> dict[str, Any]:
        """Execute one test stage at a target RPS and collect full telemetry."""
        # Generate traffic
        request_metrics = self.generator.generate(
            target_url=url,
            target_rps=target_rps,
            duration_seconds=duration,
        )

        # Collect resource telemetry from runtime adapter
        resource_metrics = self.runtime.get_metrics(instance)

        # Aggregate measurement
        measurement = Measurement(
            run_id=instance.instance_id,
            timestamp=datetime.now(UTC),
            workload_rps=target_rps,
            request_metrics=request_metrics,
            resource_metrics=resource_metrics,
        )

        # Evaluate policy thresholds
        verdicts = self.policy_engine.evaluate_measurement(measurement)
        final_stage_status = self.policy_engine.compute_final_verdict(verdicts)

        summary = {
            "rps": target_rps,
            "actual_rps": request_metrics.requests_per_second,
            "p50_ms": request_metrics.latency.p50_ms,
            "p95_ms": request_metrics.latency.p95_ms,
            "p99_ms": request_metrics.latency.p99_ms,
            "error_rate": request_metrics.error_rate,
            "cpu_percent": resource_metrics.cpu_percent if resource_metrics else 0.0,
            "memory_mb": resource_metrics.memory_mb if resource_metrics else 0.0,
            "status": final_stage_status.value,
        }

        return {
            "measurement": measurement,
            "verdicts": verdicts,
            "status": final_stage_status,
            "summary": summary,
        }

    def _identify_bottlenecks(
        self,
        measurement: Measurement | None,
    ) -> tuple[str | None, str | None, dict[str, Any]]:
        """Determine what caused failure or degradation."""
        if not measurement:
            return None, None, {}

        req = measurement.request_metrics
        res = measurement.resource_metrics
        details: dict[str, Any] = {}
        breaches: list[tuple[str, float]] = []

        if req:
            details["p95_latency_ms"] = req.latency.p95_ms
            details["error_rate"] = req.error_rate
            if req.latency.p95_ms > 500.0:
                breaches.append(("p95_latency_exceeded", req.latency.p95_ms / 500.0))
            if req.error_rate > 0.01:
                breaches.append(("error_rate_spike", req.error_rate / 0.01))

        if res:
            details["cpu_percent"] = res.cpu_percent
            details["memory_mb"] = res.memory_mb
            if res.cpu_percent > 80.0:
                breaches.append(("cpu_saturation", res.cpu_percent / 80.0))

        if not breaches:
            return "system_capacity_ceiling", None, details

        # Sort by relative severity
        breaches.sort(key=lambda x: x[1], reverse=True)
        primary = breaches[0][0]
        secondary = breaches[1][0] if len(breaches) > 1 else None

        return primary, secondary, details
