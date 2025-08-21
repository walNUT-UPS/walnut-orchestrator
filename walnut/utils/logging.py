"""
Project-wide logging setup for walNUT.

Provides a simple, consistent console logger with optional JSON output.
Controlled via environment variables:
- WALNUT_LOG_LEVEL: DEBUG|INFO|WARNING|ERROR (default: INFO)
- WALNUT_LOG_FORMAT: text|json (default: text)
"""
from __future__ import annotations

import logging
import os
from typing import Optional


def _get_level() -> int:
    level = os.getenv("WALNUT_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level, logging.INFO)


def setup_logging(force: bool = False, *, logger: Optional[logging.Logger] = None) -> None:
    """Configure root logging for console output.

    If a handler is already present and force is False, this is a no-op.
    If WALNUT_LOG_FORMAT=json and python-json-logger is available, emits JSON.
    """
    target_logger = logger or logging.getLogger()
    if target_logger.handlers and not force:
        return

    # Clear existing handlers when forcing
    if force:
        for h in list(target_logger.handlers):
            target_logger.removeHandler(h)

    log_level = _get_level()
    target_logger.setLevel(log_level)

    handler = logging.StreamHandler()

    fmt = os.getenv("WALNUT_LOG_FORMAT", "text").lower()
    if fmt == "json":
        try:
            from pythonjsonlogger import jsonlogger  # type: ignore

            formatter = jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"levelname": "level", "name": "logger"},
            )
        except Exception:
            formatter = logging.Formatter(
                fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

    handler.setFormatter(formatter)
    target_logger.addHandler(handler)

