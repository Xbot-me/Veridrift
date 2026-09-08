from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from guardrail.models.measurement import ResourceMetrics
from guardrail.models.target import Target


@dataclass
class RuntimeInstance:
    """Represents a running application instance being verified."""

    instance_id: str
    target: Target
    host: str = "127.0.0.1"
    port: int = 5000
    base_url: str = "http://127.0.0.1:5000"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    process_handle: Any = None
    env_vars: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeAdapter(ABC):
    """Abstract base class for execution environments (Process, Docker, Kubernetes)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the runtime adapter."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this runtime is available on the current machine."""
        pass

    @abstractmethod
    def start(
        self,
        target: Target,
        port: int | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> RuntimeInstance:
        """
        Start the target application in the execution environment.

        Args:
            target: The discovered target application.
            port: Preferred host port (if None, an open port is selected).
            env_vars: Environment variables to inject.

        Returns:
            The running RuntimeInstance.
        """
        pass

    @abstractmethod
    def stop(self, instance: RuntimeInstance) -> None:
        """Stop and clean up the running application instance."""
        pass

    @abstractmethod
    def health(
        self,
        instance: RuntimeInstance,
        timeout_seconds: float = 10.0,
        path: str = "/",
    ) -> bool:
        """
        Verify that the application instance is responsive and healthy.

        Args:
            instance: The running RuntimeInstance.
            timeout_seconds: Maximum time to wait for healthiness.
            path: Relative path to ping.

        Returns:
            True if healthy, False if timed out or failed.
        """
        pass

    @abstractmethod
    def get_metrics(self, instance: RuntimeInstance) -> ResourceMetrics:
        """Collect current system resource telemetry for the running instance."""
        pass

    @abstractmethod
    def get_logs(self, instance: RuntimeInstance) -> str:
        """Retrieve stdout/stderr logs from the running instance."""
        pass
