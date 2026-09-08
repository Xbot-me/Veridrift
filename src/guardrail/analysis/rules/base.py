from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from guardrail.analysis.parsers.base import ParsedFile
from guardrail.models.base import Confidence, EvidenceType
from guardrail.models.evidence import Evidence
from guardrail.models.rule import Finding, Rule


class AnalysisContext(BaseModel):
    """Context provided to rules for evaluation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_path: Path
    parsed_files: list[ParsedFile]
    languages: list[str] = []
    frameworks: list[str] = []
    config_files: dict[str, Any] = {}


class BaseRule(ABC):
    """Base class for all static analysis rules."""

    @property
    @abstractmethod
    def rule_definition(self) -> Rule:
        """Return the rule metadata."""
        pass

    @abstractmethod
    def evaluate(self, context: AnalysisContext) -> list[Finding]:
        """Evaluate this rule against the analysis context. Return findings."""
        pass

    def _create_finding(
        self,
        message: str,
        file_path: str | Path | None = None,
        line_number: int | None = None,
        code_snippet: str | None = None,
        confidence: Confidence = Confidence.LIKELY,
        recommendation: str | None = None,
        consequence: str | None = None,
        hypothesized_risk: str | None = None,
    ) -> Finding:
        """Helper to create a Finding with proper rule metadata."""
        evidence = []
        if file_path:
            evidence.append(
                Evidence(
                    type=EvidenceType.STATIC,
                    source="static_analysis",
                    description="Static rule detection",
                    file_path=str(file_path),
                    line_number=line_number or 0,
                    code_snippet=code_snippet or "",
                    content=code_snippet or "",
                )
            )

        rule = self.rule_definition
        risk = hypothesized_risk or consequence or f"Risk under production load: {rule.description}"

        return Finding(
            rule_id=rule.id,
            rule_name=rule.name,
            category=rule.category,
            severity=rule.severity,
            confidence=confidence,
            message=message,
            file_path=str(file_path) if file_path else None,
            line_number=line_number,
            code_snippet=code_snippet,
            evidence=evidence,
            recommendation=recommendation,
            potential_consequence=consequence,
            hypothesized_risk=risk,
        )
