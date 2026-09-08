from __future__ import annotations

from pydantic import Field

from guardrail.models.base import GuardrailModel


class ServiceInfo(GuardrailModel):
    """Information about a specific service within the target."""

    name: str
    language: str | None = None
    languages: list[str] = Field(default_factory=list)
    framework: str | None = None
    frameworks: list[str] = Field(default_factory=list)
    entry_point: str | None = None
    port: int | None = None


class DependencyInfo(GuardrailModel):
    """Information about an external dependency."""

    name: str
    type: str
    connection_info: dict[str, str] | None = None


class Target(GuardrailModel):
    """The application target being verified."""

    path: str
    name: str = ""
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    services: list[ServiceInfo] = Field(default_factory=list)
    dependencies: list[DependencyInfo] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list)
    containers: list[str] = Field(default_factory=list)
    test_suites: list[str] = Field(default_factory=list)
    build_systems: list[str] = Field(default_factory=list)
