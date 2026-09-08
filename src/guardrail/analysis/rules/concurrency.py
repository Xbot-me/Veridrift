from __future__ import annotations

import re

from guardrail.models.base import Confidence, RuleCategory, Severity
from guardrail.models.rule import Rule

from .base import AnalysisContext, BaseRule


class CONC001_UnboundedWorkerCreation(BaseRule):
    @property
    def rule_definition(self) -> Rule:
        return Rule(
            id="CONC-001",
            name="Unbounded Worker/Thread Creation",
            description="Spawning threads or workers in a loop without bounds can crash the system.",
            category=RuleCategory.CONCURRENCY,
            severity=Severity.HIGH,
        )

    def evaluate(self, context: AnalysisContext) -> list:
        findings = []
        for pf in context.parsed_files:
            if hasattr(pf, "ast_tree"):
                from guardrail.analysis.parsers.python_parser import PythonParser

                parser = PythonParser()
                loops = parser.find_loops(pf)

                # Check for Thread(), Process(), asyncio.create_task()
                pattern = re.compile(r"(Thread\(|Process\(|asyncio\.create_task\()")
                for loop in loops:
                    start, end = loop["line"], loop["end_line"]
                    for i in range(start, min(end, len(pf.lines))):
                        line = pf.lines[i]
                        if pattern.search(line):
                            findings.append(
                                self._create_finding(
                                    message="Thread or task created unbounded in a loop.",
                                    file_path=pf.file_path,
                                    line_number=i + 1,
                                    code_snippet=line.strip(),
                                    confidence=Confidence.CONFIRMED,
                                    recommendation="Use a ThreadPoolExecutor or bounded semaphore.",
                                )
                            )
            else:
                for i, line in enumerate(pf.lines):
                    if "new Worker(" in line or "new Thread(" in line:
                        findings.append(
                            self._create_finding(
                                message="Potential unbounded worker creation.",
                                file_path=pf.file_path,
                                line_number=i + 1,
                                code_snippet=line.strip(),
                                confidence=Confidence.POSSIBLE,
                                recommendation="Use a pool instead of raw thread creation.",
                            )
                        )
        return findings
