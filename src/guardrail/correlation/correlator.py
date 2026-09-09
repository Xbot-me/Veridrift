from __future__ import annotations

from guardrail.models.base import HypothesisStatus, RuleCategory
from guardrail.models.measurement import Measurement
from guardrail.models.rule import Finding
from guardrail.models.verdict import CapacityResult
from guardrail.models.workload import AmplificationModel


class ControlledExperimentEvidenceRequired(RuntimeError):  # noqa: N818 - name matches the guardrail DSL term
    """Raised if a correlation path attempts to declare SUPPORTED/REFUTED.

    SUPPORTED/REFUTED are ONLY reachable through the Controlled Experiment
    Engine (Milestone 7). Aggregate/observational correlation is structurally
    forbidden from reaching them. This class is the architectural seam where
    that engine will plug in.
    """


def _controlled_outcome_only(finding: Finding) -> Finding:
    """Fail fast unless a controlled-experiment caller advances to SUPPORTED/REFUTED."""
    if finding.hypothesis_status in (HypothesisStatus.SUPPORTED, HypothesisStatus.REFUTED):
        raise ControlledExperimentEvidenceRequired(
            f"{finding.rule_id} reached {finding.hypothesis_status.value} from "
            "observational correlation. SUPPORTED/REFUTED require a controlled "
            "experiment with mechanism-specific intervention."
        )
    return finding


class HypothesisCorrelator:
    """Connects static findings to empirical runtime measurements.

    Evidence ladder (verification-integrity invariant):
        DETECTED -> EXERCISED -> OBSERVED -> SUPPORTED | REFUTED | INCONCLUSIVE

    This correlator NEVER stamps a finding as VERIFIED/SUPPORTED merely because
    a coarse aggregate metric (p95, error_rate, CPU) was poor. SUPPORTED/REFUTED
    are only reachable after a controlled experiment where mechanism-specific
    instrumentation isolates the causal mechanism. Until such instrumentation
    lands, the honest classifications here are:

      * CFG-*            DETECTED   -- static config claim, no runtime check exists.
      * DB-*             OBSERVED   -- only when DB telemetry was actually measured;
                                       otherwise INCONCLUSIVE.
      * NET-001          OBSERVED   -- only when connection timeouts/network errors
                                       were directly observed; otherwise INCONCLUSIVE.
      * AMP-* / CONC-*   INCONCLUSIVE -- workload ran the endpoint, but no downstream
                                       or thread-level signal was captured.
      * everything else  INCONCLUSIVE -- workload ran; no mechanism-specific metric
                                       exists, so causality cannot be claimed.

    No fabricated amplification models are produced: amplification evidence is
    removed until downstream instrumentation can measure it.
    """

    def correlate(
        self,
        findings: list[Finding],
        measurements: list[Measurement],
        capacity: CapacityResult | None = None,
        exercised_endpoints: list[str] | None = None,
    ) -> tuple[list[Finding], list[AmplificationModel]]:
        """Correlate static findings against empirical measurements and capacity limits.

        Args:
            findings: Static analysis findings.
            measurements: Empirical runtime measurements across load stages.
            capacity: Computed capacity and bottleneck results.
            exercised_endpoints: Endpoint paths actually exercised by the workload.

        Returns:
            Tuple of (updated findings with hypothesis status and evidence summary,
            amplification models -- always empty until instrumentation exists).
        """
        exercised = list(exercised_endpoints or [])
        if not measurements:
            return findings, []

        last_m = measurements[-1]
        req = last_m.request_metrics

        # A workload that produced no usable samples cannot move any hypothesis.
        if req is None or req.total_requests == 0:
            return findings, []

        updated_findings = []
        for f in findings:
            classified = self._classify(f, last_m, exercised)
            updated_findings.append(_controlled_outcome_only(classified))
        return updated_findings, []

    def _classify(
        self,
        finding: Finding,
        measurement: Measurement,
        exercised_endpoints: list[str],
    ) -> Finding:
        """Classify one finding on the evidence ladder using only mechanism-linked signal."""
        updated = finding.model_copy()
        updated.exercised_endpoints = list(
            dict.fromkeys([*updated.exercised_endpoints, *exercised_endpoints])
        )

        path = " ".join(exercised_endpoints) or "the exercised endpoint"

        # CFG findings: static config claims with no runtime check. Never auto-verified.
        if updated.category == RuleCategory.CONFIGURATION and updated.rule_id.startswith("CFG-"):
            updated.hypothesis_status = HypothesisStatus.DETECTED
            updated.evidence_summary = (
                "Configuration-state claim; no runtime instrumentation can currently "
                "confirm or refute it, and it is NOT claimed as verified."
            )
            return updated

        # DB findings: only creditable when DB telemetry was actually measured.
        if updated.category == RuleCategory.DATABASE:
            db = measurement.database_metrics
            if db is None:
                updated.hypothesis_status = HypothesisStatus.INCONCLUSIVE
                updated.evidence_summary = (
                    f"Workload ran against {path}, but no database telemetry was "
                    "instrumented; endpoint latency alone cannot attribute cause to queries."
                )
                return updated
            updated.hypothesis_status = HypothesisStatus.OBSERVED
            updated.evidence_summary = (
                f"Workload ran against {path}; DB telemetry observed "
                f"(query_rate={db.query_rate_per_second:.1f}/s, "
                f"avg_latency={db.avg_query_latency_ms:.1f}ms, "
                f"conns={db.active_connections}). Correlation only; "
                "causality is not isolated without a controlled experiment."
            )
            return updated

        # NET-001: directly observable signal is connection-level timeout/network failures.
        if updated.rule_id == "NET-001":
            req = measurement.request_metrics
            observed_failures = (req.timeouts if req else 0) + (req.network_errors if req else 0)
            if observed_failures > 0:
                updated.hypothesis_status = HypothesisStatus.OBSERVED
                updated.evidence_summary = (
                    f"Workload ran against {path}; "
                    f"{observed_failures} request(s) failed at the transport layer "
                    f"({req.timeouts} timeout(s), {req.network_errors} network error(s)). "
                    "Consistent with a missing-timeout risk, though causality is not isolated."
                )
                return updated
            updated.hypothesis_status = HypothesisStatus.INCONCLUSIVE
            updated.evidence_summary = (
                f"Workload ran against {path} but no timeout or network failure was "
                "observed; the missing-timeout impact was not demonstrated."
            )
            return updated

        # Everything else: workload ran, but no mechanism-specific signal exists.
        updated.hypothesis_status = HypothesisStatus.INCONCLUSIVE
        updated.evidence_summary = (
            f"Workload ran against {path}; no mechanism-specific metric is "
            "instrumented for this rule, so neither support nor refutation is claimed."
        )
        return updated
