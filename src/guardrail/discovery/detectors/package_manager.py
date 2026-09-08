from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class PackageManagerResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    manager: str
    evidence_file: str

    @property
    def name(self) -> str:
        return self.manager


def detect_package_managers(project_root: Path) -> list[PackageManagerResult]:
    """Detect package managers used in the project based on lock files."""
    results = []

    if not project_root.exists() or not project_root.is_dir():
        return results

    managers = {
        "requirements.txt": "pip",
        "poetry.lock": "poetry",
        "Pipfile.lock": "pipenv",
        "uv.lock": "uv",
        "package-lock.json": "npm",
        "package.json": "npm",
        "yarn.lock": "yarn",
        "pnpm-lock.yaml": "pnpm",
        "bun.lockb": "bun",
        "go.sum": "go modules",
        "Cargo.lock": "cargo",
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "composer.lock": "composer",
        "Gemfile.lock": "bundler",
    }

    seen_managers = set()
    for filename, manager in managers.items():
        if (project_root / filename).exists() and manager not in seen_managers:
            results.append(PackageManagerResult(manager=manager, evidence_file=filename))
            seen_managers.add(manager)

    return results
