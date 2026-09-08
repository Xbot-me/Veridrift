from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Severity(str, Enum):
    """Severity levels for findings and thresholds."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class Confidence(str, Enum):
    """Confidence levels for verdicts and findings."""

    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"


class VerdictStatus(str, Enum):
    """Status outcomes for a verification run or rule.

    PASS/WARNING/FAIL describe the runtime (what was measured). INCONCLUSIVE is
    a first-class run-level outcome: the workload did not violate thresholds, but
    evidence sufficiency was not established (e.g. known instrumentation gaps), so
    the run must not be read as "the application is production-clear".
    """

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvidenceType(str, Enum):
    """Types of evidence supporting a finding or verdict."""

    STATIC = "STATIC"
    EMPIRICAL = "EMPIRICAL"
    ESTIMATED = "ESTIMATED"


class RuleCategory(str, Enum):
    """Categories of guardrail rules."""

    DATABASE = "DATABASE"
    CONCURRENCY = "CONCURRENCY"
    NETWORK = "NETWORK"
    RESOURCE = "RESOURCE"
    RELIABILITY = "RELIABILITY"
    AMPLIFICATION = "AMPLIFICATION"
    CONFIGURATION = "CONFIGURATION"


class ThresholdOperator(str, Enum):
    """Operators for policy thresholds."""

    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    EQ = "EQ"


class TrafficPattern(str, Enum):
    """Traffic generation patterns."""

    CONSTANT = "CONSTANT"
    RAMP = "RAMP"
    STEP = "STEP"
    BURST = "BURST"
    SPIKE = "SPIKE"
    WAVE = "WAVE"
    RANDOM = "RANDOM"
    REPLAY = "REPLAY"


class HypothesisStatus(str, Enum):
    """Lifecycle status of a verification hypothesis.

    Evidence ladder (MiS 6 / verification integrity):
        DETECTED -> EXERCISED -> OBSERVED -> SUPPORTED | REFUTED

    * DETECTED   -- static finding raised; no runtime workload has run against it.
    * EXERCISED  -- a valid workload ran through the endpoint the finding targets,
                    but no mechanism-specific signal was measured yet.
    * OBSERVED   -- a mechanism-specific signal consistent with the hypothesis was
                    directly observed under workload (e.g. NET-001 with measured
                    connection timeouts). Correlation only, not controlled causation.
    * SUPPORTED / REFUTED -- only reachable after a controlled experiment with
                    mechanism-specific instrumentation isolates the mechanism.
    * INCONCLUSIVE -- runtime assessments were attempted but evidence is ambiguous
                    or insufficient to choose a direction.
    Legacy members (HYPOTHESIZED, TESTABLE, NOT_EXERCISED) are preserved for
    backward compatibility with existing serialized runs.
    """

    DETECTED = "DETECTED"
    HYPOTHESIZED = "HYPOTHESIZED"
    TESTABLE = "TESTABLE"
    NOT_EXERCISED = "NOT_EXERCISED"
    EXERCISED = "EXERCISED"
    OBSERVED = "OBSERVED"
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ValidityLevel(str, Enum):
    """Confidence level in the validity of an empirical experiment."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class GuardrailModel(BaseModel):
    """Base Pydantic model for all Guardrail domain models."""

    model_config = ConfigDict(
        use_enum_values=False, populate_by_name=True, ser_json_timedelta="float"
    )


def generate_id() -> str:
    """Generate a unique ID."""
    return uuid.uuid4().hex
