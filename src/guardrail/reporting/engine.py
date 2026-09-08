from __future__ import annotations

from guardrail.models.run import VerificationRun
from guardrail.reporting.html_reporter import HTMLReporter
from guardrail.reporting.json_reporter import JSONReporter
from guardrail.reporting.markdown_reporter import MarkdownReporter


class ReportEngine:
    """Orchestrator for generating verification reports."""

    def generate(self, run: VerificationRun, format: str = "markdown") -> str:
        """
        Generate a report in the specified format.

        Args:
            run: The completed verification run data.
            format: The output format ('json', 'markdown', 'html').

        Returns:
            The formatted report as a string.
        """
        if format == "json":
            return JSONReporter().render(run)
        if format == "markdown":
            return MarkdownReporter().render(run)
        if format == "html":
            return HTMLReporter().render(run)

        raise ValueError(f"Unsupported report format: {format}")
