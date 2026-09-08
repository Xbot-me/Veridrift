from __future__ import annotations

from guardrail.models.environment import Environment


class EnvironmentManager:
    """Manages the complete verification environment lifecycle."""

    def setup(self, environment: Environment) -> bool:
        """
        Set up the necessary infrastructure for the environment.

        Args:
            environment: The environment definition.

        Returns:
            True if setup was successful.

        Raises:
            NotImplementedError: Implemented in future milestone.
        """
        raise NotImplementedError("Environment setup coming in Milestone 5.")

    def teardown(self) -> None:
        """Tear down all managed infrastructure."""
        pass

    def is_ready(self) -> bool:
        """
        Check if the environment is ready for verification execution.

        Returns:
            True if environment is active and healthy.
        """
        return False
