from __future__ import annotations

import os

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

try:
    from guardrail.discovery.engine import DiscoveryEngine
except ImportError:
    DiscoveryEngine = None

console = Console()


@click.command(name="inspect")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", type=click.Path(), help="Save output as JSON to specified file")
def inspect_cmd(path: str, output: str | None) -> None:
    """Discover architecture, languages, and frameworks of the project."""
    abs_path = os.path.abspath(path)
    console.print(f"[bold cyan]Inspecting project at:[/bold cyan] {abs_path}")

    if DiscoveryEngine is None:
        console.print("[bold red]Error:[/bold red] DiscoveryEngine is not available.")
        return

    try:
        engine = DiscoveryEngine(abs_path)
        result = engine.discover()

        target = result.target
        console.print(
            Panel(
                f"[bold]Name:[/bold] {getattr(target, 'name', 'Unknown')}\n"
                f"[bold]Path:[/bold] {getattr(target, 'path', abs_path)}",
                title="Target Information",
                border_style="blue",
            )
        )

        # Languages
        langs = getattr(target, "languages", [])
        if langs:
            lang_table = Table(title="Languages Detected", border_style="cyan")
            lang_table.add_column("Language", style="bold")
            if isinstance(langs, dict):
                lang_table.add_column("Files", justify="right")
                for lang, count in langs.items():
                    lang_table.add_row(str(lang), str(count))
            else:
                for lang in langs:
                    lang_table.add_row(str(lang))
            console.print(lang_table)

        # Frameworks
        fws = getattr(target, "frameworks", [])
        if fws:
            fw_table = Table(title="Frameworks Detected", border_style="cyan")
            fw_table.add_column("Framework", style="bold")
            for fw in fws:
                fw_name = getattr(fw, "framework", getattr(fw, "name", str(fw)))
                fw_table.add_row(str(fw_name))
            console.print(fw_table)

        # Package Managers
        pms = getattr(target, "package_managers", [])
        if pms:
            pm_table = Table(title="Package Managers", border_style="cyan")
            pm_table.add_column("Manager", style="bold")
            for pm in pms:
                pm_name = getattr(pm, "manager", getattr(pm, "name", str(pm)))
                pm_table.add_row(str(pm_name))
            console.print(pm_table)

        # Dependencies / Databases
        deps = getattr(target, "dependencies", [])
        if deps:
            dep_table = Table(title="Dependencies & Databases", border_style="cyan")
            dep_table.add_column("Name", style="bold")
            dep_table.add_column("Type")
            for dep in deps:
                dep_table.add_row(getattr(dep, "name", str(dep)), getattr(dep, "type", "unknown"))
            console.print(dep_table)

        # Endpoints
        endpoints = getattr(target, "endpoints", [])
        if endpoints:
            ep_table = Table(title=f"Endpoints Discovered ({len(endpoints)})", border_style="cyan")
            ep_table.add_column("Endpoint", style="bold green")
            for ep in endpoints[:20]:
                ep_table.add_row(str(ep))
            if len(endpoints) > 20:
                ep_table.add_row(f"... and {len(endpoints) - 20} more")
            console.print(ep_table)

        # Application Graph
        if hasattr(result, "graph") and result.graph:
            mermaid_str = result.graph.to_mermaid()
            if mermaid_str:
                console.print(
                    Panel(
                        Syntax(mermaid_str, "mermaid", theme="monokai", line_numbers=False),
                        title="Discovered Application Graph (Mermaid)",
                        border_style="magenta",
                    )
                )

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(result.model_dump_json(indent=2))
            console.print(f"[green]Saved output to {output}[/green]")

    except Exception as e:
        console.print(
            Panel(f"[bold red]Inspection failed:[/bold red] {e}", title="Error", border_style="red")
        )
