from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class DatabaseResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    connection_info: str | None = None
    evidence_file: str

    @property
    def name(self) -> str:
        return self.type


def detect_databases(project_root: Path) -> list[DatabaseResult]:
    """Detect databases used in the project."""
    results = []

    if not project_root.exists() or not project_root.is_dir():
        return results

    # Check docker-compose
    for compose_file in [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]:
        file_path = project_root / compose_file
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                # Basic regex search for common DB images to avoid yaml parsing issues if malformed
                if re.search(r"image:\s*postgres", content):
                    results.append(DatabaseResult(type="PostgreSQL", evidence_file=compose_file))
                if re.search(r"image:\s*mysql", content):
                    results.append(DatabaseResult(type="MySQL", evidence_file=compose_file))
                if re.search(r"image:\s*mongo", content):
                    results.append(DatabaseResult(type="MongoDB", evidence_file=compose_file))
                if re.search(r"image:\s*redis", content):
                    results.append(DatabaseResult(type="Redis", evidence_file=compose_file))
            except Exception as e:
                logger.warning(f"Error parsing {compose_file}: {e}")

    # Check .env for connection strings
    env_file = project_root / ".env"
    if env_file.exists():
        try:
            content = env_file.read_text(encoding="utf-8").lower()
            if "postgres" in content:
                results.append(DatabaseResult(type="PostgreSQL", evidence_file=".env"))
            elif "mysql" in content:
                results.append(DatabaseResult(type="MySQL", evidence_file=".env"))
            elif "sqlite" in content:
                results.append(DatabaseResult(type="SQLite", evidence_file=".env"))
            elif "database_url" in content:
                results.append(DatabaseResult(type="PostgreSQL", evidence_file=".env"))
            if "redis" in content:
                results.append(DatabaseResult(type="Redis", evidence_file=".env"))
            if "mongo" in content:
                results.append(DatabaseResult(type="MongoDB", evidence_file=".env"))
        except Exception as e:
            logger.warning(f"Error reading .env: {e}")

    return results
