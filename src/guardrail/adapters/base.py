from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class LanguageAdapter(ABC):
    """Abstract base class for language-specific analysis adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the language (e.g., 'python')."""
        pass

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        """List of file extensions associated with this language."""
        pass

    @abstractmethod
    def detect(self, project_path: Path) -> bool:
        """Detect if this language is used in the given project."""
        pass

    @abstractmethod
    def get_parser(self) -> Any:
        """Return a parser instance for this language."""
        pass

    @abstractmethod
    def get_entry_points(self, project_path: Path) -> list[str]:
        """Find execution entry points in the project."""
        pass

    @abstractmethod
    def get_dependencies(self, project_path: Path) -> list[str]:
        """Extract declared dependencies from the project."""
        pass


class DatabaseAdapter(ABC):
    """Abstract base class for database integrations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the database type (e.g., 'postgresql')."""
        pass

    @abstractmethod
    def detect_config(self, project_path: Path) -> dict[str, Any] | None:
        """Attempt to extract database connection info from the project."""
        pass

    @abstractmethod
    def get_metrics_query(self) -> str:
        """SQL or command to retrieve performance metrics."""
        pass

    @abstractmethod
    def get_connection_count_query(self) -> str:
        """SQL or command to count active connections."""
        pass

    @abstractmethod
    def default_port(self) -> int:
        """The default network port for this database."""
        pass

    @abstractmethod
    def default_image(self) -> str:
        """The default docker image tag to use for verification."""
        pass


class ProtocolAdapter(ABC):
    """Abstract base class for network protocols."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the protocol (e.g., 'http', 'grpc')."""
        pass

    @abstractmethod
    def detect_endpoints(self, project_path: Path) -> list[dict[str, Any]]:
        """Identify endpoints provided by the project."""
        pass

    @abstractmethod
    def generate_request(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Construct a sample request for the given endpoint."""
        pass


class RuntimeAdapter(ABC):
    """Abstract base class for container/execution runtimes."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the runtime environment (e.g., 'docker')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the runtime is installed and accessible."""
        pass

    @abstractmethod
    def run(self, config: Any) -> str:
        """Execute a workload and return an instance ID."""
        pass

    @abstractmethod
    def stop(self, id: str) -> None:
        """Stop an executing instance."""
        pass

    @abstractmethod
    def get_stats(self, id: str) -> dict[str, Any]:
        """Retrieve telemetry for an instance."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Remove leftover resources."""
        pass
