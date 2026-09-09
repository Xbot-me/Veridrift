"""Deterministic comparison logic for controlled experiments.

Nothing here invents data. Every metric is computed from
measurements the provider actually collected. If a mechanism metric was not
measured (missing DB telemetry, zero requests, division by zero), it is
NOT_MEASURED and the experiment must be INSUFFICIENT_DATA — it can never be
sneaked into SUPPORTED/REFUTED by substituting zero.
"""

from __future__ import annotations

import statistics

from guardrail.experiment.metrics import MetricValue, extract_metric
from guardrail.experiment.models import (
    Comparison,
    EffectDirection,
    EvidenceExpectation,
    MetricComparison,
    Observation,
)
from guardrail.models.measurement import Measurement


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.median(values)


def _relative_change(control: float | None, treatment: float | None) -> float | None:
    if control is None or treatment is None:
        return None
    if control == 0:
        return None
    return (treatment - control) / abs(control)


def compare_metric(
    expectation: EvidenceExpectation,
    control_observations: list[Observation],
    treatment_observations: list[Observation],
) -> MetricComparison:
    """Compare one expected metric between the two conditions.

    A metric is measured for a condition only when at least one observation
    returned an actual finite value for it. Missing telemetry → measured=False.
    """
    control_samples: list[float] = []
    treatment_samples: list[float] = []
    control_reason: str | None = None
    treatment_reason: str | None = None

    for obs in control_observations:
        mv: MetricValue = extract_metric(
            expectation.metric,
            obs.measurement.request_metrics,
            obs.measurement.resource_metrics,
            obs.measurement.database_metrics,
        )
        if mv.measured and mv.value is not None:
            control_samples.append(mv.value)
        elif control_reason is None:
            control_reason = mv.reason

    for obs in treatment_observations:
        mv = extract_metric(
            expectation.metric,
            obs.measurement.request_metrics,
            obs.measurement.resource_metrics,
            obs.measurement.database_metrics,
        )
        if mv.measured and mv.value is not None:
            treatment_samples.append(mv.value)
        elif treatment_reason is None:
            treatment_reason = mv.reason

    control_median = _median(control_samples)
    treatment_median = _median(treatment_samples)
    measured = control_median is not None and treatment_median is not None

    reason: str | None = None
    if not measured:
        reason = (
            "; ".join(r for r in (control_reason, treatment_reason) if r)
            or "metric not measured in either condition"
        )

    rel = _relative_change(control_median, treatment_median)

    meets_prediction: bool | None = None
    contradicts: bool | None = None
    if measured and control_median is not None and treatment_median is not None:
        direction_ok = (
            expectation.direction is EffectDirection.DECREASE and control_median > treatment_median
        ) or (
            expectation.direction is EffectDirection.INCREASE and control_median < treatment_median
        )
        threshold = expectation.min_relative_change
        if rel is not None:
            meets_prediction = bool(direction_ok and abs(rel) >= threshold)
            contradicts = bool(not direction_ok and abs(rel) >= threshold)
        else:
            if control_median == 0 and treatment_median != 0:
                reason = "control value is zero; relative change is undefined"
                measured = False
            meets_prediction = False

    return MetricComparison(
        metric=expectation.metric,
        role=expectation.role,
        measured=measured,
        not_measured_reason=reason,
        control_samples=control_samples,
        treatment_samples=treatment_samples,
        control_median=control_median,
        treatment_median=treatment_median,
        relative_change=rel,
        predicted_direction=expectation.direction.value,
        min_relative_change=expectation.min_relative_change,
        meets_prediction=meets_prediction,
        contradicts=contradicts,
    )


def _median_rps(observations: list[Observation]) -> float:
    values = [o.achieved_rps for o in observations if o.achieved_rps > 0]
    return _median(values) or 0.0


def workload_equivalent(
    control: list[Observation],
    treatment: list[Observation],
    tolerance: float,
) -> tuple[bool, str]:
    """Compare delivered load between control and treatment.

    Same workload definition for both conditions is a precondition; this check
    guards against overloading one side (100 RPS vs 40 RPS is not comparable).
    """
    if not control or not treatment:
        return False, "one or both conditions produced no observations"
    c_rps = _median_rps(control)
    t_rps = _median_rps(treatment)
    if c_rps <= 0 or t_rps <= 0:
        return False, "one or both conditions delivered zero load"
    ratio = max(c_rps, t_rps) / min(c_rps, t_rps)
    if ratio > 1 + tolerance:
        return False, (
            f"delivered load differs materially: control {c_rps:.2f} RPS, "
            f"treatment {t_rps:.2f} RPS (ratio {ratio:.2f} > 1 + tolerance {tolerance})."
        )
    return True, f"control {c_rps:.2f} RPS vs treatment {t_rps:.2f} RPS (tolerance {tolerance})"


def build_comparison(
    experiment_id: str,
    expectations: list[EvidenceExpectation],
    control_observations: list[Observation],
    treatment_observations: list[Observation],
    workload_tolerance: float,
) -> Comparison:
    """Deterministically compare control vs treatment for every expectation."""
    metrics = [
        compare_metric(exp, control_observations, treatment_observations) for exp in expectations
    ]
    equivalent, reason = workload_equivalent(
        control_observations, treatment_observations, workload_tolerance
    )
    return Comparison(
        experiment_id=experiment_id,
        control_observation_ids=[o.id for o in control_observations],
        treatment_observation_ids=[o.id for o in treatment_observations],
        samples_per_condition=len(control_observations),
        workload_equivalent=equivalent,
        workload_equivalence_reason=reason,
        control_achieved_rps=[o.achieved_rps for o in control_observations],
        treatment_achieved_rps=[o.achieved_rps for o in treatment_observations],
        metrics=metrics,
    )


def observation_request_volume(measurement: Measurement) -> int:
    return measurement.request_metrics.total_requests if measurement.request_metrics else 0


def empty_condition(observations: list[Observation]) -> bool:
    return any(observation_request_volume(o.measurement) == 0 for o in observations)


def aggregate(values: list[float]) -> dict[str, float | None]:
    """Oracle-free summary of measured samples (no invented statistics)."""
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None, "median": None, "stddev": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }
