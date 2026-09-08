from __future__ import annotations

from pathlib import Path
from typing import Any

from guardrail.adapters.base import DatabaseAdapter


class PostgreSQLAdapter(DatabaseAdapter):
    """Adapter for PostgreSQL databases."""

    @property
    def name(self) -> str:
        return "postgresql"

    def detect_config(self, project_path: Path) -> dict[str, Any] | None:
        """Attempt to extract database connection info from the project."""
        # In a real scenario, this might parse .env files or standard configs
        return None

    def get_metrics_query(self) -> str:
        """SQL to retrieve performance metrics."""
        return "SELECT * FROM pg_stat_database;"

    def get_connection_count_query(self) -> str:
        """SQL to count active connections."""
        return "SELECT count(*) FROM pg_stat_activity;"

    def default_port(self) -> int:
        return 5432

    def default_image(self) -> str:
        return "postgres:15-alpine"
