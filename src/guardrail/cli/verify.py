from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from guardrail.analysis.engine import AnalysisEngine
from guardrail.capacity.engine import CapacityDiscoveryEngine
from guardrail.correlation.correlator import HypothesisCorrelator
from guardrail.discovery.engine import DiscoveryEngine
from guardrail.evidence.store import EvidenceStore
from guardrail.models.base import VerdictStatus
from guardrail.models.environment import Environment
from guardrail.models.policy import Policy
from guardrail.models.run import RunMetadata, VerificationRun
from guardrail.models.verdict import Verdict
from guardrail.policy.engine import PolicyEngine
from guardrail.runtime.adapter import RuntimeAdapter
from guardrail.runtime.local_process import LocalProcessRuntimeAdapter

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()


@click.command(name="verify")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--port", type=int, help="Port to run application on")
@click.option("--stages", type=str, default="10,25,50,100,200", help="Comma-separated RPS stages")
@click.option("--stage-duration", type=float, default=2.5, help="Seconds per load test stage")
@click.option(
    "--endpoint", type=str, help="Specific relative endpoint path to verify (e.g., /api/users)"
)
def verify_cmd(
    path: str,
    port: int | None,
    stages: str,
    stage_duration: float,
    endpoint: str | None,
) -> None:
    """Execute complete empirical runtime verification and capacity discovery."""
    abs_path = os.path.abspath(path)
    start_time = datetime.now(UTC)
    t0 = time.time()

    console.print(
        Panel(
            f"[bold cyan]Guardrail Production Runtime Verification Engine[/bold cyan]\n"
            f"Target: [bold]{abs_path}[/bold]",
            border_style="cyan",
        )
    )

    # Parse stages
    try:
        rps_stages = [float(s.strip()) for s in stages.split(",") if s.strip()]
    except ValueError:
        rps_stages = [10.0, 25.0, 50.0, 100.0, 200.0]

    # --- Step 1: Discovery ---
    console.print("[cyan][1/6] Discovering application architecture...[/cyan]")
    discovery_engine = DiscoveryEngine(abs_path)
    discovery_result = discovery_engine.discover()
    target = discovery_result.target
    console.print(
        f"[green]✓ Discovered:[/green] {target.name} "
        f"({', '.join(target.languages) or 'unknown'}), "
        f"frameworks: {', '.join(target.frameworks) or 'none'}, "
        f"endpoints: {len(target.endpoints)}"
    )

    # --- Step 2: Static Analysis ---
    console.print("\n[cyan][2/6] Running static risk analysis & hypothesis formation...[/cyan]")
    analysis_engine = AnalysisEngine(abs_path)
    analysis_result = analysis_engine.analyze()
    static_findings = analysis_result.findings
    console.print(
        f"[green]✓ Static hypotheses formed:[/green] {len(static_findings)} potential risk(s) identified"
    )

    # --- Step 3: Runtime Environment Setup ---
    console.print("\n[cyan][3/6] Starting application runtime environment...[/cyan]")
    runtime: RuntimeAdapter = LocalProcessRuntimeAdapter()

    try:
        instance = runtime.start(target, port=port)
    except Exception as e:
        console.print(
            Panel(
                f"[bold red]Failed to start application runtime:[/bold red] {e}", border_style="red"
            )
        )
        raise click.Abort() from e

    try:
        # --- Step 4: Health Check ---
        console.print(
            f"Waiting for instance at [bold]{instance.base_url}[/bold] to become healthy..."
        )
        is_healthy = runtime.health(instance, timeout_seconds=8.0)

        if not is_healthy:
            logs = runtime.get_logs(instance)
            console.print(
                Panel(
                    f"[bold red]Health check failed:[/bold red] Application failed to respond on {instance.base_url}.\n"
                    f"Process logs:\n{logs}",
                    border_style="red",
                )
            )
            raise click.Abort()

        console.print("[green]✓ Application is healthy and responsive.[/green]")

        # Select target endpoint to verify
        test_path = "/"
        if endpoint:
            test_path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        elif target.endpoints:
            # Pick first non-empty endpoint that starts with /
            for ep in target.endpoints:
                if ep.startswith("/"):
                    test_path = ep
                    break

        console.print(
            f"Verifying target workload endpoint: [bold magenta]{test_path}[/bold magenta]"
        )

        # --- Step 5: Capacity Discovery & Empirical Load Testing ---
        console.print("\n[cyan][4/6] Executing capacity discovery & traffic ramp...[/cyan]")

        load_table = Table(title="Empirical Load Stages", border_style="blue")
        load_table.add_column("Stage RPS", justify="right", style="bold")
        load_table.add_column("Actual RPS", justify="right")
        load_table.add_column("p50 (ms)", justify="right")
        load_table.add_column("p95 (ms)", justify="right")
        load_table.add_column("p99 (ms)", justify="right")
        load_table.add_column("Errors", justify="right")
        load_table.add_column("CPU", justify="right")
        load_table.add_column("Verdict", justify="center")

        def on_stage_done(summary: dict) -> None:
            status = summary["status"].upper()
            color = "green" if status == "PASS" else "yellow" if status == "WARNING" else "red"
            err_col = "red" if summary["error_rate"] > 0.01 else "green"
            load_table.add_row(
                f"{summary['rps']:.0f}",
                f"{summary['actual_rps']:.1f}",
                f"{summary['p50_ms']:.1f}",
                f"{summary['p95_ms']:.1f}",
                f"{summary['p99_ms']:.1f}",
                f"[{err_col}]{summary['error_rate'] * 100:.1f}%[/{err_col}]",
                f"{summary['cpu_percent']:.1f}%",
                f"[{color}]{status}[/{color}]",
            )

        policy = Policy.default()
        capacity_engine = CapacityDiscoveryEngine(runtime=runtime, policy=policy)
        capacity_result, measurements, runtime_verdicts = capacity_engine.discover_capacity(
            instance=instance,
            endpoint_path=test_path,
            initial_stages=rps_stages,
            stage_duration_seconds=stage_duration,
            refine_iterations=2,
            on_stage_complete=on_stage_done,
        )

        console.print(load_table)

        # --- Step 6: Static Hypothesis to Runtime Reality Correlation ---
        console.print(
            "\n[cyan][5/6] Correlating static hypotheses with empirical reality...[/cyan]"
        )
        correlator = HypothesisCorrelator()
        verified_findings, amplifications = correlator.correlate(
            findings=static_findings,
            measurements=measurements,
            capacity=capacity_result,
            exercised_endpoints=[test_path],
        )

        corr_table = Table(title="Hypothesis-to-Reality Verification", border_style="magenta")
        corr_table.add_column("Rule ID", style="magenta bold")
        corr_table.add_column("Detection")
        corr_table.add_column("Hypothesized Risk")
        corr_table.add_column("Hypothesis Status", style="bold")
        corr_table.add_column("Empirical Evidence")

        status_counts = {"SUPPORTED": 0, "OBSERVED": 0, "INCONCLUSIVE": 0, "DETECTED": 0, "REFUTED": 0}
        for f in verified_findings:
            status_val = f.hypothesis_status.value
            status_counts[status_val] = status_counts.get(status_val, 0) + 1
            status_color = {
                "SUPPORTED": "green",
                "OBSERVED": "green",
                "INCONCLUSIVE": "yellow",
                "DETECTED": "white",
                "REFUTED": "cyan",
            }.get(status_val, "yellow")

            corr_table.add_row(
                f.rule_id,
                f.confidence.value,
                f.hypothesized_risk or f.message,
                f"[{status_color}]{status_val}[/{status_color}]",
                f.evidence_summary or "No workload exercised this hypothesis",
            )

        console.print(corr_table)

        # --- Step 7: Final Verdict & Cryptographic Evidence Persistence ---
        console.print(
            "\n[cyan][6/6] Packaging cryptographic evidence and computing final verdict...[/cyan]"
        )
        policy_engine = PolicyEngine(policy)
        if not measurements:
            final_verdict = VerdictStatus.FAIL
            final_verdict_reason = "No measurements were produced; PASS cannot be granted on an unobserved workload."
        else:
            # Evidence sufficiency: any static hypothesis that did not reach
            # SUPPORTED/REFUTED leaves the run INCONCLUSIVE at the verification
            # level, even if the measured runtime thresholds all passed.
            uncovered = [f for f in verified_findings if f.hypothesis_status.value not in ("SUPPORTED", "REFUTED")]
            for f in uncovered:
                runtime_verdicts.append(
                    Verdict(
                        status=VerdictStatus.INCONCLUSIVE,
                        category="evidence_sufficiency",
                        reason=(
                            f"{f.rule_id} ({f.hypothesis_status.value}): {f.evidence_summary or 'no runtime evidence'}. "
                            "Predictive readiness is not established until this is a controlled outcome."
                        ),
                    )
                )
            final_verdict = policy_engine.compute_final_verdict(runtime_verdicts)
            if final_verdict == VerdictStatus.INCONCLUSIVE:
                final_verdict_reason = (
                    f"{len(uncovered)} hypothesis/hypotheses remain unverified (static or inconclusive); "
                    "runtime thresholds passed but production readiness is NOT established."
                )
            else:
                final_verdict_reason = ""

        duration = time.time() - t0
        run_record = VerificationRun(
            target=target,
            environment=Environment(name="local_process"),
            policy=policy,
            static_findings=verified_findings,
            runtime_findings=[],
            measurements=measurements,
            verdicts=runtime_verdicts,
            capacity=capacity_result,
            amplification=amplifications,
            final_verdict=final_verdict,
            metadata=RunMetadata(
                guardrail_version="0.2.0",
                start_time=start_time,
                end_time=datetime.now(UTC),
                duration_seconds=duration,
                machine_info={"os": os.name},
            ),
        )

        store = EvidenceStore()
        saved_dir = store.save_run(run_record)
        valid, _ = store.verify_manifest(run_record.id)

        # --- Summary Display ---
        status_val = final_verdict.value.upper()
        v_color = (
            "green"
            if status_val == "PASS"
            else "yellow"
            if status_val == "WARNING"
            else "magenta"
            if status_val == "INCONCLUSIVE"
            else "red"
        )

        console.print("\n")
        console.print(
            Panel(
                f"[bold {v_color}]FINAL VERDICT: {status_val}[/bold {v_color}]\n\n"
                f"{f'[red]{final_verdict_reason}[/red]\n' if final_verdict_reason else ''}"
                f"[bold]Empirical Capacity Boundary:[/bold]\n"
                f"  • Safe Operating Load:    [green]{capacity_result.safe_rps:.1f} RPS[/green]\n"
                f"  • Warning Boundary:       [yellow]{capacity_result.warning_rps or 'None'} RPS[/yellow]\n"
                f"  • Hard Failure Boundary:  [red]{capacity_result.failure_rps or 'None'} RPS[/red]\n"
                f"  • Primary Bottleneck:     [bold]{capacity_result.primary_bottleneck or 'None'}[/bold]\n\n"
                f"[bold]Hypothesis Validation:[/bold]\n"
                f"  • Static Hypotheses:      {len(verified_findings)} detected\n"
                f"  • SUPPORTED:              {status_counts['SUPPORTED']}\n"
                f"  • OBSERVED:               {status_counts['OBSERVED']}\n"
                f"  • INCONCLUSIVE:           {status_counts['INCONCLUSIVE']}\n"
                f"  • DETECTED (static only): {status_counts['DETECTED']}\n\n"
                f"[bold]Immutable Evidence Store:[/bold]\n"
                f"  • Run ID:                 [bold cyan]{run_record.id}[/bold cyan]\n"
                f"  • SHA-256 Manifest:       {'[green]VERIFIED VALID[/green]' if valid else '[red]INVALID[/red]'}\n"
                f"  • Artifact Directory:     {saved_dir}\n\n"
                f"Generate full report with: [cyan]guardrail report {run_record.id}[/cyan]",
                title="Guardrail Verification Summary",
                border_style=v_color,
            )
        )

    finally:
        runtime.stop(instance)
