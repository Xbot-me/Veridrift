from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TextColumn
from rich.table import Table

from guardrail.analysis.engine import AnalysisEngine
from guardrail.discovery.engine import DiscoveryEngine
from guardrail.evidence.store import EvidenceStore
from guardrail.models.base import Severity, VerdictStatus
from guardrail.models.environment import Environment
from guardrail.models.policy import Policy
from guardrail.models.run import RunMetadata, VerificationRun
from guardrail.models.verdict import Verdict
from guardrail.policy.engine import PolicyEngine

console = Console()


@click.command(name="run")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--policy-file", type=click.Path(exists=True), help="Path to custom policy YAML")
def run_cmd(path: str, policy_file: str | None) -> None:
    """Orchestrate a full verification run."""
    abs_path = os.path.abspath(path)
    start_time = datetime.now(UTC)
    t0 = time.time()

    console.print(
        Panel(
            f"[bold cyan]Guardrail Production Verification Run[/bold cyan]\nTarget: {abs_path}",
            border_style="cyan",
        )
    )

    target = None
    findings = []
    verdicts = []

    with Progress(
        TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        # Step 1: Discovery
        task1 = progress.add_task("[cyan]Step 1: Discovering architecture...", total=None)
        discovery_engine = DiscoveryEngine(abs_path)
        discovery_result = discovery_engine.discover()
        target = discovery_result.target
        progress.update(task1, description="[green]Step 1: Architecture discovery complete[/green]")

        # Step 2: Static Analysis
        task2 = progress.add_task("[cyan]Step 2: Running static analysis...", total=None)
        analysis_engine = AnalysisEngine(abs_path)
        analysis_result = analysis_engine.analyze()
        findings = analysis_result.findings
        progress.update(
            task2,
            description=f"[green]Step 2: Static analysis complete ({len(findings)} findings)[/green]",
        )

        # Step 3, 4, 5
        console.print(
            "\n[yellow]NOTE: Runtime verification (Steps 3-5: container orchestration, load generation) requires Docker runtime. Using static + policy evaluation.[/yellow]\n"
        )

        # Step 6: Policy Evaluation
        task6 = progress.add_task("[cyan]Step 6: Evaluating policies...", total=None)
        policy = Policy.default()
        policy_engine = PolicyEngine(policy)

        # Count findings by severity
        severity_counts: dict[Severity, int] = {}
        for f in findings:
            sev = getattr(f, "severity", Severity.MEDIUM)
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        static_verdicts = policy_engine.evaluate_static_findings_severity(severity_counts)
        verdicts.extend(static_verdicts)
        # This path performs no runtime verification; without empirical evidence the
        # run cannot be PASS even if no static severity triggered a verdict. Express
        # that explicitly so the run-level status reads INCONCLUSIVE, not PASS.
        verdicts.append(
            Verdict(
                status=VerdictStatus.INCONCLUSIVE,
                category="evidence_sufficiency",
                reason="Static-only run; no runtime measurements were collected.",
            )
        )
        final_verdict = policy_engine.compute_final_verdict(verdicts)
        progress.update(task6, description="[green]Step 6: Policy evaluation complete[/green]")

        # Step 7: Save results to evidence store
        task7 = progress.add_task("[cyan]Step 7: Saving results to evidence store...", total=None)
        store = EvidenceStore()
        duration = time.time() - t0

        run_record = VerificationRun(
            target=target,
            environment=Environment(name="default"),
            policy=policy,
            static_findings=findings,
            runtime_findings=[],
            measurements=[],
            verdicts=verdicts,
            final_verdict=final_verdict,
            metadata=RunMetadata(
                guardrail_version="0.1.0",
                start_time=start_time,
                end_time=datetime.now(UTC),
                duration_seconds=duration,
                machine_info={"os": os.name},
            ),
        )
        saved_dir = store.save_run(run_record)
        progress.update(
            task7,
            description=f"[green]Step 7: Saved to evidence store ({run_record.id[:8]})[/green]",
        )

    # Print Summary Table
    console.print("\n[bold]Verification Findings Summary:[/bold]")
    summary_table = Table(border_style="cyan")
    summary_table.add_column("Severity", style="bold")
    summary_table.add_column("Count", justify="right")
    for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
        cnt = severity_counts.get(sev, 0)
        color = "red" if sev == Severity.CRITICAL else "yellow" if sev == Severity.HIGH else "cyan"
        summary_table.add_row(f"[{color}]{sev.value}[/{color}]", str(cnt))
    console.print(summary_table)

    # Verdict Panel
    status_str = final_verdict.value.upper()
    v_color = (
        "green"
        if status_str == "PASS"
        else "yellow"
        if status_str == "WARNING"
        else "magenta"
        if status_str == "INCONCLUSIVE"
        else "red"
    )
    console.print(
        Panel(
            f"[bold {v_color}]VERDICT: {status_str}[/bold {v_color}]\n\n"
            f"Run ID: [bold]{run_record.id}[/bold]\n"
            f"Evidence stored at: {saved_dir}\n\n"
            f"View report with: [cyan]guardrail report {run_record.id}[/cyan]",
            title="Verification Verdict",
            border_style=v_color,
        )
    )
