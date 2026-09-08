from __future__ import annotations

import re

from guardrail.models.base import Confidence, RuleCategory, Severity
from guardrail.models.rule import Rule

from .base import AnalysisContext, BaseRule


class NET001_MissingTimeoutOnHttpRequest(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="NET-001",
            name="Missing Timeout on HTTP Request",
            description="HTTP requests without timeouts can hang indefinitely and consume resources.",
            category=RuleCategory.NETWORK,
            severity=Severity.HIGH,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        py_req_pattern = re.compile(
            r"(requests\.(get|post|put|delete|patch)|httpx\.(get|post))\(.*?\)"
        )

        for pf in context.parsed_files:
            for i, line in enumerate(pf.lines):
                if py_req_pattern.search(line) and "timeout=" not in line:
                    findings.append(
                        self._create_finding(
                            message="HTTP request missing explicit timeout parameter.",
                            file_path=pf.file_path,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            confidence=Confidence.CONFIRMED,
                            recommendation="Always set a `timeout` parameter for external calls.",
                        )
                    )
                elif ("fetch(" in line or "axios." in line) and "timeout" not in line.lower():
                    # For JS, check if timeout is mentioned in nearby configuration
                    findings.append(
                        self._create_finding(
                            message="Potential missing timeout on HTTP request.",
                            file_path=pf.file_path,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            confidence=Confidence.POSSIBLE,
                            recommendation="Configure timeout for network clients.",
                        )
                    )
        return findings


class NET002_UnboundedRetryLoop(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="NET-002",
            name="Unbounded Retry Loop",
            description="Retry loops without a maximum attempt limit can run forever.",
            category=RuleCategory.NETWORK,
            severity=Severity.HIGH,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            if hasattr(pf, "ast_tree"):
                from guardrail.analysis.parsers.python_parser import PythonParser

                parser = PythonParser()
                loops = parser.find_loops(pf)
                for loop in loops:
                    snippet = loop.get("snippet", "")
                    if loop.get("type") == "While" and "True" in snippet:
                        # Unbounded while loop, check if it has a try block via node info
                        if "try:" in "".join(pf.lines[loop["line"] : loop["end_line"]]):
                            findings.append(
                                self._create_finding(
                                    message="Potential unbounded retry loop (while True + try).",
                                    file_path=pf.file_path,
                                    line_number=loop["line"],
                                    code_snippet=snippet,
                                    confidence=Confidence.POSSIBLE,
                                    recommendation="Add a maximum retry count limit.",
                                )
                            )
        return findings
