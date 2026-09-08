# Guardrail

**Production Verification Engine for AI-Generated Software**

Guardrail empirically verifies whether software can safely operate under expected production workloads. It uses deterministic rules, static analysis, controlled execution, instrumentation, and hard thresholds to produce evidence-backed PASS / WARNING / FAIL verdicts.

> **"We tested it, measured it, found its limits, and can show you the evidence."**

## Core Principles

```
Deterministic rules → Static evidence → Runtime instrumentation →
Controlled experiments → Measured results → Hard thresholds → PASS / WARNING / FAIL
```

- **Evidence over opinion** — every finding links to concrete evidence
- **Measured over predicted** — empirical results, not assumptions
- **Deterministic over probabilistic** — hard rules, not LLM confidence scores
- **Reproducible** — every run can be replayed and compared

## Quick Start

```bash
# Install
pip install guardrail

# Initialize in your project
guardrail init

# Discover project structure
guardrail inspect ./my-project

# Run static analysis
guardrail analyze ./my-project

# Full verification run (requires Docker)
guardrail run ./my-project

# Generate report
guardrail report <run-id>

# Compare two runs
guardrail compare <run-1> <run-2>
```

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/
```

## License

MIT
