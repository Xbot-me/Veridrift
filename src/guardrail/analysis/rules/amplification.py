from __future__ import annotations

import re

from guardrail.models.base import Confidence, RuleCategory, Severity
from guardrail.models.rule import Rule

from .base import AnalysisContext, BaseRule


class AMP001_TightPollingInterval(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="AMP-001",
            name="Tight Polling Interval",
            description="Tight polling loops can amplify load and degrade system performance.",
            category=RuleCategory.RELIABILITY,
            severity=Severity.HIGH,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        # Pattern to catch sleep(< 5) or setInterval(< 5000)
        py_pattern = re.compile(r"sleep\(\s*([0-4](?:\.\d+)?)\s*\)")
        js_pattern = re.compile(r"setInterval\([^,]+,\s*([0-4]?\d{1,3})\s*\)")

        for pf in context.parsed_files:
            for i, line in enumerate(pf.lines):
                py_match = py_pattern.search(line)
                js_match = js_pattern.search(line)

                if py_match or js_match:
                    findings.append(
                        self._create_finding(
                            message="Tight polling interval detected (less than 5 seconds).",
                            file_path=pf.file_path,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            confidence=Confidence.LIKELY,
                            recommendation="Increase polling interval or use event-driven architecture.",
                        )
                    )
        return findings


class AMP002_RetryWithoutBackoff(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="AMP-002",
            name="Retry Without Backoff",
            description="Retrying failing operations without exponential backoff causes retry storms.",
            category=RuleCategory.RELIABILITY,
            severity=Severity.HIGH,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            if hasattr(pf, "ast_tree"):
                from guardrail.analysis.parsers.python_parser import PythonParser

                parser = PythonParser()
                retries = parser.find_retry_patterns(pf)
                for retry in retries:
                    snippet = retry.get("snippet", "")
                    if "wait" not in snippet.lower() and "backoff" not in snippet.lower():
                        findings.append(
                            self._create_finding(
                                message="Retry mechanism lacks exponential backoff.",
                                file_path=pf.file_path,
                                line_number=retry.get("line", 0),
                                code_snippet=snippet,
                                confidence=Confidence.POSSIBLE,
                                recommendation="Implement exponential backoff and jitter.",
                            )
                        )
            else:
                for i, line in enumerate(pf.lines):
                    if "retry" in line.lower() and "backoff" not in line.lower():
                        findings.append(
                            self._create_finding(
                                message="Potential retry without backoff.",
                                file_path=pf.file_path,
                                line_number=i + 1,
                                code_snippet=line.strip(),
                                confidence=Confidence.POSSIBLE,
                                recommendation="Implement exponential backoff.",
                            )
                        )
        return findings


class AMP003_RecursiveNestedHttpRequests(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="AMP-003",
            name="Recursive/Nested HTTP Requests",
            description="Making HTTP requests in loops amplifies external load and latency.",
            category=RuleCategory.RELIABILITY,
            severity=Severity.MEDIUM,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            if hasattr(pf, "ast_tree"):
                from guardrail.analysis.parsers.python_parser import PythonParser

                parser = PythonParser()
                loops = parser.find_loops(pf)
                http_calls = parser.find_http_requests(pf)

                for loop in loops:
                    start, end = loop["line"], loop["end_line"]
                    for call in http_calls:
                        if start <= call["line"] <= end:
                            findings.append(
                                self._create_finding(
                                    message="HTTP request inside a loop.",
                                    file_path=pf.file_path,
                                    line_number=call["line"],
                                    code_snippet=call["snippet"],
                                    confidence=Confidence.CONFIRMED,
                                    recommendation="Batch HTTP requests or fetch concurrently outside the loop.",
                                )
                            )
        return findings
