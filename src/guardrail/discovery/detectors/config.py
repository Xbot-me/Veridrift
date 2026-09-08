from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class ConfigResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    config_file: str
    type: str
    has_debug_patterns: bool = False


def detect_config(project_root: Path) -> list[ConfigResult]:
    """Detect configuration files and patterns."""
    results = []

    if not project_root.exists() or not project_root.is_dir():
        return results

    IGNORE_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel_root = Path(root).relative_to(project_root)

        for f in files:
            path_str = str(rel_root / f)
            f_lower = f.lower()

            is_config = False
            config_type = ""

            if f_lower.startswith(".env"):
                is_config = True
                config_type = "env"
            elif f_lower.endswith((".yaml", ".yml")):
                # Filter out obvious non-configs
                if "k8s" not in str(rel_root) and "docker-compose" not in f_lower:
                    is_config = True
                    config_type = "yaml"
            elif f_lower.endswith((".toml", ".json", ".ini", ".cfg")):
                if f_lower not in ["package.json", "package-lock.json"]:
                    is_config = True
                    config_type = Path(f).suffix[1:]

            if is_config:
                has_debug = False
                try:
                    file_path = Path(root) / f
                    content = file_path.read_text(encoding="utf-8")
                    if re.search(r"(?i)(debug\s*=\s*true|log_level\s*=\s*debug)", content):
                        has_debug = True
                except Exception as e:
                    logger.debug(f"Could not read {path_str} for debug patterns: {e}")

                results.append(
                    ConfigResult(
                        config_file=path_str, type=config_type, has_debug_patterns=has_debug
                    )
                )

    return results
