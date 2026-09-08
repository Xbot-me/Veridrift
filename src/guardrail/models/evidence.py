from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from guardrail.models.base import EvidenceType, GuardrailModel, generate_id


def utc_now() -> datetime:
    return datetime.now(UTC)


class Evidence(GuardrailModel):
    """Evidence record supporting a rule finding."""

    id: str = Field(default_factory=generate_id)
    type: EvidenceType = EvidenceType.STATIC
    source: str = "static_analysis"
    description: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    file_path: str | None = None
    line_number: int | None = None
    code_snippet: str | None = None
    content: str | None = None
    measurement_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)
