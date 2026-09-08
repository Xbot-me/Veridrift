from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from guardrail.evidence.store import EvidenceStore
from guardrail.models.base import Severity

console = Console()


@click.command(name="compare")
@click.argument("run_id_1")
@click.argument("run_id_2")
def compare_cmd(run_id_1: str, run_id_2: str) -> None:
    """Compare two verification runs."""
    store = EvidenceStore()
    run1 = store.load_run(run_id_1)
    run2 = store.load_run(run_id_2)

    if run1 is None:
        console.print(
            f"[bold red]Error:[/bold red] Run 1 '{run_id_1}' not found in evidence store."
        )
        raise click.Abort()

    if run2 is None:
        console.print(
            f"[bold red]Error:[/bold red] Run 2 '{run_id_2}' not found in evidence store."
        )
        raise click.Abort()

    console.print(
        f"[bold cyan]Comparing Verification Runs:[/bold cyan] {run_id_1[:8]} vs {run_id_2[:8]}\n"
    )

    table = Table(title="Run Comparison", border_style="blue")
    table.add_column("Dimension / Metric", style="bold")
    table.add_column(f"Run 1 ({run_id_1[:8]})")
    table.add_column(f"Run 2 ({run_id_2[:8]})")
    table.add_column("Delta / Assessment")

    # Target name
    table.add_row("Target", run1.target.name, run2.target.name, "—")

    # Final Verdict
    v1 = run1.final_verdict.value.upper()
    v2 = run2.final_verdict.value.upper()
    v1_col = "green" if v1 == "PASS" else "yellow" if v1 == "WARNING" else "red"
    v2_col = "green" if v2 == "PASS" else "yellow" if v2 == "WARNING" else "red"

    verdict_change = "Unchanged"
    if v1 != v2:
        if v2 == "PASS" or (v1 == "FAIL" and v2 == "WARNING"):
            verdict_change = "[green]Improved[/green]"
        else:
            verdict_change = "[red]Regressed[/red]"

    table.add_row(
        "Verdict", f"[{v1_col}]{v1}[/{v1_col}]", f"[{v2_col}]{v2}[/{v2_col}]", verdict_change
    )

    # Static findings comparison
    f1_total = len(run1.static_findings)
    f2_total = len(run2.static_findings)
    diff_total = f2_total - f1_total
    diff_col = "green" if diff_total < 0 else "red" if diff_total > 0 else "white"
    diff_str = f"[{diff_col}]{diff_total:+d}[/{diff_col}]" if diff_total != 0 else "0"
    table.add_row("Total Static Findings", str(f1_total), str(f2_total), diff_str)

    for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
        c1 = sum(1 for f in run1.static_findings if getattr(f, "severity", None) == sev)
        c2 = sum(1 for f in run2.static_findings if getattr(f, "severity", None) == sev)
        d = c2 - c1
        d_col = "green" if d < 0 else "red" if d > 0 else "white"
        d_str = f"[{d_col}]{d:+d}[/{d_col}]" if d != 0 else "0"
        table.add_row(f"{sev.value.capitalize()} Findings", str(c1), str(c2), d_str)

    console.print(table)
