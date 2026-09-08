from __future__ import annotations

from guardrail.models.environment import Environment


class RuntimeEngine:
    """Orchestrator for the execution environment."""

    def __init__(self, environment: Environment):
        self.environment = environment
        self._running = False

    def setup(self) -> bool:
        """
        Set up the isolated execution environment.

        Raises:
            NotImplementedError: Because full runtime requires Docker.
        """
        # Check Docker availability
        # Create network
        # Start containers
        # Wait for health checks
        raise NotImplementedError("Runtime engine requires Docker. Coming in Milestone 5.")

    def teardown(self) -> None:
        """Clean up all containers and networks."""
        pass

    def is_docker_available(self) -> bool:
        """
        Check if Docker is available on this system.

        Returns:
            True if Docker daemon is running and accessible, False otherwise.
        """
        try:
            import docker  # type: ignore

            client = docker.from_env()
            client.ping()
            return True
        except Exception:
            return False
