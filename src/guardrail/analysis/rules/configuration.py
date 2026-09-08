from __future__ import annotations

import re

from guardrail.models.base import Confidence, RuleCategory, Severity
from guardrail.models.rule import Rule

from .base import AnalysisContext, BaseRule


class CFG001_DebugModeEnabled(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="CFG-001",
            name="Debug Mode Enabled",
            description="Leaving debug mode on in production exposes sensitive data and stack traces.",
            category=RuleCategory.CONFIGURATION,
            severity=Severity.MEDIUM,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        debug_pattern = re.compile(
            r"(DEBUG\s*=\s*True|NODE_ENV\s*=\s*['\"]development['\"]|app\.run\([^)]*debug=True[^)]*\))",
            re.IGNORECASE,
        )

        for pf in context.parsed_files:
            for i, line in enumerate(pf.lines):
                if debug_pattern.search(line):
                    findings.append(
                        self._create_finding(
                            message="Debug mode potentially enabled in code.",
                            file_path=pf.file_path,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            confidence=Confidence.LIKELY,
                            recommendation="Ensure debug mode is driven by environment variables and disabled in production.",
                        )
                    )
        return findings


class CFG002_MissingResourceLimits(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="CFG-002",
            name="Missing Resource Limits",
            description="Services without memory or CPU limits can affect neighboring services.",
            category=RuleCategory.CONFIGURATION,
            severity=Severity.MEDIUM,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        # In a real scanner, we'd check Dockerfiles/docker-compose config here.
        # Check connection pool sizes as a proxy in code
        for pf in context.parsed_files:
            for i, line in enumerate(pf.lines):
                if "create_engine" in line and "pool_size" not in line:
                    findings.append(
                        self._create_finding(
                            message="Database connection pool without max_size limit.",
                            file_path=pf.file_path,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            confidence=Confidence.POSSIBLE,
                            recommendation="Specify pool_size and max_overflow limits explicitly.",
                        )
                    )
        return findings
