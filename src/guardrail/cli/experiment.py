from __future__ import annotations

import json
import os
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from guardrail.evidence.store import EvidenceStore
from guardrail.experiment.engine import ControlledExperimentEngine
from guardrail.experiment.models import ExperimentWorkload
from guardrail.experiment.providers import RuntimeMeasurementProvider, StaticMeasurementProvider
from guardrail.experiment.registry import registered_experiments
from guardrail.models.measurement import Measurement
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


def _status_color(status: str) -> str:
    if status == "SUPPORTED":
        return "green"
    if status == "REFUTED":
        return "cyan"
    return "yellow"


def _load_measurements(path: str) -> list[Measurement]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return [Measurement.model_validate(item) for item in data]


@click.group(name="experiment")
def experiment_cmd() -> None:
    """Controlled Experiment Engine (evidence-based hypothesis outcomes)."""


@experiment_cmd.command("list")
def experiment_list() -> None:
    """List registered controlled experiments."""
    table = Table(title="Registered Controlled Experiments", border_style="magenta")
    table.add_column("Experiment ID", style="bold")
    table.add_column("Hypothesis", style="magenta")
    table.add_column("Finding")
    table.add_column("Mechanism Metric(s)")
    table.add_column("Endpoints")
    for exp in registered_experiments().values():
        mechanisms = ", ".join(
            e.metric for e in exp.expectations if e.role == "mechanism"
        )
        table.add_row(
            exp.id,
            exp.hypothesis.id,
            exp.hypothesis.finding_id,
            mechanisms,
            exp.hypothesis.target_endpoint,
        )
    console.print(table)


@experiment_cmd.command("run")
@click.argument("experiment_id")
@click.option(
    "--control-measurements",
    type=click.Path(exists=True),
    help="JSON file(s) of recorded CONTROL Measurements (real telemetry).",
)
@click.option(
    "--treatment-measurements",
    type=click.Path(exists=True),
    help="JSON file(s) of recorded TREATMENT Measurements (real telemetry).",
)
@click.option("--path", type=click.Path(exists=True), help="Target app path for a live runtime run.")
@click.option("--port", type=int, help="Port to run the app on (live runtime run).")
@click.option("--endpoint", type=str, help="Override the experiment target endpoint.")
@click.option("--rps", type=float, default=None, help="Override workload target RPS.")
@click.option("--duration", type=float, default=None, help="Override workload duration (s).")
@click.option("--repetitions", type=int, default=None, help="Override repetition count.")
def experiment_run(
    experiment_id: str,
    control_measurements: str | None,
    treatment_measurements: str | None,
    path: str | None,
    port: int | None,
    endpoint: str | None,
    rps: float | None,
    duration: float | None,
    repetitions: int | None,
) -> None:
    """Run a controlled experiment and persist all evidence artifacts."""
    registry = registered_experiments()
    if experiment_id not in registry:
        console.print(
            Panel(
                f"[bold red]Unknown experiment:[/bold red] {experiment_id}\n"
                f"Available: {', '.join(sorted(registry))}",
                title="Error",
                border_style="red",
            )
        )
        raise click.Abort()

    experiment = registry[experiment_id]
    workload = experiment.default_workload
    if workload is None:
        workload = ExperimentWorkload(endpoint=endpoint or "/", target_rps=rps or 30.0, duration_seconds=duration or 5.0)
    if endpoint:
        workload = workload.model_copy(update={"endpoint": endpoint if endpoint.startswith("/") else f"/{endpoint}"})
    if rps:
        workload = workload.model_copy(update={"target_rps": rps})
    if duration:
        workload = workload.model_copy(update={"duration_seconds": duration})
    if repetitions:
        experiment = experiment.model_copy(update={"repetitions": repetitions})

    store = EvidenceStore()
    engine = ControlledExperimentEngine(store=store)

    if control_measurements and treatment_measurements:
        provider = StaticMeasurementProvider(
            control_measurements=_load_measurements(control_measurements),
            treatment_measurements=_load_measurements(treatment_measurements),
        )
        source_note = "recorded telemetry"
    elif path:
        runtime = LocalProcessRuntimeAdapter()
        console.print(f"Starting app at [bold]{os.path.abspath(path)}[/bold]...")
        target = _target_from_path(path)
        instance = runtime.start(target, port=port)
        provider = RuntimeMeasurementProvider(runtime=runtime, instance=instance)
        source_note = "live runtime"
    else:
        console.print(
            Panel(
                "[yellow]No measurement source provided.[/yellow]\n"
                "Provide --control-measurements/--treatment-measurements (recorded telemetry)\n"
                "or --path (live runtime run).",
                title="Missing Input",
                border_style="yellow",
            )
        )
        raise click.Abort()

    run = engine.run_experiment(experiment, provider, workload=workload)
    conclusion = run.conclusion

    if path:
        runtime.stop(instance)

    valid, _ = store.verify_experiment_manifest(run.id)

    console.print("\n")
    console.print(
        Panel(
            f"[bold {_status_color(conclusion.status)}]EXPERIMENT CONCLUSION: {conclusion.status}[/bold {_status_color(conclusion.status)}]\n"
            f"  • Experiment:          [bold cyan]{run.experiment.id}[/bold cyan]\n"
            f"  • Hypothesis:          {run.experiment.hypothesis.statement}\n"
            f"  • Validity:            [bold]{conclusion.validity.value}[/bold]\n"
            f"  • Measurement source:  {source_note}\n"
            f"  • Samples/condition:   {len(run.control_observations)}\n\n"
            f"[bold]Reasons:[/bold]\n"
            + "\n".join(f"    - {r}" for r in conclusion.reasons)
            + f"\n\n[bold]Immutable Evidence:[/bold]\n"
            f"  • Run ID:              [bold cyan]{run.id}[/bold cyan]\n"
            f"  • SHA-256 Manifest:    {'[green]VERIFIED VALID[/green]' if valid else '[red]INVALID[/red]'}\n\n"
            f"Full report: [cyan]guardrail experiment report {run.id}[/cyan]",
            title="Controlled Experiment",
            border_style=_status_color(conclusion.status),
        )
    )


@experiment_cmd.command("report")
@click.argument("experiment_run_id")
def experiment_report(experiment_run_id: str) -> None:
    """Render a persisted controlled experiment report."""
    store = EvidenceStore()
    run = store.load_experiment(experiment_run_id)
    if run is None:
        console.print(
            Panel(
                f"[bold red]Experiment not found:[/bold red] {experiment_run_id}",
                title="Error",
                border_style="red",
            )
        )
        raise click.Abort()

    conclusion = run.conclusion
    valid, _ = store.verify_experiment_manifest(experiment_run_id)

    console.print(
        Panel(
            f"[bold {_status_color(conclusion.status)}]{conclusion.status}[/bold {_status_color(conclusion.status)}] "
            f"(validity: {conclusion.validity.value})\n"
            f"{run.experiment.hypothesis.statement}\n"
            f"Experiment {run.experiment.id} | run {run.id} | SHA-256 manifest "
            f"{'[green]VALID[/green]' if valid else '[red]INVALID[/red]'}",
            title="Experiment Report",
            border_style=_status_color(conclusion.status),
        )
    )

    if run.comparison is not None:
        table = Table(title="Control vs Treatment (deterministic)", border_style="magenta")
        table.add_column("Metric")
        table.add_column("Role")
        table.add_column("Control (median)")
        table.add_column("Treatment (median)")
        table.add_column("Rel. Change")
        table.add_column("Predicted")
        table.add_column("Measured")
        table.add_column("Meets")
        for m in run.comparison.metrics:
            table.add_row(
                m.metric,
                m.role,
                f"{m.control_median:.2f}" if m.control_median is not None else "—",
                f"{m.treatment_median:.2f}" if m.treatment_median is not None else "—",
                f"{m.relative_change:+.2%}" if m.relative_change is not None else "—",
                m.predicted_direction or "—",
                "[green]yes[/green]" if m.measured else "[red]no[/red]",
                "[green]yes[/green]" if m.meets_prediction else ("[red]contra[/red]" if m.contradicts else "—"),
            )
        console.print(table)
        console.print(f"Workload equivalence: {run.comparison.workload_equivalence_reason}")

    console.print("\n[bold]Conclusion reasons:[/bold]")
    for r in conclusion.reasons:
        console.print(f"  - {r}")


def _target_from_path(path: str):
    from guardrail.discovery.engine import DiscoveryEngine

    return DiscoveryEngine(os.path.abspath(path)).discover().target