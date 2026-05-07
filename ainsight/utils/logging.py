"""Centralized logging setup for AInsight-CLI using Rich."""

from __future__ import annotations

import logging
import sys
from typing import ClassVar

from rich.console import Console
from rich.logging import RichHandler

# Shared console instance — import this everywhere for consistent output
console = Console(stderr=False, highlight=True)
err_console = Console(stderr=True, style="bold red")

# Module-level logger
_LOGGER_NAME = "ainsight"


def get_logger(name: str = _LOGGER_NAME) -> logging.Logger:
    """Return (and lazily configure) the AInsight logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        _configure_logger(logger)
    return logger


def _configure_logger(logger: logging.Logger, level: int = logging.INFO) -> None:
    logger.setLevel(level)
    handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_path=False,
        markup=True,
        log_time_format="[%X]",
    )
    handler.setLevel(level)
    logger.addHandler(handler)
    # Prevent double-logging via root logger
    logger.propagate = False


def set_verbosity(verbose: bool) -> None:
    """Raise log level to DEBUG when ``--verbose`` is passed."""
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)


class LogMixin:
    """Mixin that provides a ``self.log`` attribute."""

    _log: ClassVar[logging.Logger]

    @property
    def log(self) -> logging.Logger:
        if not hasattr(self.__class__, "_log"):
            self.__class__._log = get_logger(
                f"{_LOGGER_NAME}.{self.__class__.__module__}.{self.__class__.__name__}"
            )
        return self.__class__._log
