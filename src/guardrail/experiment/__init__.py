"""Controlled Experiment Engine (Milestone 7).

SUPPORTED/REFUTED hypothesis outcomes are ONLY reachable through this package.
Observational correlation (guardrail.correlation) is structurally forbidden from
producing them; the ControlledExperimentEvidenceRequired guard in the correlator
is the architectural seam this engine plugs into.
"""

from __future__ import annotations

from guardrail.experiment.conclusion import (
    ExperimentConclusion,
    ExperimentValidity,
    decide_conclusion,
)
from guardrail.experiment.engine import (
    ControlledExperimentEngine,
    apply_experiment_conclusion,
    transition_finding,
)
from guardrail.experiment.models import (
    Comparison,
    ConditionKind,
    Experiment,
    ExperimentRun,
    ExperimentWorkload,
    Hypothesis,
    Intervention,
    Observation,
    Precondition,
)
from guardrail.experiment.providers import (
    ExperimentProvider,
    RuntimeMeasurementProvider,
    StaticMeasurementProvider,
)
from guardrail.experiment.registry import db002_experiment

__all__ = [
    "Comparison",
    "ConditionKind",
    "ControlledExperimentEngine",
    "Experiment",
    "ExperimentConclusion",
    "ExperimentProvider",
    "ExperimentRun",
    "ExperimentValidity",
    "ExperimentWorkload",
    "Hypothesis",
    "Intervention",
    "Observation",
    "Precondition",
    "RuntimeMeasurementProvider",
    "StaticMeasurementProvider",
    "apply_experiment_conclusion",
    "db002_experiment",
    "decide_conclusion",
    "transition_finding",
]