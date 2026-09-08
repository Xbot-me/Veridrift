from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class LanguageResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    language: str
    file_count: int
    confidence: float

    @property
    def name(self) -> str:
        return self.language


def detect_languages(project_root: Path) -> list[LanguageResult]:
    """Detect programming languages used in the project."""
    EXTENSIONS = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".cpp": "C++",
        ".c": "C",
        ".swift": "Swift",
        ".kt": "Kotlin",
    }

    IGNORE_DIRS = {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".idea",
        ".vscode",
    }

    file_counts = {lang: 0 for lang in EXTENSIONS.values()}
    total_files = 0

    if not project_root.exists() or not project_root.is_dir():
        return []

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            ext = Path(f).suffix.lower()
            if ext in EXTENSIONS:
                lang = EXTENSIONS[ext]
                file_counts[lang] += 1
                total_files += 1

    results = []
    for lang, count in file_counts.items():
        if count > 0:
            confidence = count / total_files if total_files > 0 else 0.0
            results.append(LanguageResult(language=lang, file_count=count, confidence=confidence))

    results.sort(key=lambda x: x.file_count, reverse=True)
    return results
