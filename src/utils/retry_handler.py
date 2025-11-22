# -*- coding: utf-8 -*-
"""Retry mechanism utilities."""

from functools import wraps
from typing import Any, Callable, TypeVar, Union

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")


def retry_on_connection_error(
    max_attempts: int = 3,
    min_wait: float = 2.0,
    max_wait: float = 10.0,
    multiplier: float = 1.0,
):
    """Decorator for retrying on connection-related errors.

    Args:
        max_attempts: Maximum number of retry attempts.
        min_wait: Minimum wait time between retries (seconds).
        max_wait: Maximum wait time between retries (seconds).
        multiplier: Exponential backoff multiplier.

    Returns:
        Decorator function.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True,
    )


def retry_on_value_error(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 5.0,
    multiplier: float = 1.0,
):
    """Decorator for retrying on ValueError.

    Args:
        max_attempts: Maximum number of retry attempts.
        min_wait: Minimum wait time between retries (seconds).
        max_wait: Maximum wait time between retries (seconds).
        multiplier: Exponential backoff multiplier.

    Returns:
        Decorator function.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(ValueError),
        reraise=True,
    )


def retry_with_config(
    config: dict[str, Any],
    exception_types: tuple[type[Exception], ...] = (Exception,),
):
    """Create retry decorator from configuration.

    Args:
        config: Configuration dictionary with retry settings.
        exception_types: Tuple of exception types to retry on.

    Returns:
        Retry decorator.
    """
    max_attempts = config.get("max_attempts", 3)
    backoff_factor = config.get("backoff_factor", 2.0)
    min_wait = config.get("min_wait", 1.0)
    max_wait = config.get("max_wait", 10.0)

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=backoff_factor, min=min_wait, max=max_wait
        ),
        retry=retry_if_exception_type(exception_types),
        reraise=True,
    )


def safe_execute(
    func: Callable[..., T],
    default: T,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute function safely, returning default value on exception.

    Args:
        func: Function to execute.
        default: Default value to return on exception.
        *args: Positional arguments for function.
        **kwargs: Keyword arguments for function.

    Returns:
        Function result or default value.
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return default

