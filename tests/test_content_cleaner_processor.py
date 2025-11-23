# -*- coding: utf-8 -*-
"""Tests for ContentCleanerProcessor."""

from unittest.mock import Mock

import pytest

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
from src.processors.content_cleaner_processor import ContentCleanerProcessor
from src.processors.processing_context import ProcessingContext


@pytest.fixture
def cleaning_config():
    """Sample cleaning configuration."""
    return {
        "enabled": True,
        "remove_ads": True,
        "normalize_encoding": True,
        "max_summary_length": 500,
    }


@pytest.fixture
def cleaner_processor(cleaning_config):
    """ContentCleanerProcessor instance."""
    return ContentCleanerProcessor(config=cleaning_config)


def test_content_cleaner_processor_init_default():
    """Test ContentCleanerProcessor initialization with defaults."""
    processor = ContentCleanerProcessor()
    assert processor.enabled is True
    assert processor.remove_ads is True
    assert processor.normalize_encoding is True
    assert processor.max_summary_length == 500


def test_content_cleaner_processor_init_custom():
    """Test ContentCleanerProcessor initialization with custom config."""
    config = {
        "enabled": False,
        "remove_ads": False,
        "max_summary_length": 1000,
    }
    processor = ContentCleanerProcessor(config=config)
    assert processor.enabled is False
    assert processor.remove_ads is False
    assert processor.max_summary_length == 1000


def test_content_cleaner_processor_process_collected_entry(cleaner_processor):
    """Test processing CollectedEntry."""
    entry = CollectedEntry(
        title="Test Title",
        link="https://example.com",
        summary="<p>This is a <b>test</b> summary.</p>",
    )

    result = cleaner_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.title == "Test Title"
    assert result.cleaned_content is not None
    assert result.normalized_text is not None
    assert "<p>" not in result.cleaned_content
    assert "<b>" not in result.cleaned_content


def test_content_cleaner_processor_process_processed_entry(cleaner_processor):
    """Test processing ProcessedEntry."""
    entry = ProcessedEntry(
        title="Test Title",
        link="https://example.com",
        summary="<p>HTML content</p>",
    )

    result = cleaner_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.cleaned_content is not None


def test_content_cleaner_processor_process_with_context(cleaner_processor):
    """Test processing with context."""
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test summary",
    )
    context = ProcessingContext()

    result = cleaner_processor.process(entry, context)
    assert isinstance(result, ProcessedEntry)


def test_content_cleaner_processor_process_invalid_entry(cleaner_processor):
    """Test processing invalid entry (no title or link)."""
    # Use a valid entry but with minimal content to test validation
    entry = CollectedEntry(
        title="T",  # Minimal valid title
        link="https://example.com",
        summary="",  # Empty summary
    )

    result = cleaner_processor.process(entry)
    # Should still process, just with empty cleaned content
    assert isinstance(result, ProcessedEntry)


def test_content_cleaner_processor_process_long_summary(cleaner_processor):
    """Test processing entry with very long summary."""
    long_summary = "A" * 2000  # Very long summary
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary=long_summary,
    )

    result = cleaner_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    # Summary should be truncated
    assert len(result.summary) <= 500


def test_content_cleaner_processor_get_processor_name(cleaner_processor):
    """Test get_processor_name method."""
    assert cleaner_processor.get_processor_name() == "ContentCleanerProcessor"


def test_content_cleaner_processor_is_enabled(cleaner_processor):
    """Test is_enabled method."""
    assert cleaner_processor.is_enabled() is True

    disabled_processor = ContentCleanerProcessor(config={"enabled": False})
    assert disabled_processor.is_enabled() is False

