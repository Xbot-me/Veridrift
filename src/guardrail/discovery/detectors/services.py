from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class ServiceTopologyResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_service: str
    target_service: str
    relationship_type: str
    evidence: str


def detect_service_topology(project_root: Path) -> list[ServiceTopologyResult]:
    """Detect inter-service relationships."""
    results = []

    if not project_root.exists() or not project_root.is_dir():
        return results

    for compose_file in [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]:
        file_path = project_root / compose_file
        if file_path.exists():
            try:
                import yaml

                with open(file_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data and "services" in data and isinstance(data["services"], dict):
                    for srv_name, srv_def in data["services"].items():
                        if not isinstance(srv_def, dict):
                            continue

                        # depends_on
                        if "depends_on" in srv_def:
                            depends_on = srv_def["depends_on"]
                            if isinstance(depends_on, list):
                                for target in depends_on:
                                    results.append(
                                        ServiceTopologyResult(
                                            source_service=srv_name,
                                            target_service=target,
                                            relationship_type="depends_on",
                                            evidence=f"{compose_file}: depends_on",
                                        )
                                    )
                            elif isinstance(depends_on, dict):
                                for target in depends_on.keys():
                                    results.append(
                                        ServiceTopologyResult(
                                            source_service=srv_name,
                                            target_service=target,
                                            relationship_type="depends_on",
                                            evidence=f"{compose_file}: depends_on",
                                        )
                                    )

                        # links
                        if "links" in srv_def:
                            links = srv_def["links"]
                            if isinstance(links, list):
                                for link in links:
                                    target = link.split(":")[0]
                                    results.append(
                                        ServiceTopologyResult(
                                            source_service=srv_name,
                                            target_service=target,
                                            relationship_type="links",
                                            evidence=f"{compose_file}: links",
                                        )
                                    )
            except Exception as e:
                logger.warning(f"Error parsing {compose_file} for topology: {e}")

    return results
