"""Structured logging utilities for Guardrail."""

from __future__ import annotations

import logging
import sys
from typing import ClassVar


class GuardrailLogger:
    """Centralized logging configuration for the Guardrail engine.

    Provides structured logging with configurable verbosity levels.
    All Guardrail components should obtain loggers through this class.
    """

    _configured: ClassVar[bool] = False
    _log_level: ClassVar[int] = logging.INFO

    @classmethod
    def configure(cls, verbosity: int = 0, quiet: bool = False) -> None:
        """Configure the root guardrail logger.

        Args:
            verbosity: 0 = INFO, 1 = DEBUG, 2+ = DEBUG with third-party debug.
            quiet: If True, suppress all output except errors.
        """
        if quiet:
            cls._log_level = logging.ERROR
        elif verbosity >= 2:
            cls._log_level = logging.DEBUG
            logging.getLogger().setLevel(logging.DEBUG)
        elif verbosity >= 1:
            cls._log_level = logging.DEBUG
        else:
            cls._log_level = logging.INFO

        root_logger = logging.getLogger("guardrail")
        root_logger.setLevel(cls._log_level)

        if not root_logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(cls._log_level)
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
            handler.setFormatter(formatter)
            root_logger.addHandler(handler)

        cls._configured = True

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get a logger for a Guardrail component.

        Args:
            name: Component name (e.g., 'discovery', 'analysis.rules').

        Returns:
            Configured logger instance.
        """
        if not cls._configured:
            cls.configure()
        return logging.getLogger(f"guardrail.{name}")
