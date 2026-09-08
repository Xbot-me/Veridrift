from __future__ import annotations

import re

from guardrail.models.base import Confidence, RuleCategory, Severity
from guardrail.models.rule import Rule

from .base import AnalysisContext, BaseRule


class REL001_NoCircuitBreaker(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="REL-001",
            name="No Circuit Breaker on External Call",
            description="External calls without circuit breakers can cascade failures.",
            category=RuleCategory.RELIABILITY,
            severity=Severity.LOW,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        py_req_pattern = re.compile(r"(requests\.(get|post|put)|httpx\.(get|post))")
        circuit_breaker_pkgs = {"pybreaker", "circuitbreaker", "resilience4j"}

        # Check if project uses circuit breaker
        has_cb = False
        for pf in context.parsed_files:
            content = pf.source_code
            if any(pkg in content for pkg in circuit_breaker_pkgs):
                has_cb = True
                break

        if not has_cb:
            for pf in context.parsed_files:
                for i, line in enumerate(pf.lines):
                    if py_req_pattern.search(line):
                        findings.append(
                            self._create_finding(
                                message="External HTTP call detected without global circuit breaker library usage.",
                                file_path=pf.file_path,
                                line_number=i + 1,
                                code_snippet=line.strip(),
                                confidence=Confidence.POSSIBLE,
                                recommendation="Consider wrapping external calls with a circuit breaker.",
                            )
                        )
        return findings
