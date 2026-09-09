"""Measurement providers for the Controlled Experiment Engine.

A provider is the ONLY source of experiment measurements. It decides how each
condition (control/treatment) is exercised and what gets recorded.

* ``RuntimeMeasurementProvider`` runs real traffic against a live application.
  DB telemetry is deliberately NOT fabricated: today no adapter instruments
  database internals, so mechanism metrics like db_queries_per_request are
  NOT_MEASURED and the honest conclusion is INCONCLUSIVE.
* ``StaticMeasurementProvider`` serves pre-recorded measurements (from a real
  instrumented environment, or from explicitly-labelled synthetic fixtures in
  tests). It never generates values itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from guardrail.experiment.models import (
    ConditionKind,
    ExperimentWorkload,
    Hypothesis,
    Intervention,
    Observation,
    PreconditionCheck,
)
from guardrail.models.measurement import Measurement
from guardrail.runtime.adapter import RuntimeAdapter, RuntimeInstance


class ExperimentProvider(Protocol):
    """Interface every controlled-experiment measurement source must implement."""

    def check_preconditions(self, hypothesis: Hypothesis) -> list[PreconditionCheck]: ...

    def apply_intervention(self, intervention: Intervention) -> Intervention: ...

    def run_condition(
        self,
        condition: ConditionKind,
        workload: ExperimentWorkload,
        repetition: int,
        run_id: str,
    ) -> Observation: ...


class StaticMeasurementProvider:
    """Serves pre-recorded measurements: one per condition, per repetition.

    Measurements are inputs, not outputs of the engine. The number of control
    measurements must match the number of treatment measurements (one per
    repetition). Synthetic fixtures are explicitly labelled by the caller.
    """

    def __init__(
        self,
        control_measurements: list[Measurement],
        treatment_measurements: list[Measurement],
        preconditions: list[PreconditionCheck] | None = None,
        intervention_result: Intervention | None = None,
    ) -> None:
        if len(control_measurements) != len(treatment_measurements):
            raise ValueError(
                "control and treatment must have the same number of measurements "
                "(one per repetition)"
            )
        self._control = list(control_measurements)
        self._treatment = list(treatment_measurements)
        self._preconditions = preconditions
        self._intervention = intervention_result
        self._run_id: str | None = None

    def check_preconditions(self, hypothesis: Hypothesis) -> list[PreconditionCheck]:
        if self._preconditions is not None:
            return self._preconditions
        return [
            PreconditionCheck(
                precondition_id="static", description="fixtures present", satisfied=True
            )
        ]

    def apply_intervention(self, intervention: Intervention) -> Intervention:
        if self._intervention is not None:
            applied = self._intervention
            applied.id = applied.id or intervention.id
            applied.description = applied.description or intervention.description
            return applied
        return Intervention(
            id=intervention.id,
            description=intervention.description,
            change_description=intervention.change_description,
            applied=True,
        )

    def run_condition(
        self,
        condition: ConditionKind,
        workload: ExperimentWorkload,
        repetition: int,
        run_id: str,
    ) -> Observation:
        measurements = self._control if condition is ConditionKind.CONTROL else self._treatment
        if repetition >= len(measurements):
            raise IndexError(f"no {condition.value} measurement for repetition {repetition}")
        measurement = measurements[repetition]
        achieved = (
            measurement.request_metrics.requests_per_second if measurement.request_metrics else 0.0
        )
        delivered = measurement.request_metrics.total_requests if measurement.request_metrics else 0
        return Observation(
            experiment_run_id=run_id,
            condition=condition,
            repetition=repetition,
            measurement=measurement,
            workload_definition_key=workload.key(),
            delivered_requests=delivered,
            achieved_rps=achieved,
            offered_rps=workload.target_rps,
        )


class RuntimeMeasurementProvider:
    """Runs real HTTP traffic against a live app for each experiment condition.

    Honesty contract: the runtime adapter has NO database instrumentation, so
    ``database_metrics`` is omitted. Mechanism metrics that depend on DB telemetry
    are therefore NOT_MEASURED and DB-002 experiments must conclude INCONCLUSIVE
    against a real app — the engine never invents query counts.

    The treatment arm additionally requires an intervention executor that does
    not exist yet; without one, the intervention is reported as not applied and
    the experiment is INVALID/INCONCLUSIVE rather than fabricating a "fix".
    """

    def __init__(
        self,
        runtime: RuntimeAdapter,
        instance: RuntimeInstance,
    ) -> None:
        self._runtime = runtime
        self._instance = instance

    def check_preconditions(self, hypothesis: Hypothesis) -> list[PreconditionCheck]:
        healthy = self._runtime.health(self._instance, timeout_seconds=8.0)
        checks: list[PreconditionCheck] = [
            PreconditionCheck(
                precondition_id="app_healthy",
                description="application is healthy and reachable",
                satisfied=healthy,
                detail="health check OK" if healthy else "health check failed",
            )
        ]
        for p in hypothesis.preconditions:
            if p.check == "db_telemetry_available":
                checks.append(
                    PreconditionCheck(
                        precondition_id=p.id,
                        description=p.description,
                        satisfied=False,
                        detail=(
                            "no database telemetry instrumentation exists in the runtime "
                            "adapter, so db_queries_per_request cannot be measured"
                        ),
                    )
                )
            else:
                checks.append(
                    PreconditionCheck(
                        precondition_id=p.id,
                        description=p.description,
                        satisfied=healthy,
                        detail="not verifiable without additional instrumentation",
                    )
                )
        return checks

    def apply_intervention(self, intervention: Intervention) -> Intervention:
        return Intervention(
            id=intervention.id,
            description=intervention.description,
            change_description=intervention.change_description,
            applied=False,
            failure_reason=(
                "no code-mutation / intervention executor is implemented yet; "
                "the treatment variant cannot be produced and executed"
            ),
        )

    def run_condition(
        self,
        condition: ConditionKind,
        workload: ExperimentWorkload,
        repetition: int,
        run_id: str,
    ) -> Observation:
        from guardrail.workload.generator import HttpWorkloadGenerator

        generator = HttpWorkloadGenerator()
        url = f"{self._instance.base_url}{workload.endpoint}"
        request_metrics = generator.generate(
            target_url=url,
            target_rps=workload.target_rps,
            duration_seconds=workload.duration_seconds,
            concurrency=workload.concurrency,
            method=workload.method,
            headers=workload.headers,
            payload=workload.payload,
        )
        resource_metrics = self._runtime.get_metrics(self._instance)
        measurement = Measurement(
            run_id=run_id,
            timestamp=datetime.now(UTC),
            workload_rps=workload.target_rps,
            request_metrics=request_metrics,
            resource_metrics=resource_metrics,
            database_metrics=None,
        )
        return Observation(
            experiment_run_id=run_id,
            condition=condition,
            repetition=repetition,
            measurement=measurement,
            workload_definition_key=workload.key(),
            delivered_requests=request_metrics.total_requests,
            achieved_rps=request_metrics.requests_per_second,
            offered_rps=workload.target_rps,
        )
