from __future__ import annotations

from pathlib import Path
from typing import Any

from guardrail.adapters.base import LanguageAdapter


class PythonLanguageAdapter(LanguageAdapter):
    """Adapter for analyzing Python projects."""

    @property
    def name(self) -> str:
        return "python"

    @property
    def extensions(self) -> list[str]:
        return [".py", ".pyi"]

    def detect(self, project_path: Path) -> bool:
        """Detect Python projects by checking for standard files."""
        indicators = ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"]
        for ind in indicators:
            if (project_path / ind).exists():
                return True
        # Fallback to checking for .py files
        return any(project_path.glob("**/*.py"))

    def get_parser(self) -> Any:
        raise NotImplementedError("Python AST parser coming in Milestone 2.")

    def get_entry_points(self, project_path: Path) -> list[str]:
        """Find main execution scripts."""
        # Stub implementation
        return []

    def get_dependencies(self, project_path: Path) -> list[str]:
        """Extract python dependencies."""
        deps = []
        req_file = project_path / "requirements.txt"
        if req_file.exists():
            for line in req_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    deps.append(line)
        return deps
