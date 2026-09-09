"""Deterministic conclusion logic for controlled experiments.

A conclusion is a pure function of the measured evidence and configured
expectations. There is no statistical-significance invention and no LLM:
if the mechanism metric was not measured the only honest answer is
INCONCLUSIVE / INSUFFICIENT_DATA.
"""

from __future__ import annotations

from guardrail.experiment.comparison import empty_condition
from guardrail.experiment.models import (
    Comparison,
    Experiment,
    ExperimentConclusion,
    ExperimentValidity,
    Intervention,
    Observation,
    PreconditionCheck,
)
from guardrail.models.measurement import MeasurementValidity


def _invalid_measurements(observations: list[Observation]) -> list[str]:
    return [
        o.measurement.id
        for o in observations
        if o.measurement.validity == MeasurementValidity.INVALID
    ]


def assess_validity(
    experiment: Experiment,
    control_observations: list[Observation],
    treatment_observations: list[Observation],
    comparison: Comparison,
    intervention: Intervention | None,
) -> tuple[ExperimentValidity, list[str]]:
    """Determine experiment validity from structural evidence only.

    Requirements (all must hold for VALID):
      * preconditions satisfied (checked by caller via decide_conclusion),
      * intervention was actually applied,
      * every observation is structurally sound (no INVALID measurements),
      * no zero-request condition arm,
      * delivered workload is equivalent between control and treatment,
      * every required mechanism metric was actually measured.
    """
    if intervention is None or not intervention.applied:
        return (
            ExperimentValidity.INVALID,
            [intervention.failure_reason or "intervention was not applied"]
            if intervention
            else ["no intervention definition provided"],
        )

    bad = _invalid_measurements([*control_observations, *treatment_observations])
    if bad:
        return ExperimentValidity.INVALID, [f"malformed measurements: {', '.join(bad)}"]

    if empty_condition(control_observations) or empty_condition(treatment_observations):
        return ExperimentValidity.INSUFFICIENT_DATA, [
            "control or treatment arm delivered zero requests"
        ]

    if not comparison.workload_equivalent:
        return (
            ExperimentValidity.INSUFFICIENT_DATA,
            [comparison.workload_equivalence_reason],
        )

    required_mechanisms = [
        m
        for m in comparison.metrics
        if m.role == "mechanism"
        and m.metric in {e.metric for e in experiment.expectations if e.required}
    ]
    unmeasured = [m.metric for m in required_mechanisms if not m.measured]
    if unmeasured:
        return (
            ExperimentValidity.INSUFFICIENT_DATA,
            [f"required mechanism metric(s) not measured: {', '.join(sorted(unmeasured))}"],
        )

    return ExperimentValidity.VALID, []


def decide_conclusion(
    experiment: Experiment,
    preconditions: list[PreconditionCheck],
    control_observations: list[Observation],
    treatment_observations: list[Observation],
    comparison: Comparison,
    intervention: Intervention | None,
) -> ExperimentConclusion:
    """Produce the deterministic experiment conclusion.

    Decision tree (ordered):
      1. Any required precondition unmet       -> INCONCLUSIVE (INSUFFICIENT_DATA)
      2. Validity not VALID (see assess_validity) -> INCONCLUSIVE with validity reason
      3. Any expectation strongly contradicted -> REFUTED (mechanism measured but
         moved opposite the predicted direction)
      4. >=1 mechanism metric meets prediction -> SUPPORTED
      5. refute_on_flat_mechanism and no mechanism changed -> REFUTED
      6. otherwise                             -> INCONCLUSIVE
    """
    reasons: list[str] = []

    unmet = [p for p in preconditions if not p.satisfied]
    if unmet:
        details = "; ".join(f"{p.precondition_id}: {p.detail}" for p in unmet)
        return ExperimentConclusion(
            status="INCONCLUSIVE",
            validity=ExperimentValidity.INSUFFICIENT_DATA,
            reasons=[f"precondition(s) not satisfied: {details}"],
            evidence_observation_ids=[],
            metric_summary=comparison.metrics,
            experiment_id=experiment.id,
            hypothesis_id=experiment.hypothesis.id,
        )

    validity, validity_reasons = assess_validity(
        experiment,
        control_observations,
        treatment_observations,
        comparison,
        intervention,
    )
    if validity is not ExperimentValidity.VALID:
        return ExperimentConclusion(
            status="INCONCLUSIVE",
            validity=validity,
            reasons=validity_reasons,
            evidence_observation_ids=[
                *[o.id for o in control_observations],
                *[o.id for o in treatment_observations],
            ],
            metric_summary=comparison.metrics,
            experiment_id=experiment.id,
            hypothesis_id=experiment.hypothesis.id,
        )

    mechanism_met = [m for m in comparison.metrics if m.role == "mechanism" and m.meets_prediction]
    contradicted = [m for m in comparison.metrics if m.contradicts]
    mechanism_flat = [
        m
        for m in comparison.metrics
        if m.role == "mechanism" and m.measured and m.meets_prediction is False
    ]

    evidence_ids = [
        *[o.id for o in control_observations],
        *[o.id for o in treatment_observations],
    ]

    if contradicted:
        names = ", ".join(m.metric for m in contradicted)
        return ExperimentConclusion(
            status="REFUTED",
            validity=ExperimentValidity.VALID,
            reasons=[f"measured evidence contradicts predicted direction: {names}"],
            evidence_observation_ids=evidence_ids,
            metric_summary=comparison.metrics,
            experiment_id=experiment.id,
            hypothesis_id=experiment.hypothesis.id,
        )

    if mechanism_met:
        names = ", ".join(m.metric for m in mechanism_met)
        reasons.append(
            f"mechanism metric(s) moved as predicted: {names} "
            f"(all required mechanism metrics measured, workload equivalent, "
            f"intervention applied)"
        )
        return ExperimentConclusion(
            status="SUPPORTED",
            validity=ExperimentValidity.VALID,
            reasons=reasons,
            evidence_observation_ids=evidence_ids,
            metric_summary=comparison.metrics,
            experiment_id=experiment.id,
            hypothesis_id=experiment.hypothesis.id,
        )

    if experiment.refute_on_flat_mechanism and len(mechanism_flat) == sum(
        1 for e in experiment.expectations if e.role == "mechanism" and e.required
    ):
        return ExperimentConclusion(
            status="REFUTED",
            validity=ExperimentValidity.VALID,
            reasons=[
                "all required mechanism metrics were measured and none moved in the "
                "predicted direction despite the applied intervention"
            ],
            evidence_observation_ids=evidence_ids,
            metric_summary=comparison.metrics,
            experiment_id=experiment.id,
            hypothesis_id=experiment.hypothesis.id,
        )

    return ExperimentConclusion(
        status="INCONCLUSIVE",
        validity=ExperimentValidity.VALID,
        reasons=[
            "experiment was valid but no mechanism metric met the predicted effect "
            "threshold with strong enough magnitude (or expectations were underspecified)"
        ],
        evidence_observation_ids=evidence_ids,
        metric_summary=comparison.metrics,
        experiment_id=experiment.id,
        hypothesis_id=experiment.hypothesis.id,
    )
