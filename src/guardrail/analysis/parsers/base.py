from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class ParsedFile(BaseModel):
    """Represents a parsed source file with AST information."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    file_path: Path
    language: str
    source_code: str
    lines: list[str]


class BaseParser(ABC):
    """Base class for language-specific source code parsers."""

    language: str = "unknown"
    file_extensions: list[str] = []

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Determine if this parser can handle the given file."""
        return file_path.suffix in self.file_extensions

    @abstractmethod
    def parse(self, file_path: Path) -> ParsedFile | None:
        """Parse the source file and return a ParsedFile."""
        pass

    @abstractmethod
    def find_function_calls(self, parsed: ParsedFile, function_name: str) -> list[dict[str, Any]]:
        """Find occurrences of a specific function call."""
        pass

    @abstractmethod
    def find_string_literals(self, parsed: ParsedFile, pattern: str) -> list[dict[str, Any]]:
        """Find string literals matching a pattern."""
        pass

    @abstractmethod
    def find_loops(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        """Find loops (for, while) in the code."""
        pass

    @abstractmethod
    def find_imports(self, parsed: ParsedFile) -> list[dict[str, Any]]:
        """Find import statements."""
        pass
