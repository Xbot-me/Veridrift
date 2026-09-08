from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from guardrail.adapters.base import LanguageAdapter


class JavaScriptLanguageAdapter(LanguageAdapter):
    """Adapter for analyzing JavaScript/Node.js projects."""

    @property
    def name(self) -> str:
        return "javascript"

    @property
    def extensions(self) -> list[str]:
        return [".js", ".jsx", ".ts", ".tsx"]

    def detect(self, project_path: Path) -> bool:
        """Detect JS projects by checking for standard files."""
        return (project_path / "package.json").exists()

    def get_parser(self) -> Any:
        raise NotImplementedError("JavaScript AST parser coming in Milestone 2.")

    def get_entry_points(self, project_path: Path) -> list[str]:
        """Find main execution scripts."""
        pkg_json = project_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text())
                if "main" in data:
                    return [data["main"]]
            except Exception:
                pass
        return []

    def get_dependencies(self, project_path: Path) -> list[str]:
        """Extract Node.js dependencies."""
        deps = []
        pkg_json = project_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text())
                deps.extend(list(data.get("dependencies", {}).keys()))
            except Exception:
                pass
        return deps
