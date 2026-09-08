from __future__ import annotations

import ast

from guardrail.models.base import Confidence, RuleCategory, Severity
from guardrail.models.rule import Rule

from .base import AnalysisContext, BaseRule


class RES001_UnclosedFileConnection(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="RES-001",
            name="Unclosed File or Connection",
            description="Failing to close resources leaks file descriptors.",
            category=RuleCategory.RESOURCE,
            severity=Severity.MEDIUM,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            if hasattr(pf, "ast_tree"):
                for node in ast.walk(pf.ast_tree):
                    # Flag open() calls that are not in a With statement
                    if isinstance(node, ast.Assign):
                        if isinstance(node.value, ast.Call) and isinstance(
                            node.value.func, ast.Name
                        ):
                            if node.value.func.id == "open":
                                snippet = (
                                    pf.lines[node.lineno - 1].strip()
                                    if hasattr(node, "lineno")
                                    else ""
                                )
                                findings.append(
                                    self._create_finding(
                                        message="File opened without context manager.",
                                        file_path=pf.file_path,
                                        line_number=getattr(node, "lineno", 0),
                                        code_snippet=snippet,
                                        confidence=Confidence.LIKELY,
                                        recommendation="Use `with open(...) as f:` to ensure closure.",
                                    )
                                )
        return findings


class RES002_UnboundedInMemoryCollection(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="RES-002",
            name="Unbounded In-Memory Collection",
            description="Appending to lists/dicts in unbounded loops risks out-of-memory errors.",
            category=RuleCategory.RESOURCE,
            severity=Severity.MEDIUM,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            if hasattr(pf, "ast_tree"):
                from guardrail.analysis.parsers.python_parser import PythonParser

                parser = PythonParser()
                loops = parser.find_loops(pf)

                for loop in loops:
                    start, end = loop["line"], loop["end_line"]
                    # Look for list.append within the loop bounds
                    for node in ast.walk(pf.ast_tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                            if node.func.attr == "append" and hasattr(node, "lineno"):
                                if start <= node.lineno <= end:
                                    findings.append(
                                        self._create_finding(
                                            message="Collection appended to inside loop without bounds.",
                                            file_path=pf.file_path,
                                            line_number=node.lineno,
                                            code_snippet=pf.lines[node.lineno - 1].strip(),
                                            confidence=Confidence.POSSIBLE,
                                            recommendation="Monitor memory usage or paginate the processing.",
                                        )
                                    )
        return findings
