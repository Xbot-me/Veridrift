from __future__ import annotations

import logging
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .detectors.config import detect_config
from .detectors.container import detect_containers
from .detectors.database import detect_databases
from .detectors.endpoints import detect_endpoints
from .detectors.framework import detect_frameworks
from .detectors.language import detect_languages
from .detectors.package_manager import detect_package_managers
from .detectors.services import detect_service_topology
from .graph import ApplicationGraph, GraphEdge, GraphNode

try:
    from guardrail.models.target import DependencyInfo, ServiceInfo, Target
except ImportError:

    class ServiceInfo(BaseModel):
        model_config = ConfigDict(extra="ignore")
        name: str
        frameworks: list[str] = []
        languages: list[str] = []

    class DependencyInfo(BaseModel):
        model_config = ConfigDict(extra="ignore")
        name: str
        type: str

    class Target(BaseModel):
        model_config = ConfigDict(extra="ignore")
        path: str
        services: list[ServiceInfo] = []
        dependencies: list[DependencyInfo] = []


logger = logging.getLogger(__name__)


class DiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target: Target
    graph: ApplicationGraph
    warnings: list[str] = []
    scan_duration_seconds: float = 0.0


class DiscoveryEngine:
    def __init__(self, project_path: str | Path = "."):
        self.project_path = Path(project_path).resolve()

    def discover(self, project_path: str | Path | None = None) -> DiscoveryResult:
        """Run all detectors and build the application graph."""
        if project_path is not None:
            self.project_path = Path(project_path).resolve()

        start_time = time.time()
        warnings = []

        try:
            languages = detect_languages(self.project_path)
            frameworks = detect_frameworks(self.project_path)
            pkg_managers = detect_package_managers(self.project_path)
            databases = detect_databases(self.project_path)
            containers = detect_containers(self.project_path)
            endpoints = detect_endpoints(self.project_path)
            topology = detect_service_topology(self.project_path)
            configs = detect_config(self.project_path)
        except Exception as e:
            logger.error(f"Discovery error: {e}")
            warnings.append(str(e))

            languages = []
            frameworks = []
            pkg_managers = []
            databases = []
            endpoints = []
            topology = []
            configs = []

            class EmptyContainers:
                services = []

            containers = EmptyContainers()

        target = Target(
            path=str(self.project_path),
            name=self.project_path.name,
            languages=[l.language for l in languages],
            frameworks=[f.framework for f in frameworks],
            package_managers=[p.manager for p in pkg_managers],
            endpoints=[getattr(e, "path", str(e)) for e in endpoints],
            config_files=[getattr(c, "evidence_file", str(c)) for c in configs],
        )

        main_service = ServiceInfo(
            name=self.project_path.name,
            language=languages[0].language if languages else None,
            languages=[l.language for l in languages],
            framework=frameworks[0].framework if frameworks else None,
            frameworks=[f.framework for f in frameworks],
        )
        target.services.append(main_service)

        for db in databases:
            target.dependencies.append(DependencyInfo(name=db.type, type="database"))

        graph = ApplicationGraph()

        graph.add_node(
            GraphNode(
                id="main",
                type="service",
                name=self.project_path.name,
                metadata={"languages": [l.language for l in languages]},
            )
        )

        if hasattr(containers, "services"):
            for srv in containers.services:
                graph.add_node(
                    GraphNode(
                        id=srv.name,
                        type="service",
                        name=srv.name,
                        metadata={"image": srv.image} if srv.image else {},
                    )
                )

        for i, db in enumerate(databases):
            db_id = f"db_{i}"
            graph.add_node(
                GraphNode(
                    id=db_id, type="database", name=db.type, metadata={"evidence": db.evidence_file}
                )
            )
            graph.add_edge(GraphEdge(source="main", target=db_id, type="connects_to"))

        for rel in topology:
            graph.add_edge(
                GraphEdge(
                    source=rel.source_service, target=rel.target_service, type=rel.relationship_type
                )
            )

        duration = time.time() - start_time

        return DiscoveryResult(
            target=target, graph=graph, warnings=warnings, scan_duration_seconds=duration
        )
