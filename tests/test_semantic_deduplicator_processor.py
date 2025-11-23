# -*- coding: utf-8 -*-
"""Tests for SemanticDeduplicatorProcessor."""

from unittest.mock import Mock, MagicMock

import pytest

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
from src.processors.processing_context import ProcessingContext
from src.processors.semantic_deduplicator_processor import SemanticDeduplicatorProcessor


@pytest.fixture
def semantic_config():
    """Sample semantic deduplication configuration."""
    return {
        "enabled": True,
        "similarity_threshold": 0.85,
        "embedding_model": None,
        "use_openai_embedding": False,
    }


@pytest.fixture
def semantic_processor(semantic_config):
    """SemanticDeduplicatorProcessor instance."""
    return SemanticDeduplicatorProcessor(config=semantic_config)


def test_semantic_deduplicator_processor_init_default():
    """Test SemanticDeduplicatorProcessor initialization with defaults."""
    processor = SemanticDeduplicatorProcessor()
    assert processor.enabled is True
    assert processor.similarity_threshold == 0.85
    assert processor.use_openai_embedding is False


def test_semantic_deduplicator_processor_process_no_content(semantic_processor):
    """Test processing entry with no content."""
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="",  # No content
    )

    result = semantic_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.is_semantic_duplicate is False


def test_semantic_deduplicator_processor_process_short_content(semantic_processor):
    """Test processing entry with short content."""
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Short",  # Too short
    )

    result = semantic_processor.process(entry)
    assert isinstance(result, ProcessedEntry)


def test_semantic_deduplicator_processor_process_no_embedding_model(semantic_processor):
    """Test processing without embedding model."""
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="This is a test summary with sufficient content length for processing.",
    )

    result = semantic_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.is_semantic_duplicate is False


def test_semantic_deduplicator_processor_process_with_embedding_model(semantic_processor):
    """Test processing with embedding model in context."""
    # Mock embedding model
    mock_model = MagicMock()
    mock_model.encode = MagicMock(return_value=[0.1] * 384)

    context = ProcessingContext(embedding_model=mock_model)

    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="This is a test summary with sufficient content length for processing.",
    )

    result = semantic_processor.process(entry, context)
    assert isinstance(result, ProcessedEntry)


def test_semantic_deduplicator_processor_load_embedding_model():
    """Test loading embedding model."""
    processor = SemanticDeduplicatorProcessor(
        config={"embedding_model": "sentence-transformers/all-MiniLM-L6-v2"}
    )

    # Should raise ImportError if sentence-transformers not installed
    with pytest.raises(ImportError):
        processor._load_embedding_model("test-model")


def test_semantic_deduplicator_processor_compute_embedding(semantic_processor):
    """Test computing embedding."""
    mock_model = MagicMock()
    mock_model.encode = MagicMock(return_value=[0.1, 0.2, 0.3])

    embedding = semantic_processor._compute_embedding("test text", mock_model)
    assert isinstance(embedding, list)
    assert len(embedding) == 3


def test_semantic_deduplicator_processor_compute_embedding_with_cache(semantic_processor):
    """Test computing embedding with cache."""
    mock_model = MagicMock()
    mock_cache = MagicMock()
    mock_cache.get = MagicMock(return_value=[0.1, 0.2, 0.3])

    context = ProcessingContext(cache=mock_cache)

    embedding = semantic_processor._compute_embedding("test text", mock_model, context)
    assert embedding == [0.1, 0.2, 0.3]
    # Should use cache, not call model
    mock_model.encode.assert_not_called()


def test_semantic_deduplicator_processor_get_processor_name(semantic_processor):
    """Test get_processor_name method."""
    assert semantic_processor.get_processor_name() == "SemanticDeduplicatorProcessor"

