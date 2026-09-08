from __future__ import annotations

import os

import click
from rich.console import Console
from rich.panel import Panel

console = Console()

GUARDRAIL_YAML = """# Guardrail Production Verification Configuration
version: '1.0'

target:
  name: my-application
  path: .

production:
  expected_concurrent_users: 100
  peak_requests_per_second: 50
  sustained_requests_per_second: 20

database:
  expected_rows:
    users: 10000
    orders: 50000

policy:
  max_p95_latency_ms: 500
  max_p99_latency_ms: 1000
  max_error_rate: 0.01
  max_cpu_percent: 80
  max_memory_percent: 80
  max_db_connection_utilization: 0.80

environment:
  max_duration_seconds: 600
  network_isolation: true
  cleanup_on_exit: true
"""

POLICY_YAML = """# Default Policy Configuration
rules:
  - id: P001
    name: No plaintext passwords
    severity: CRITICAL
"""


@click.command(name="init")
@click.option("--template", default="default", help="Template to use (default, strict, relaxed)")
def init_cmd(template: str) -> None:
    """Initialize a new Guardrail verification configuration in the current directory."""
    cwd = os.getcwd()
    guardrail_dir = os.path.join(cwd, ".guardrail")
    guardrail_yaml_path = os.path.join(cwd, "guardrail.yaml")
    policy_yaml_path = os.path.join(cwd, "policy.yaml")

    try:
        os.makedirs(guardrail_dir, exist_ok=True)

        with open(guardrail_yaml_path, "w", encoding="utf-8") as f:
            f.write(GUARDRAIL_YAML)

        with open(policy_yaml_path, "w", encoding="utf-8") as f:
            f.write(POLICY_YAML)

        console.print(
            Panel.fit(
                "[bold green]Successfully initialized Guardrail![/bold green]\n"
                "Created:\n"
                f"- [cyan]{guardrail_yaml_path}[/cyan]\n"
                f"- [cyan]{policy_yaml_path}[/cyan]\n"
                f"- [cyan]{guardrail_dir}/[/cyan]\n\n"
                "You can now customize these files for your workload and run:\n"
                "[bold yellow]guardrail run[/bold yellow]",
                title="Guardrail Init",
                border_style="green",
            )
        )
    except Exception as e:
        console.print(
            Panel.fit(
                f"[bold red]Failed to initialize Guardrail:[/bold red] {e}",
                title="Error",
                border_style="red",
            )
        )
