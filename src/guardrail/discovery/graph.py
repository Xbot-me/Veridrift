from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    type: str  # 'service', 'database', 'cache', 'queue', 'external_api', 'reverse_proxy'
    name: str
    metadata: dict[str, Any] = {}


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source: str  # node id
    target: str  # node id
    type: str  # 'depends_on', 'connects_to', 'proxies_to'
    metadata: dict[str, Any] = {}


class ApplicationGraph(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    def add_node(self, node: GraphNode) -> None:
        if not any(n.id == node.id for n in self.nodes):
            self.nodes.append(node)

    def add_edge(self, edge: GraphEdge) -> None:
        if not any(
            e.source == edge.source and e.target == edge.target and e.type == edge.type
            for e in self.edges
        ):
            self.edges.append(edge)

    def to_mermaid(self) -> str:
        """Generate Mermaid diagram string."""
        lines = ["graph TD"]
        for node in self.nodes:
            # Escape quotes in name
            safe_name = node.name.replace('"', '\\"')
            lines.append(f'    {node.id}["{safe_name} ({node.type})"]')
        for edge in self.edges:
            lines.append(f"    {edge.source} -->|{edge.type}| {edge.target}")
        return "\n".join(lines)

    def get_dependencies(self, node_id: str) -> list[GraphNode]:
        """Get nodes that the given node depends on."""
        target_ids = [e.target for e in self.edges if e.source == node_id]
        return [n for n in self.nodes if n.id in target_ids]
