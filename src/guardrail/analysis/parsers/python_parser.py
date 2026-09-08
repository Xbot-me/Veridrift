from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from .base import BaseParser, ParsedFile


class PythonParsedFile(ParsedFile):
    """Parsed Python file including AST."""

    ast_tree: ast.Module | None = None


class PythonParser(BaseParser):
    language = "python"
    file_extensions = [".py"]

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in self.file_extensions

    def parse(self, file_path: Path) -> PythonParsedFile | None:
        try:
            source_code = file_path.read_text(encoding="utf-8")
            lines = source_code.splitlines()
            ast_tree = ast.parse(source_code, filename=str(file_path))
            return PythonParsedFile(
                file_path=file_path,
                language=self.language,
                source_code=source_code,
                lines=lines,
                ast_tree=ast_tree,
            )
        except Exception:
            return None

    def _get_snippet(self, parsed: PythonParsedFile, node: ast.AST) -> str:
        if hasattr(node, "lineno"):
            idx = node.lineno - 1
            if 0 <= idx < len(parsed.lines):
                return parsed.lines[idx].strip()
        return ""

    def _create_node_info(
        self, parsed: PythonParsedFile, node: ast.AST, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        info = {
            "line": getattr(node, "lineno", -1),
            "col": getattr(node, "col_offset", -1),
            "file": parsed.file_path,
            "snippet": self._get_snippet(parsed, node),
            "node": node,
        }
        if extra:
            info.update(extra)
        return info

    def find_function_calls(self, parsed: ParsedFile, function_name: str) -> list[dict[str, Any]]:
        if not isinstance(parsed, PythonParsedFile) or not parsed.ast_tree:
            return []

        results = []
        for node in ast.walk(parsed.ast_tree):
            if isinstance(node, ast.Call):
                call_name = ""
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr

                if call_name == function_name:
                    results.append(
                        self._create_node_info(parsed, node, {"name": call_name, "args": node.args})
                    )
        return results

    def find_string_literals(self, parsed: ParsedFile, pattern: str) -> list[dict[str, Any]]:
        if not isinstance(parsed, PythonParsedFile) or not parsed.ast_tree:
            return []

        regex = re.compile(pattern)
        results = []
        for node in ast.walk(parsed.ast_tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if regex.search(node.value):
                    results.append(self._create_node_info(parsed, node, {"value": node.value}))
        return results

    def find_loops(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        if not isinstance(parsed, PythonParsedFile) or not parsed.ast_tree:
            return []

        results = []
        for node in ast.walk(parsed.ast_tree):
            if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                end_line = getattr(node, "end_lineno", getattr(node, "lineno", -1))
                results.append(
                    self._create_node_info(
                        parsed, node, {"type": node.__class__.__name__, "end_line": end_line}
                    )
                )
        return results

    def find_imports(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        if not isinstance(parsed, PythonParsedFile) or not parsed.ast_tree:
            return []

        results = []
        for node in ast.walk(parsed.ast_tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    results.append(self._create_node_info(parsed, node, {"module": alias.name}))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    results.append(self._create_node_info(parsed, node, {"module": node.module}))
        return results

    def find_database_queries(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        """Look for common ORM or DB execution calls."""
        if not isinstance(parsed, PythonParsedFile) or not parsed.ast_tree:
            return []

        results = []
        db_methods = {"execute", "query", "filter", "all", "find", "select"}
        for node in ast.walk(parsed.ast_tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in db_methods:
                    results.append(self._create_node_info(parsed, node, {"method": node.func.attr}))
        return results

    def find_http_requests(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        if not isinstance(parsed, PythonParsedFile) or not parsed.ast_tree:
            return []

        results = []
        http_methods = {"get", "post", "put", "delete", "patch", "request"}
        for node in ast.walk(parsed.ast_tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in http_methods:
                    if isinstance(node.func.value, ast.Name) and node.func.value.id in {
                        "requests",
                        "httpx",
                        "session",
                    }:
                        results.append(
                            self._create_node_info(parsed, node, {"method": node.func.attr})
                        )
        return results

    def find_timer_intervals(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        if not isinstance(parsed, PythonParsedFile) or not parsed.ast_tree:
            return []

        results = []
        for node in ast.walk(parsed.ast_tree):
            if isinstance(node, ast.Call):
                if (isinstance(node.func, ast.Attribute) and node.func.attr == "sleep") or (
                    isinstance(node.func, ast.Name) and node.func.id == "sleep"
                ):
                    results.append(self._create_node_info(parsed, node, {"method": "sleep"}))
        return results

    def find_retry_patterns(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        if not isinstance(parsed, PythonParsedFile) or not parsed.ast_tree:
            return []

        results = []
        for node in ast.walk(parsed.ast_tree):
            # Check for @retry decorators
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Name)
                        and "retry" in dec.func.id.lower()
                    ) or (isinstance(dec, ast.Name) and "retry" in dec.id.lower()):
                        results.append(self._create_node_info(parsed, dec, {"type": "decorator"}))
            # Check for while True + try
            if isinstance(node, ast.While):
                has_try = any(isinstance(child, ast.Try) for child in node.body)
                if has_try:
                    results.append(self._create_node_info(parsed, node, {"type": "while_try"}))
        return results
