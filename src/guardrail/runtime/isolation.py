from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

# Default security settings
DEFAULT_CPU_LIMIT = 2.0  # cores
DEFAULT_MEMORY_LIMIT_MB = 512
DEFAULT_PIDS_LIMIT = 256
DEFAULT_NETWORK_ISOLATED = True
DEFAULT_READ_ONLY_ROOT = False
DEFAULT_MAX_DURATION_SECONDS = 3600

CAP_DROP_ALL = ["ALL"]
CAP_ADD_MINIMAL: list[str] = []  # No extra caps by default


class IsolationConfig(BaseModel):
    """Security configuration for container execution."""

    model_config = ConfigDict(frozen=True)

    cpu_limit: float = DEFAULT_CPU_LIMIT
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB
    pids_limit: int = DEFAULT_PIDS_LIMIT
    network_isolated: bool = DEFAULT_NETWORK_ISOLATED
    read_only_root: bool = DEFAULT_READ_ONLY_ROOT
    max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS
    cap_drop: list[str] = CAP_DROP_ALL
    cap_add: list[str] = CAP_ADD_MINIMAL


def build_container_security_opts(config: IsolationConfig) -> dict[str, Any]:
    """
    Convert isolation config to Docker run kwargs.

    Args:
        config: The isolation configuration model.

    Returns:
        A dictionary of kwargs suitable for the Docker SDK.
    """
    return {
        "nano_cpus": int(config.cpu_limit * 1e9),
        "mem_limit": f"{config.memory_limit_mb}m",
        "pids_limit": config.pids_limit,
        "network_mode": "none" if config.network_isolated else "bridge",
        "read_only": config.read_only_root,
        "cap_drop": config.cap_drop,
        "cap_add": config.cap_add,
        "security_opt": ["no-new-privileges:true"],
    }
