from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class ContainerService(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    image: str | None = None
    ports: list[str] = []
    volumes: list[str] = []
    networks: list[str] = []


class ContainerResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dockerfiles: list[str] = []
    compose_files: list[str] = []
    k8s_manifests: list[str] = []
    services: list[ContainerService] = []


def detect_containers(project_root: Path) -> ContainerResult:
    """Detect container configurations and services."""
    result = ContainerResult()

    if not project_root.exists() or not project_root.is_dir():
        return result

    IGNORE_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel_root = Path(root).relative_to(project_root)

        for f in files:
            path_str = str(rel_root / f)
            f_lower = f.lower()

            # Dockerfiles
            if (
                f_lower == "dockerfile"
                or f_lower.startswith("dockerfile.")
                or f_lower.endswith(".dockerfile")
            ):
                result.dockerfiles.append(path_str)

            # Compose files
            if f_lower in [
                "docker-compose.yml",
                "docker-compose.yaml",
                "compose.yml",
                "compose.yaml",
            ]:
                result.compose_files.append(path_str)
                # Try a very basic parse for services using string manipulation since yaml isn't guaranteed
                # A proper implementation would use pyyaml but we handle it safely here.
                try:
                    import yaml

                    compose_path = Path(root) / f
                    with open(compose_path, encoding="utf-8") as file:
                        data = yaml.safe_load(file)
                        if data and "services" in data and isinstance(data["services"], dict):
                            for srv_name, srv_def in data["services"].items():
                                if isinstance(srv_def, dict):
                                    result.services.append(
                                        ContainerService(
                                            name=srv_name,
                                            image=srv_def.get("image"),
                                            ports=[str(p) for p in srv_def.get("ports", [])]
                                            if isinstance(srv_def.get("ports"), list)
                                            else [],
                                            volumes=[str(v) for v in srv_def.get("volumes", [])]
                                            if isinstance(srv_def.get("volumes"), list)
                                            else [],
                                            networks=list(srv_def.get("networks", {}).keys())
                                            if isinstance(srv_def.get("networks"), dict)
                                            else (
                                                srv_def.get("networks", [])
                                                if isinstance(srv_def.get("networks"), list)
                                                else []
                                            ),
                                        )
                                    )
                except Exception as e:
                    logger.warning(f"Error parsing compose file {path_str}: {e}")

            # K8s manifests
            if f_lower in ["deployment.yaml", "service.yaml"] or "k8s" in path_str.split(os.sep):
                if f_lower.endswith(".yaml") or f_lower.endswith(".yml"):
                    result.k8s_manifests.append(path_str)

    return result
