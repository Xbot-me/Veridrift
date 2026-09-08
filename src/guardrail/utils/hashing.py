"""Content hashing utilities for evidence integrity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def hash_content(content: str | bytes) -> str:
    """Generate a SHA-256 hash of content.

    Args:
        content: String or bytes to hash.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def hash_file(file_path: str | Path) -> str:
    """Generate a SHA-256 hash of a file's contents.

    Args:
        file_path: Path to the file to hash.

    Returns:
        Hex digest of the SHA-256 hash.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_dict(data: dict[str, Any]) -> str:
    """Generate a deterministic hash of a dictionary.

    Serializes to sorted JSON before hashing to ensure determinism.

    Args:
        data: Dictionary to hash.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hash_content(serialized)
