from __future__ import annotations

from guardrail.models.base import Severity, VerdictStatus
from guardrail.models.run import VerificationRun


class MarkdownReporter:
    """Reporter that generates a structured Markdown report."""

    def render(self, run: VerificationRun) -> str:
        """
        Render the verification run to a Markdown string.

        Args:
            run: The completed verification run data.

        Returns:
            A Markdown formatted string.
        """
        md = []
        md.append(f"# Production Verification Report — {run.id[:8]}\n")

        # Executive Summary
        md.append("## Executive Summary")
        status_val = run.final_verdict.value.upper() if hasattr(run, "final_verdict") else "UNKNOWN"
        md.append(f"- **Final Verdict:** **{status_val}**")

        # Aggregate findings
        static_findings = getattr(run, "static_findings", [])
        runtime_findings = getattr(run, "runtime_findings", [])

        crit = sum(1 for f in static_findings if f.severity == Severity.CRITICAL)
        high = sum(1 for f in static_findings if f.severity == Severity.HIGH)
        med = sum(1 for f in static_findings if f.severity == Severity.MEDIUM)
        low = sum(1 for f in static_findings if f.severity == Severity.LOW)

        md.append(f"- **Static Findings:** {crit} critical, {high} high, {med} medium, {low} low")
        md.append(f"- **Runtime Findings:** {len(runtime_findings)}")

        # Time and target
        meta = getattr(run, "metadata", None)
        if meta:
            start_time = getattr(meta, "start_time", None)
            date_str = start_time.strftime("%Y-%m-%d %H:%M:%S UTC") if start_time else "N/A"
            duration = getattr(meta, "duration_seconds", 0) or 0
            md.append(f"- **Date:** {date_str} (Duration: {duration:.2f}s)")

        target = getattr(run, "target", None)
        if target:
            md.append(f"- **Target Application:** {target.name}\n")
            md.append("## Target Application")
            md.append(f"- **Name:** {target.name}")
            md.append(f"- **Path:** {target.path}")
            if getattr(target, "languages", None):
                md.append(f"- **Languages:** {', '.join(target.languages)}")
            if getattr(target, "frameworks", None):
                md.append(f"- **Frameworks:** {', '.join(target.frameworks)}")
            if getattr(target, "package_managers", None):
                md.append(f"- **Package Managers:** {', '.join(target.package_managers)}")
            if getattr(target, "dependencies", None):
                dep_names = [f"{d.name} ({d.type})" for d in target.dependencies]
                md.append(f"- **Dependencies:** {', '.join(dep_names)}\n")
            else:
                md.append("")

        # Static Findings
        md.append("## Static Analysis Findings")
        if not static_findings:
            md.append("*(No static findings)*\n")
        else:
            for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
                sev_findings = [f for f in static_findings if f.severity == severity]
                if sev_findings:
                    md.append(f"### {severity.value.title()} ({len(sev_findings)})")
                    for f in sev_findings:
                        loc = f" (`{f.file_path}:{f.line_number}`)" if f.file_path else ""
                        md.append(f"- **{f.rule_id}**: {f.message}{loc}")
                        if f.code_snippet:
                            md.append(f"  ```python\n  {f.code_snippet}\n  ```")
                        if f.recommendation:
                            md.append(f"  *Recommendation:* {f.recommendation}")
            md.append("")

        # Runtime Findings
        md.append("## Runtime Findings")
        if not runtime_findings:
            md.append("*(Runtime verification pending Docker execution environment)*\n")
        else:
            for f in runtime_findings:
                md.append(f"- **{f.rule_id}**: {f.message}")
            md.append("")

        # Verdicts
        verdicts = getattr(run, "verdicts", [])
        md.append("## Verdicts")
        if not verdicts:
            md.append("*(No policy threshold breaches recorded)*\n")
        else:
            md.append("| Category | Status | Observed | Threshold | Reason |")
            md.append("|---|---|---|---|---|")
            for v in verdicts:
                obs = f"{v.observed_value:.2f}" if v.observed_value is not None else "N/A"
                th = (
                    f"{v.threshold_breached.operator.value} {v.threshold_breached.value}"
                    if v.threshold_breached
                    else "N/A"
                )
                cat = getattr(v, "category", "general")
                status = getattr(v, "status", VerdictStatus.PASS).value.upper()
                md.append(f"| {cat} | {status} | {obs} | {th} | {v.reason} |")
            md.append("")

        # Capacity
        capacity = getattr(run, "capacity", None)
        md.append("## Capacity Results")
        if capacity:
            md.append(f"- **Safe RPS:** {capacity.safe_rps or 'N/A'}")
            md.append(f"- **Warning RPS:** {capacity.warning_rps or 'N/A'}")
            md.append(f"- **Failure RPS:** {capacity.failure_rps or 'N/A'}")
            md.append(f"- **Primary Bottleneck:** {capacity.primary_bottleneck or 'N/A'}\n")
        else:
            md.append("*(Capacity discovery pending runtime workload generation)*\n")

        # Recommendations
        md.append("## Recommendations")
        recommendations = []
        for f in static_findings:
            if f.recommendation and f.recommendation not in recommendations:
                recommendations.append(f.recommendation)
        if recommendations:
            for rec in recommendations[:5]:
                md.append(f"- {rec}")
        else:
            md.append("- Configure production limits before deployment.")
        md.append("")

        # Run Metadata
        md.append("## Run Metadata")
        md.append(f"- **Run ID:** `{run.id}`")
        if meta:
            md.append(f"- **Guardrail Version:** {getattr(meta, 'guardrail_version', '0.1.0')}")
            md.append(f"- **Machine Info:** {getattr(meta, 'machine_info', {})}")

        return "\n".join(md)
