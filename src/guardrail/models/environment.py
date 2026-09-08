from __future__ import annotations

from pydantic import Field

from guardrail.models.base import GuardrailModel


class ResourceLimits(GuardrailModel):
    """Resource constraints for infrastructure."""

    cpu_cores: float | None = None
    memory_mb: int | None = None
    pids_limit: int | None = None
    network_bandwidth_mbps: int | None = None
    disk_mb: int | None = None


class ContainerConfig(GuardrailModel):
    """Configuration for a containerized service."""

    image: str
    tag: str = "latest"
    ports: dict[int, int] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)
    volumes: dict[str, str] = Field(default_factory=dict)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    healthcheck_url: str | None = None
    healthcheck_interval_seconds: float = 5.0
    startup_timeout_seconds: float = 60.0


class DatabaseConfig(GuardrailModel):
    """Configuration for a database dependency."""

    type: str
    image: str | None = None
    port: int | None = None
    initial_dataset_rows: dict[str, int] = Field(default_factory=dict)
    max_connections: int | None = None


class Environment(GuardrailModel):
    """Infrastructure context and constraints."""

    name: str = "default"
    containers: dict[str, ContainerConfig] = Field(default_factory=dict)
    databases: dict[str, DatabaseConfig] = Field(default_factory=dict)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    network_isolation: bool = True
    max_duration_seconds: int = 3600
    cleanup_on_exit: bool = True
