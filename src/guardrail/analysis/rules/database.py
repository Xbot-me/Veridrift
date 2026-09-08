from __future__ import annotations

import ast

from guardrail.models.base import Confidence, RuleCategory, Severity
from guardrail.models.rule import Rule

from .base import AnalysisContext, BaseRule


class DB001_UnboundedDatabaseQuery(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="DB-001",
            name="Unbounded Database Query",
            description="Database query without limits or pagination can cause memory exhaustion.",
            category=RuleCategory.DATABASE,
            severity=Severity.HIGH,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            if hasattr(pf, "ast_tree"):  # Python
                for node in ast.walk(pf.ast_tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        if node.func.attr in ("all", "find", "select"):
                            # check if chained with limit. Hard via AST, so flag if it's just .all()
                            snippet = (
                                pf.lines[node.lineno - 1].strip() if hasattr(node, "lineno") else ""
                            )
                            if ".limit(" not in snippet and "[:" not in snippet:
                                findings.append(
                                    self._create_finding(
                                        message="Unbounded database query detected.",
                                        file_path=pf.file_path,
                                        line_number=getattr(node, "lineno", 0),
                                        code_snippet=snippet,
                                        confidence=Confidence.LIKELY,
                                        recommendation="Add a limit() or use pagination.",
                                    )
                                )
            else:  # JS
                for i, line in enumerate(pf.lines):
                    if (".find()" in line or ".all()" in line) and ".limit(" not in line:
                        findings.append(
                            self._create_finding(
                                message="Unbounded database query detected.",
                                file_path=pf.file_path,
                                line_number=i + 1,
                                code_snippet=line.strip(),
                                confidence=Confidence.LIKELY,
                                recommendation="Add a limit or pagination.",
                            )
                        )
        return findings


class DB002_QueryInsideLoop(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="DB-002",
            name="Query Inside Loop (N+1)",
            description="Executing a database query inside a loop causes the N+1 problem.",
            category=RuleCategory.DATABASE,
            severity=Severity.HIGH,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            if hasattr(pf, "ast_tree"):
                from guardrail.analysis.parsers.python_parser import PythonParser

                parser = PythonParser()
                loops = parser.find_loops(pf)
                db_calls = parser.find_database_queries(pf)

                for loop in loops:
                    start, end = loop["line"], loop["end_line"]
                    for call in db_calls:
                        if start <= call["line"] <= end:
                            findings.append(
                                self._create_finding(
                                    message="Database query executed inside a loop (N+1 risk).",
                                    file_path=pf.file_path,
                                    line_number=call["line"],
                                    code_snippet=call["snippet"],
                                    confidence=Confidence.CONFIRMED,
                                    recommendation="Batch the query outside the loop.",
                                )
                            )
            else:  # JS
                from guardrail.analysis.parsers.javascript_parser import JavaScriptParser

                parser = JavaScriptParser()
                loops = parser.find_loops(pf)
                db_calls = parser.find_database_queries(pf)

                # Naive proximity check for JS (since we don't have block scoped end_line easily)
                # If a query is closely following a loop on the same or next few lines
                for loop in loops:
                    for call in db_calls:
                        if loop["line"] < call["line"] <= loop["line"] + 10:  # heuristic
                            findings.append(
                                self._create_finding(
                                    message="Potential database query executed inside a loop.",
                                    file_path=pf.file_path,
                                    line_number=call["line"],
                                    code_snippet=call["snippet"],
                                    confidence=Confidence.POSSIBLE,
                                    recommendation="Ensure queries are outside loops.",
                                )
                            )
        return findings


class DB003_SelectStarUsage(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="DB-003",
            name="SELECT * Usage",
            description="Using SELECT * retrieves unnecessary columns.",
            category=RuleCategory.DATABASE,
            severity=Severity.MEDIUM,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            for i, line in enumerate(pf.lines):
                if "SELECT *" in line.upper():
                    findings.append(
                        self._create_finding(
                            message="SELECT * found in string literal.",
                            file_path=pf.file_path,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            confidence=Confidence.LIKELY,
                            recommendation="Specify required columns explicitly.",
                        )
                    )
        return findings


class DB004_LargeOffsetPagination(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="DB-004",
            name="Large OFFSET Pagination",
            description="OFFSET pagination degrades performance on deep pages.",
            category=RuleCategory.DATABASE,
            severity=Severity.MEDIUM,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            for i, line in enumerate(pf.lines):
                if ".offset(" in line.lower() or " OFFSET " in line.upper():
                    findings.append(
                        self._create_finding(
                            message="OFFSET pagination used.",
                            file_path=pf.file_path,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            confidence=Confidence.POSSIBLE,
                            recommendation="Use keyset/cursor pagination instead of OFFSET.",
                        )
                    )
        return findings
