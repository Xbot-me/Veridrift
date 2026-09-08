from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from guardrail.evidence.store import EvidenceStore
from guardrail.reporting.engine import ReportEngine

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()


@click.command(name="report")
@click.argument("run_id")
@click.option(
    "--format",
    "fmt",
    default="markdown",
    type=click.Choice(["markdown", "json", "html"], case_sensitive=False),
    help="Output format",
)
@click.option("--output", type=click.Path(), help="Save report to file")
def report_cmd(run_id: str, fmt: str, output: str | None) -> None:
    """Generate a report for a specific verification run."""
    store = EvidenceStore()
    run = store.load_run(run_id)

    if run is None:
        console.print(
            Panel(
                f"[bold red]Run not found:[/bold red] Could not find verification run with ID '{run_id}'.\n"
                f"Check stored runs in: {store.base_path}",
                title="Error",
                border_style="red",
            )
        )
        raise click.Abort()

    engine = ReportEngine()
    content = engine.generate(run, format=fmt.lower())

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"[green]Report saved to {output}[/green]")
    elif fmt.lower() == "json" or fmt.lower() == "html":
        console.print(content)
    else:
        md = Markdown(content)
        console.print(Panel(md, title=f"Verification Report: {run_id}", border_style="cyan"))
