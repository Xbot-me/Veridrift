"""Controlled Experiment Engine orchestrator.

The engine is the ONLY code path that may advance a finding to
SUPPORTED/REFUTED. It knows nothing about app internals: it asks a provider
to enforce preconditions, apply the intervention, and produce measurements for
each condition arm, then deterministically compares and concludes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from guardrail.experiment.comparison import build_comparison
from guardrail.experiment.conclusion import decide_conclusion
from guardrail.experiment.models import (
    Comparison,
    ConditionKind,
    Experiment,
    ExperimentConclusion,
    ExperimentRun,
    ExperimentValidity,
    ExperimentWorkload,
    Intervention,
    Observation,
)
from guardrail.experiment.providers import ExperimentProvider
from guardrail.models.base import generate_id


def apply_experiment_conclusion(experiment_run: ExperimentRun) -> str:
    """Surface the conclusion status of a completed experiment.

    Raises if the experiment is not VALID: SUPPORTED/REFUTED conclusions are
    only reproducible from VALID experiments with measured mechanism evidence.
    """
    if experiment_run.conclusion is None:
        raise ValueError("experiment run has no conclusion")
    if experiment_run.conclusion.validity is not ExperimentValidity.VALID:
        raise ValueError(
            f"experiment {experiment_run.experiment.id} validity is "
            f"{experiment_run.conclusion.validity.value}; cannot derive a causal outcome"
        )
    return experiment_run.conclusion.status


def transition_finding(finding, experiment_run, new_status: str | None):
    """The ONLY sanctioned way to move a finding to SUPPORTED/REFUTED.

    The finding must belong to the experiment's hypothesis (matched by rule id),
    the experiment must be VALID, and the experiment conclusion must actually be
    SUPPORTED or REFUTED. Any attempt to transition from an INCONCLUSIVE or
    non-VALID experiment raises instead of silently downgrading evidence.
    """
    from guardrail.models.base import HypothesisStatus

    conclusion = experiment_run.conclusion
    if conclusion is None:
        raise ValueError("experiment run has no conclusion")
    if conclusion.validity is not ExperimentValidity.VALID:
        raise ValueError(
            f"cannot transition finding {finding.rule_id}: experiment "
            f"{experiment_run.experiment.id} is {conclusion.validity.value}"
        )
    if conclusion.status not in ("SUPPORTED", "REFUTED"):
        right = conclusion.status
        raise ValueError(
            f"cannot transition finding {finding.rule_id} to SUPPORTED/REFUTED from an "
            f"experiment that concluded {right}"
        )
    expected_finding = experiment_run.experiment.hypothesis.finding_id
    if finding.rule_id != expected_finding:
        raise ValueError(
            f"finding {finding.rule_id} does not belong to hypothesis "
            f"{experiment_run.experiment.hypothesis.id} (expected finding {expected_finding})"
        )

    target = new_status or conclusion.status
    target_enum = HypothesisStatus(target)
    updated = finding.model_copy(
        update={
            "hypothesis_status": target_enum,
            "controlled_experiment_id": experiment_run.id,
            "evidence_summary": (
                f"Controlled experiment {experiment_run.id} ({experiment_run.experiment.id}) "
                f"concluded {target} from measurements {experiment_run.comparison.control_observation_ids + experiment_run.comparison.treatment_observation_ids if experiment_run.comparison else []}."
            ),
        },
        deep=True,
    )
    return updated


class ControlledExperimentEngine:
    """Runs a controlled experiment and records a fully reproducible ExperimentRun."""

    def __init__(self, store=None) -> None:
        self._store = store

    @property
    def store(self):
        return self._store

    def run_experiment(
        self,
        experiment: Experiment,
        provider: ExperimentProvider,
        workload: ExperimentWorkload | None = None,
        repetitions: int | None = None,
    ) -> ExperimentRun:
        run_id = f"{experiment.id}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{generate_id()[:6]}"
        workload = workload or experiment.default_workload
        if workload is None:
            raise ValueError(f"experiment {experiment.id} requires a workload definition")
        reps = repetitions or experiment.repetitions or 1

        preconditions = provider.check_preconditions(experiment.hypothesis)

        unmet = [p for p in preconditions if not p.satisfied]
        if unmet:
            conclusion = ExperimentConclusion(
                status="INCONCLUSIVE",
                validity=ExperimentValidity.INSUFFICIENT_DATA,
                reasons=[
                    f"precondition(s) not satisfied: "
                    + "; ".join(f"{p.precondition_id} ({p.detail})" for p in unmet)
                ],
                evidence_observation_ids=[],
                metric_summary=[],
            )
            return self._finalize(
                run_id,
                experiment,
                workload,
                preconditions,
                intervention=None,
                control=[],
                treatment=[],
                comparison=None,
                conclusion=conclusion,
            )

        intervention = self._apply_intervention(experiment, provider)
        if intervention is None:
            conclusion = ExperimentConclusion(
                status="INCONCLUSIVE",
                validity=ExperimentValidity.INVALID,
                reasons=["experiment defines no intervention; a controlled experiment "
                         "requires an explicit control->treatment change"],
                evidence_observation_ids=[],
                metric_summary=[],
            )
            return self._finalize(
                run_id,
                experiment,
                workload,
                preconditions,
                intervention=None,
                control=[],
                treatment=[],
                comparison=None,
                conclusion=conclusion,
            )
        if not intervention.applied:
            conclusion = ExperimentConclusion(
                status="INCONCLUSIVE",
                validity=ExperimentValidity.INVALID,
                reasons=[intervention.failure_reason or "intervention was not applied"],
                evidence_observation_ids=[],
                metric_summary=[],
            )
            return self._finalize(
                run_id,
                experiment,
                workload,
                preconditions,
                intervention=intervention,
                control=[],
                treatment=[],
                comparison=None,
                conclusion=conclusion,
            )

        control: list[Observation] = []
        treatment: list[Observation] = []
        for i in range(reps):
            control.append(provider.run_condition(ConditionKind.CONTROL, workload, i, run_id))
            treatment.append(provider.run_condition(ConditionKind.TREATMENT, workload, i, run_id))

        comparison = build_comparison(
            experiment_id=experiment.id,
            expectations=experiment.expectations,
            control_observations=control,
            treatment_observations=treatment,
            workload_tolerance=experiment.workload_tolerance,
        )
        conclusion = decide_conclusion(
            experiment,
            preconditions,
            control,
            treatment,
            comparison,
            intervention,
        )
        return self._finalize(
            run_id,
            experiment,
            workload,
            preconditions,
            intervention,
            control,
            treatment,
            comparison,
            conclusion,
        )

    def _apply_intervention(self, experiment: Experiment, provider: ExperimentProvider) -> Intervention | None:
        if not experiment.interventions:
            return None
        return provider.apply_intervention(experiment.interventions[0])

    def _finalize(
        self,
        run_id: str,
        experiment: Experiment,
        workload: ExperimentWorkload,
        preconditions,
        intervention: Intervention | None,
        control: list[Observation],
        treatment: list[Observation],
        comparison: Comparison | None,
        conclusion: ExperimentConclusion,
    ) -> ExperimentRun:
        run = ExperimentRun(
            id=run_id,
            experiment=experiment,
            workload=workload,
            preconditions=preconditions,
            intervention=intervention,
            control_observations=control,
            treatment_observations=treatment,
            comparison=comparison,
            conclusion=conclusion,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        if self._store is not None:
            self._store.save_experiment(run)
        return run