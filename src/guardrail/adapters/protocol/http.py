from __future__ import annotations

from pathlib import Path
from typing import Any

from guardrail.adapters.base import ProtocolAdapter


class HTTPProtocolAdapter(ProtocolAdapter):
    """Adapter for HTTP based protocols (REST/GraphQL)."""

    @property
    def name(self) -> str:
        return "http"

    def detect_endpoints(self, project_path: Path) -> list[dict[str, Any]]:
        """Identify HTTP endpoints provided by the project."""
        # Static analysis endpoint discovery goes here
        raise NotImplementedError("HTTP endpoint detection coming in Milestone 3.")

    def generate_request(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Construct a sample HTTP request payload."""
        return {"method": "GET", "url": endpoint, "headers": {"Accept": "application/json"}}
