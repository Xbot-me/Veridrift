from __future__ import annotations

import json
import os

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

try:
    from guardrail.analysis.engine import AnalysisEngine
except ImportError:
    AnalysisEngine = None

console = Console()


@click.command(name="analyze")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--severity", help="Filter by minimum severity (e.g., CRITICAL, HIGH)")
@click.option("--category", help="Filter by rule category")
@click.option("--output", type=click.Path(), help="Save findings as JSON")
def analyze_cmd(path: str, severity: str | None, category: str | None, output: str | None) -> None:
    """Run static analysis to identify potential issues."""
    console.print(f"[bold cyan]Analyzing project at:[/bold cyan] {path}")

    if AnalysisEngine is None:
        console.print("[bold red]Error:[/bold red] AnalysisEngine is not available.")
        raise click.Abort()

    engine = AnalysisEngine()
    try:
        result = engine.analyze(path)
        findings = getattr(result, "findings", [])

        if severity:
            findings = [
                f
                for f in findings
                if getattr(
                    getattr(f, "severity", None),
                    "value",
                    getattr(getattr(f, "severity", None), "name", ""),
                ).upper()
                == severity.upper()
            ]

        if category:
            findings = [
                f
                for f in findings
                if getattr(
                    getattr(f, "category", None),
                    "value",
                    getattr(getattr(f, "category", None), "name", ""),
                ).upper()
                == category.upper()
            ]

        if not findings:
            console.print(Panel("[green]No issues found![/green]", border_style="green"))
            return

        # Summary counts
        counts: dict[str, int] = {}
        for f in findings:
            sev_name = getattr(
                getattr(f, "severity", None),
                "value",
                getattr(getattr(f, "severity", None), "name", "UNKNOWN"),
            )
            counts[sev_name] = counts.get(sev_name, 0) + 1

        summary = ", ".join([f"{k}: {v}" for k, v in counts.items()])
        console.print(f"[bold]Findings Summary:[/bold] {summary}")

        table = Table(title="Static Analysis Findings", border_style="cyan")
        table.add_column("Rule ID", style="magenta")
        table.add_column("Severity")
        table.add_column("Confidence")
        table.add_column("File:Line")
        table.add_column("Message")

        has_critical = False
        out_data = []
        for f in findings:
            sev_name = getattr(
                getattr(f, "severity", None),
                "value",
                getattr(getattr(f, "severity", None), "name", "UNKNOWN"),
            )
            sev_color = (
                "red"
                if sev_name.upper() == "CRITICAL"
                else "yellow"
                if sev_name.upper() == "HIGH"
                else "cyan"
            )
            if sev_name.upper() == "CRITICAL":
                has_critical = True

            fp = getattr(f, "file_path", None) or ""
            if fp and os.path.isabs(fp):
                try:
                    fp = os.path.relpath(fp, path)
                except Exception:
                    pass
            line_no = getattr(f, "line_number", None)
            file_line = f"{fp}:{line_no}" if line_no else (fp or "Unknown")
            rule_id = getattr(f, "rule_id", None) or getattr(
                getattr(f, "rule", None), "id", "Unknown"
            )
            conf_name = getattr(
                getattr(f, "confidence", None),
                "value",
                getattr(getattr(f, "confidence", None), "name", "UNKNOWN"),
            )
            msg = getattr(f, "message", "")

            table.add_row(
                rule_id, f"[{sev_color}]{sev_name}[/{sev_color}]", conf_name, file_line, msg
            )
            out_data.append(
                {"rule_id": rule_id, "severity": sev_name, "message": msg, "file": file_line}
            )

        console.print(table)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2)
            console.print(f"[green]Saved output to {output}[/green]")

        if has_critical:
            raise click.Abort()

    except click.Abort:
        raise
    except Exception as e:
        console.print(
            Panel(f"[bold red]Analysis failed:[/bold red] {e}", title="Error", border_style="red")
        )
        raise click.Abort()
