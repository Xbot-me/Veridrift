from __future__ import annotations

from guardrail.models.environment import Environment


class RuntimeEngine:
    """Orchestrator for the execution environment."""

    def __init__(self, environment: Environment | None = None):
        self.environment = environment or Environment(name="default")
        self._running = False

    def available_runtimes(self) -> list[str]:
        """
        Probe which runtimes are usable on this machine without raising.

        Checks the local-process adapter first (zero-dependency), then the
        optional Docker daemon. Any probe failure degrades to that runtime
        simply being absent; callers are expected to handle an empty result
        (no usable runtime) explicitly.

        Returns:
            Names of usable runtimes, e.g. ["local_process", "docker"].
        """
        names: list[str] = []

        try:
            from guardrail.runtime.local_process import LocalProcessRuntimeAdapter

            if LocalProcessRuntimeAdapter().is_available():
                names.append("local_process")
        except Exception:
            # Availability checks must never prevent a verification run.
            pass

        try:
            from guardrail.adapters.runtime.docker import DockerRuntimeAdapter

            if self.is_docker_available() and DockerRuntimeAdapter:
                names.append("docker")
        except Exception:
            # Availability checks must never prevent a verification run.
            pass

        return names

    def is_available(self) -> bool:
        """
        True if at least one execution runtime (local process or Docker) is usable.

        Never raises: availability probing must not crash the CLI; callers
        degrade to an explicit INCONCLUSIVE outcome when nothing is usable.
        """
        return bool(self.available_runtimes())

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
