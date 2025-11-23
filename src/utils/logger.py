# -*- coding: utf-8 -*-
"""Logging utilities using loguru."""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(
    name: str,
    log_level: str = "INFO",
    log_file: str | None = None,
    log_dir: str | None = None,
) -> None:
    """Set up loguru logger configuration.

    Args:
        name: Logger name (typically __name__).
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional log file name. If None, logs only to console.
        log_dir: Directory for log files. Defaults to 'data/logs'.
    """
    # Remove default handler
    logger.remove()

    # Add console handler
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
        level=log_level.upper(),
        colorize=True,
    )

    # Add file handler if specified
    if log_file:
        if log_dir is None:
            log_dir = Path(__file__).parent.parent.parent / "data" / "logs"
        else:
            log_dir = Path(log_dir)

        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / log_file

        logger.add(
            log_path,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="30 days",
            encoding="utf-8",
        )


def get_logger(name: str):
    """Get loguru logger instance.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Loguru logger instance (bound to the name).
    """
    # Bind the name to the logger for context
    return logger.bind(name=name)
