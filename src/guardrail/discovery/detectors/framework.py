from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class FrameworkResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    framework: str
    version: str | None = None
    evidence_file: str

    @property
    def name(self) -> str:
        return self.framework


def detect_frameworks(project_root: Path) -> list[FrameworkResult]:
    """Detect frameworks used in the project based on package manifests and imports."""
    results = []

    if not project_root.exists() or not project_root.is_dir():
        return results

    # Check Python requirements.txt
    req_file = project_root / "requirements.txt"
    if req_file.exists():
        try:
            content = req_file.read_text(encoding="utf-8").lower()
            for fw in [
                "flask",
                "django",
                "fastapi",
                "tornado",
                "aiohttp",
                "starlette",
                "sqlalchemy",
                "celery",
            ]:
                if re.search(rf"^{fw}\b", content, re.MULTILINE):
                    results.append(
                        FrameworkResult(framework=fw.capitalize(), evidence_file="requirements.txt")
                    )
        except Exception as e:
            logger.warning(f"Error reading requirements.txt: {e}")

    # Check JS package.json
    pkg_file = project_root / "package.json"
    if pkg_file.exists():
        try:
            content = pkg_file.read_text(encoding="utf-8").lower()
            for fw in [
                "express",
                "koa",
                "nest",
                "next",
                "react",
                "vue",
                "angular",
                "prisma",
                "sequelize",
            ]:
                if f'"{fw}"' in content:
                    results.append(
                        FrameworkResult(framework=fw.capitalize(), evidence_file="package.json")
                    )
        except Exception as e:
            logger.warning(f"Error reading package.json: {e}")

    # Check Go go.mod
    go_file = project_root / "go.mod"
    if go_file.exists():
        try:
            content = go_file.read_text(encoding="utf-8").lower()
            for fw in [
                "gin-gonic/gin",
                "labstack/echo",
                "gofiber/fiber",
                "jinzhu/gorm",
                "go-gorm/gorm",
            ]:
                if fw in content:
                    results.append(
                        FrameworkResult(
                            framework=fw.split("/")[-1].capitalize(), evidence_file="go.mod"
                        )
                    )
        except Exception as e:
            logger.warning(f"Error reading go.mod: {e}")

    # Check Ruby Gemfile
    gemfile = project_root / "Gemfile"
    if gemfile.exists():
        try:
            content = gemfile.read_text(encoding="utf-8").lower()
            for fw in ["rails", "sinatra"]:
                if f"gem '{fw}'" in content or f'gem "{fw}"' in content:
                    results.append(
                        FrameworkResult(framework=fw.capitalize(), evidence_file="Gemfile")
                    )
        except Exception as e:
            logger.warning(f"Error reading Gemfile: {e}")

    # Check Java pom.xml
    pom_file = project_root / "pom.xml"
    if pom_file.exists():
        try:
            content = pom_file.read_text(encoding="utf-8").lower()
            if "spring-boot" in content:
                results.append(FrameworkResult(framework="Spring Boot", evidence_file="pom.xml"))
            if "quarkus" in content:
                results.append(FrameworkResult(framework="Quarkus", evidence_file="pom.xml"))
        except Exception as e:
            logger.warning(f"Error reading pom.xml: {e}")

    return results
