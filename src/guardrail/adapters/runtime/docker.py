from __future__ import annotations

from typing import Any

from guardrail.adapters.base import RuntimeAdapter
from guardrail.runtime.container import ContainerManager


class DockerRuntimeAdapter(RuntimeAdapter):
    """Adapter for Docker based execution."""

    def __init__(self) -> None:
        self.manager = ContainerManager()

    @property
    def name(self) -> str:
        return "docker"

    def is_available(self) -> bool:
        """Check if Docker is installed and accessible."""
        return self.manager.connect()

    def run(self, config: Any) -> str:
        """Execute a workload and return an instance ID."""
        raise NotImplementedError("Docker run coming in Milestone 5.")

    def stop(self, id: str) -> None:
        """Stop an executing Docker container."""
        raise NotImplementedError("Docker stop coming in Milestone 5.")

    def get_stats(self, id: str) -> dict[str, Any]:
        """Retrieve telemetry for a Docker container."""
        raise NotImplementedError("Docker stats coming in Milestone 5.")

    def cleanup(self) -> None:
        """Remove leftover Docker resources."""
        self.manager.teardown_all()
