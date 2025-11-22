# -*- coding: utf-8 -*-
"""Tests for utils module."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

from src.utils.config_loader import ConfigLoader
from src.utils.logger import setup_logger, get_logger
from src.utils.retry_handler import (
    retry_on_connection_error,
    retry_on_value_error,
    safe_execute,
)


@pytest.fixture
def config_dir(tmp_path):
    """Temporary config directory."""
    config_path = tmp_path / "configs"
    config_path.mkdir()
    return config_path


def test_config_loader_load_yaml(config_dir):
    """Test loading YAML configuration."""
    config_file = config_dir / "test.yml"
    config_file.write_text("key: value\nnumber: 42")

    loader = ConfigLoader(config_dir=str(config_dir))
    config = loader.load_yaml("test.yml")

    assert config["key"] == "value"
    assert config["number"] == 42


def test_config_loader_missing_file(config_dir):
    """Test loading non-existent file."""
    loader = ConfigLoader(config_dir=str(config_dir))

    with pytest.raises(FileNotFoundError):
        loader.load_yaml("missing.yml")


def test_config_loader_env_substitution(config_dir, monkeypatch):
    """Test environment variable substitution."""
    monkeypatch.setenv("TEST_VAR", "substituted_value")
    config_file = config_dir / "test.yml"
    config_file.write_text("key: ${TEST_VAR}")

    loader = ConfigLoader(config_dir=str(config_dir))
    config = loader.load_yaml("test.yml")

    assert config["key"] == "substituted_value"


def test_config_loader_env_missing(config_dir):
    """Test missing environment variable."""
    config_file = config_dir / "test.yml"
    config_file.write_text("key: ${MISSING_VAR}")

    loader = ConfigLoader(config_dir=str(config_dir))
    config = loader.load_yaml("test.yml")

    # Should keep original if env var not found
    assert config["key"] == "${MISSING_VAR}"


def test_config_loader_get_config_caching(config_dir):
    """Test config caching."""
    config_file = config_dir / "test.yml"
    config_file.write_text("key: value")

    loader = ConfigLoader(config_dir=str(config_dir))
    config1 = loader.get_config("test.yml")
    config2 = loader.get_config("test.yml")

    assert config1 == config2
    assert config1 is config2  # Same object (cached)


def test_config_loader_get_rss_sources(config_dir):
    """Test getting RSS sources."""
    sources_file = config_dir / "sources" / "rss.yaml"
    sources_file.parent.mkdir()
    sources_file.write_text("feeds:\n  - name: Test\n    url: https://test.com")

    loader = ConfigLoader(config_dir=str(config_dir))
    sources = loader.get_rss_sources()

    assert len(sources) == 1
    assert sources[0]["name"] == "Test"


def test_config_loader_get_classification_rules(config_dir):
    """Test getting classification rules."""
    rules_file = config_dir / "sources" / "rules.yaml"
    rules_file.parent.mkdir()
    rules_file.write_text("topics:\n  AI: [ai, ml]\npriority:\n  High: [release]")

    loader = ConfigLoader(config_dir=str(config_dir))
    rules = loader.get_classification_rules()

    assert "topics" in rules
    assert "priority" in rules


def test_logger_setup():
    """Test logger setup."""
    logger = setup_logger("test_logger")
    assert logger.name == "test_logger"
    assert logger.level <= 20  # INFO or lower


def test_logger_setup_with_file(tmp_path):
    """Test logger setup with file."""
    log_dir = tmp_path / "logs"
    log_file = log_dir / "test.log"
    logger = setup_logger("test_logger_file", log_file="test.log", log_dir=str(log_dir))

    logger.info("Test message")
    # Force flush and close to ensure file is written
    for handler in logger.handlers:
        handler.flush()
        if hasattr(handler, 'close'):
            handler.close()
    
    # Reopen logger to check file was created
    import logging
    logging.shutdown()
    
    assert log_file.exists()


def test_logger_get_logger():
    """Test getting logger instance."""
    logger1 = get_logger("test")
    logger2 = get_logger("test")
    assert logger1 is logger2  # Same instance


def test_retry_on_connection_error_success():
    """Test retry decorator on success."""
    @retry_on_connection_error(max_attempts=3)
    def success_func():
        return "success"

    assert success_func() == "success"


def test_retry_on_connection_error_retry():
    """Test retry decorator retries on connection error."""
    call_count = 0

    @retry_on_connection_error(max_attempts=3, min_wait=0.1, max_wait=0.2)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("Connection failed")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 2


def test_retry_on_value_error():
    """Test retry on ValueError."""
    call_count = 0

    @retry_on_value_error(max_attempts=3, min_wait=0.1, max_wait=0.2)
    def value_error_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Invalid value")
        return "success"

    result = value_error_func()
    assert result == "success"
    assert call_count == 2


def test_safe_execute_success():
    """Test safe_execute on success."""
    def func():
        return "success"

    result = safe_execute(func, "default")
    assert result == "success"


def test_safe_execute_exception():
    """Test safe_execute returns default on exception."""
    def func():
        raise ValueError("Error")

    result = safe_execute(func, "default")
    assert result == "default"


def test_safe_execute_with_args():
    """Test safe_execute with arguments."""
    def func(x, y):
        return x + y

    result = safe_execute(func, 0, 2, 3)
    assert result == 5


def test_retry_with_config():
    """Test retry with configuration."""
    from src.utils.retry_handler import retry_with_config

    call_count = 0

    @retry_with_config(
        config={"max_attempts": 3, "backoff_factor": 1.0, "min_wait": 0.1, "max_wait": 0.2},
        exception_types=(ConnectionError,)
    )
    def test_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("Error")
        return "success"

    result = test_func()
    assert result == "success"
    assert call_count == 2

