from __future__ import annotations

from guardrail.models.run import VerificationRun


class JSONReporter:
    """Reporter that serializes the verification run to JSON."""

    def render(self, run: VerificationRun) -> str:
        """
        Render the verification run to a JSON string.

        Args:
            run: The completed verification run data.

        Returns:
            A formatted JSON string.
        """
        return run.model_dump_json(indent=2)
