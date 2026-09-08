from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from guardrail.analysis.parsers.base import BaseParser, ParsedFile
from guardrail.analysis.parsers.javascript_parser import JavaScriptParser
from guardrail.analysis.parsers.python_parser import PythonParser
from guardrail.analysis.rule_engine import RuleEngine
from guardrail.analysis.rules.base import AnalysisContext
from guardrail.models.rule import Finding


class AnalysisResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    findings: list[Finding]
    files_analyzed: int
    rules_evaluated: int
    duration_seconds: float
    languages_analyzed: list[str]


class AnalysisEngine:
    def __init__(self, project_path: str | Path = ".", register_builtins: bool = True):
        self.project_path = Path(project_path)
        self.rule_engine = RuleEngine(register_builtins=register_builtins)
        self.parsers: list[BaseParser] = []
        if register_builtins:
            self.register_builtin_parsers()

    def register_parser(self, parser: BaseParser) -> None:
        if not any(p.language == parser.language for p in self.parsers):
            self.parsers.append(parser)

    def register_builtin_parsers(self) -> None:
        self.register_parser(PythonParser())
        self.register_parser(JavaScriptParser())

    def analyze(
        self,
        target_or_languages: str | Path | list[str] | None = None,
        languages: list[str] | None = None,
    ) -> AnalysisResult:
        """Run full static analysis on the project directory."""
        if isinstance(target_or_languages, (str, Path)):
            self.project_path = Path(target_or_languages).resolve()
        elif isinstance(target_or_languages, list):
            languages = target_or_languages

        start_time = time.time()

        # Collect source files
        parsed_files: list[ParsedFile] = []
        languages_found = set()

        if not self.project_path.exists() or not self.project_path.is_dir():
            raise ValueError(f"Invalid project path: {self.project_path}")

        for filepath in self.project_path.rglob("*"):
            if not filepath.is_file():
                continue

            # Skip common ignores
            if any(part.startswith(".") for part in filepath.parts):
                continue
            if "node_modules" in filepath.parts or "venv" in filepath.parts:
                continue

            # Parse with appropriate parsers
            for parser in self.parsers:
                if languages and parser.language not in languages:
                    continue

                if parser.can_parse(filepath):
                    parsed = parser.parse(filepath)
                    if parsed:
                        parsed_files.append(parsed)
                        languages_found.add(parser.language)
                        break  # file successfully parsed, stop trying other parsers

        # Build AnalysisContext
        context = AnalysisContext(
            project_path=self.project_path,
            parsed_files=parsed_files,
            languages=list(languages_found),
            frameworks=[],
            config_files={},
        )

        # Evaluate all rules
        findings = self.rule_engine.evaluate_all(context)

        duration = time.time() - start_time

        return AnalysisResult(
            findings=findings,
            files_analyzed=len(parsed_files),
            rules_evaluated=len(self.rule_engine.get_rules()),
            duration_seconds=duration,
            languages_analyzed=list(languages_found),
        )
