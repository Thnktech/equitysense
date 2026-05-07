"""
Lightweight logger configured once for the whole application.

Logs go to both stderr and a rotating cache file so that long
analysis runs can be inspected after the fact.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config.settings import LOG_FILE

_LOGGER_NAME = "stockanalyzer"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a configured logger. Idempotent across calls."""
    base = logging.getLogger(_LOGGER_NAME)
    if not base.handlers:
        base.setLevel(logging.INFO)
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        base.addHandler(stream)

        try:
            file_handler = RotatingFileHandler(
                LOG_FILE, maxBytes=2_000_000, backupCount=2, encoding="utf-8"
            )
            file_handler.setFormatter(fmt)
            base.addHandler(file_handler)
        except OSError:
            # If we cannot open the file (read-only fs, etc.) just skip it.
            pass

    if name:
        return base.getChild(name)
    return base
