from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class EndpointResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    method: str
    path: str
    file: str
    line_number: int


def detect_endpoints(project_root: Path) -> list[EndpointResult]:
    """Detect HTTP/RPC endpoints by parsing source code."""
    results = []

    if not project_root.exists() or not project_root.is_dir():
        return results

    IGNORE_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}

    # Patterns for different frameworks
    PATTERNS = [
        # Flask/FastAPI style: @app.get("/path"), @router.post("/path"), @blueprint.route('/path', methods=['GET'])
        (r'@(?:\w+\.)?(get|post|put|delete|patch|route)\s*\(\s*[\'"]([^\'"]+)[\'"]', "python"),
        # Express/Koa style: app.get('/path', ...), router.post('/path', ...)
        (r'(?:\w+\.)?(get|post|put|delete|patch|all)\s*\(\s*[\'"]([^\'"]+)[\'"]', "js"),
    ]

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for f in files:
            if not f.endswith((".py", ".js", ".ts")):
                continue

            file_path = Path(root) / f
            rel_path = str(file_path.relative_to(project_root))

            try:
                content = file_path.read_text(encoding="utf-8")
                lines = content.splitlines()

                for line_idx, line in enumerate(lines):
                    for pattern, lang in PATTERNS:
                        matches = re.finditer(pattern, line)
                        for match in matches:
                            method = match.group(1).upper()
                            if method == "ROUTE" or method == "ALL":
                                method = "ANY"
                            path = match.group(2)
                            results.append(
                                EndpointResult(
                                    method=method,
                                    path=path,
                                    file=rel_path,
                                    line_number=line_idx + 1,
                                )
                            )
            except Exception as e:
                logger.warning(f"Error reading file {rel_path} for endpoints: {e}")

    return results
