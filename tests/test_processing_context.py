# -*- coding: utf-8 -*-
"""Tests for ProcessingContext."""

from unittest.mock import Mock

import pytest

from src.processors.processing_context import ProcessingContext


def test_processing_context_init_default():
    """Test ProcessingContext initialization with defaults."""
    context = ProcessingContext()
    assert context.embedding_model is None
    assert context.cache is None
    assert context.config == {}
    assert context.stats == {}


def test_processing_context_init_with_values():
    """Test ProcessingContext initialization with values."""
    embedding_model = Mock()
    cache = Mock()
    config = {"test": "value"}
    stats = {"count": 5}

    context = ProcessingContext(
        embedding_model=embedding_model,
        cache=cache,
        config=config,
        stats=stats,
    )

    assert context.embedding_model == embedding_model
    assert context.cache == cache
    assert context.config == config
    assert context.stats == stats


def test_processing_context_get_stat():
    """Test get_stat method."""
    context = ProcessingContext(stats={"count": 10, "errors": 2})

    assert context.get_stat("count") == 10
    assert context.get_stat("errors") == 2
    assert context.get_stat("missing") == 0
    assert context.get_stat("missing", default=5) == 5


def test_processing_context_increment_stat():
    """Test increment_stat method."""
    context = ProcessingContext(stats={"count": 5})

    context.increment_stat("count")
    assert context.get_stat("count") == 6

    context.increment_stat("count", amount=3)
    assert context.get_stat("count") == 9

    context.increment_stat("new_stat")
    assert context.get_stat("new_stat") == 1

