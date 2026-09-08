from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import BaseParser, ParsedFile


class JavaScriptParsedFile(ParsedFile):
    """JavaScript parsed file."""

    pass


class JavaScriptParser(BaseParser):
    language = "javascript"
    file_extensions = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in self.file_extensions

    def parse(self, file_path: Path) -> JavaScriptParsedFile | None:
        try:
            source_code = file_path.read_text(encoding="utf-8")
            lines = source_code.splitlines()
            return JavaScriptParsedFile(
                file_path=file_path, language=self.language, source_code=source_code, lines=lines
            )
        except Exception:
            return None

    def _regex_search(
        self, parsed: ParsedFile, pattern: str, extra: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        results = []
        regex = re.compile(pattern)
        for i, line in enumerate(parsed.lines):
            for match in regex.finditer(line):
                info = {
                    "line": i + 1,
                    "col": match.start(),
                    "file": parsed.file_path,
                    "snippet": line.strip(),
                    "match": match.group(0),
                }
                if extra:
                    info.update(extra)
                results.append(info)
        return results

    def find_function_calls(self, parsed: ParsedFile, function_name: str) -> list[dict[str, Any]]:
        # Naive regex for function calls
        pattern = rf"\b{re.escape(function_name)}\s*\("
        return self._regex_search(parsed, pattern, {"name": function_name})

    def find_string_literals(self, parsed: ParsedFile, pattern: str) -> list[dict[str, Any]]:
        # Combine string matching with the pattern logic
        full_pattern = rf"(['\"`]).*?{pattern}.*?\1"
        return self._regex_search(parsed, full_pattern)

    def find_loops(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        pattern = r"\b(for|while)\s*\("
        return self._regex_search(parsed, pattern)

    def find_imports(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        pattern = r"(\bimport\b.*\bfrom\b|\brequire\s*\()"
        return self._regex_search(parsed, pattern)

    # JS specific finders mimicking Python AST ones for cross-language compatibility
    def find_database_queries(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        pattern = r"\b(query|execute|findMany|findOne|select)\s*\("
        return self._regex_search(parsed, pattern)

    def find_http_requests(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        pattern = r"\b(fetch|axios\.(get|post|put|delete)|http\.request)\s*\("
        return self._regex_search(parsed, pattern)

    def find_timer_intervals(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        pattern = r"\b(setTimeout|setInterval)\s*\("
        return self._regex_search(parsed, pattern)

    def find_retry_patterns(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        pattern = r"\b(retry|p-retry)\s*\("
        return self._regex_search(parsed, pattern)
