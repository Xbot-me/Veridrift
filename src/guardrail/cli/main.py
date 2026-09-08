from __future__ import annotations

import sys

import click
from rich.console import Console

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="guardrail")
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v, -vv)")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-error output")
@click.pass_context
def cli(ctx: click.Context, verbose: int, quiet: bool) -> None:
    """Guardrail — Production Verification Engine for AI-Generated Software.

    Empirically verify whether software can safely operate under expected
    production workloads. Evidence over opinion. Measurements over predictions.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["console"] = console

    # Configure logging based on verbosity
    try:
        from guardrail.utils import GuardrailLogger

        GuardrailLogger.configure(verbosity=verbose, quiet=quiet)
    except ImportError:
        pass


# Register subcommands
from guardrail.cli.analyze import analyze_cmd
from guardrail.cli.compare import compare_cmd
from guardrail.cli.experiment import experiment_cmd
from guardrail.cli.init import init_cmd
from guardrail.cli.inspect_cmd import inspect_cmd
from guardrail.cli.report import report_cmd
from guardrail.cli.run import run_cmd
from guardrail.cli.verify import verify_cmd

cli.add_command(init_cmd)
cli.add_command(inspect_cmd)
cli.add_command(analyze_cmd)
cli.add_command(run_cmd)
cli.add_command(verify_cmd)
cli.add_command(report_cmd)
cli.add_command(compare_cmd)
cli.add_command(experiment_cmd)

if __name__ == "__main__":
    cli()
