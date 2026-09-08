"""Allow running guardrail as `python -m guardrail`."""

from __future__ import annotations

from guardrail.cli.main import cli

if __name__ == "__main__":
    cli()
