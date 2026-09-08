"""File system utilities for project scanning."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

# Directories to always skip when scanning projects
SKIP_DIRECTORIES: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "htmlcov",
        ".coverage",
        ".idea",
        ".vscode",
        "vendor",
        "target",  # Rust/Java build output
        ".gradle",
        ".mvn",
        ".next",
        ".nuxt",
        ".output",
        "coverage",
        ".turbo",
        ".vercel",
        ".netlify",
    }
)

# Binary file extensions to skip
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".dylib",
        ".exe",
        ".bin",
        ".obj",
        ".o",
        ".a",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".svg",
        ".webp",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wav",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".lock",  # lock files can be huge
    }
)


def should_skip_directory(dir_name: str) -> bool:
    """Check if a directory should be skipped during scanning.

    Args:
        dir_name: Name of the directory (not full path).

    Returns:
        True if the directory should be skipped.
    """
    if dir_name.startswith("."):
        # Skip most hidden directories, but allow some
        allowed_hidden = {".github", ".gitlab", ".circleci"}
        return dir_name not in allowed_hidden
    return dir_name in SKIP_DIRECTORIES or dir_name.endswith(".egg-info")


def is_text_file(file_path: Path) -> bool:
    """Check if a file is likely a text file based on extension.

    Args:
        file_path: Path to check.

    Returns:
        True if the file is likely text.
    """
    return file_path.suffix.lower() not in BINARY_EXTENSIONS


def walk_project_files(
    project_path: str | Path,
    extensions: set[str] | None = None,
    max_files: int = 10000,
) -> Iterator[Path]:
    """Walk project files, skipping irrelevant directories and binary files.

    Args:
        project_path: Root directory to scan.
        extensions: If provided, only yield files with these extensions.
        max_files: Maximum number of files to yield.

    Yields:
        Path objects for each relevant file.
    """
    root = Path(project_path).resolve()
    count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Modify dirnames in-place to skip unwanted directories
        dirnames[:] = [d for d in dirnames if not should_skip_directory(d)]

        for filename in filenames:
            if count >= max_files:
                return

            file_path = Path(dirpath) / filename

            # Skip binary files
            if not is_text_file(file_path):
                continue

            # Filter by extension if specified
            if extensions and file_path.suffix.lower() not in extensions:
                continue

            yield file_path
            count += 1


def read_file_safe(file_path: str | Path, max_size_bytes: int = 10 * 1024 * 1024) -> str | None:
    """Read a file's contents safely, returning None on failure.

    Args:
        file_path: Path to the file.
        max_size_bytes: Maximum file size to read (default 10MB).

    Returns:
        File contents as string, or None if the file cannot be read.
    """
    path = Path(file_path)
    try:
        if not path.exists() or not path.is_file():
            return None
        if path.stat().st_size > max_size_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return None


def get_line_snippet(
    source: str,
    line_number: int,
    context_lines: int = 2,
) -> str:
    """Extract a code snippet around a specific line number.

    Args:
        source: Full source code string.
        line_number: 1-based line number to center on.
        context_lines: Number of lines to include before and after.

    Returns:
        Code snippet with line numbers.
    """
    lines = source.splitlines()
    if line_number < 1 or line_number > len(lines):
        return ""

    start = max(0, line_number - 1 - context_lines)
    end = min(len(lines), line_number + context_lines)

    snippet_lines = []
    for i in range(start, end):
        marker = "→ " if i == line_number - 1 else "  "
        snippet_lines.append(f"{marker}{i + 1:4d} │ {lines[i]}")

    return "\n".join(snippet_lines)


def find_files_by_name(
    project_path: str | Path,
    filenames: set[str],
) -> list[Path]:
    """Find files matching specific filenames in the project.

    Args:
        project_path: Root directory to search.
        filenames: Set of filenames to look for (case-sensitive).

    Returns:
        List of matching file paths.
    """
    results: list[Path] = []
    root = Path(project_path).resolve()

    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_directory(d)]
        for f in files:
            if f in filenames:
                results.append(Path(dirpath) / f)

    return results


def find_files_by_extension(
    project_path: str | Path,
    extensions: set[str],
) -> list[Path]:
    """Find files matching specific extensions in the project.

    Args:
        project_path: Root directory to search.
        extensions: Set of extensions including dot (e.g., {'.py', '.js'}).

    Returns:
        List of matching file paths.
    """
    return list(walk_project_files(project_path, extensions=extensions))
