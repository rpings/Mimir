# -*- coding: utf-8 -*-
"""Tests for BaseProcessor improvements."""

import asyncio
from unittest.mock import Mock

import pytest

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.processing_context import ProcessingContext


class MockProcessor(BaseProcessor):
    """Test processor implementation."""

    def __init__(self, config=None, return_none=False):
        """Initialize test processor."""
        super().__init__(config)
        self.return_none = return_none

    def process(self, entry, context=None):
        """Process entry."""
        if self.return_none:
            return None
        if isinstance(entry, ProcessedEntry):
            return entry
        return ProcessedEntry.from_collected(entry)

    def get_processor_name(self):
        """Get processor name."""
        return "TestProcessor"


def test_base_processor_init_default():
    """Test BaseProcessor initialization with defaults."""
    processor = MockProcessor()
    assert processor.enabled is True
    assert processor.config == {}


def test_base_processor_init_with_config():
    """Test BaseProcessor initialization with config."""
    config = {"enabled": False, "test": "value"}
    processor = MockProcessor(config=config)
    assert processor.enabled is False
    assert processor.config == config


def test_base_processor_process_collected_entry():
    """Test processing CollectedEntry."""
    processor = MockProcessor()
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test summary",
    )

    result = processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.title == "Test"


def test_base_processor_process_processed_entry():
    """Test processing ProcessedEntry."""
    processor = MockProcessor()
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test summary",
    )

    result = processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result == entry


def test_base_processor_process_with_context():
    """Test processing with context."""
    processor = MockProcessor()
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )
    context = ProcessingContext()

    result = processor.process(entry, context)
    assert isinstance(result, ProcessedEntry)


def test_base_processor_process_return_none():
    """Test processor returning None (skip)."""
    processor = MockProcessor(return_none=True)
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )

    result = processor.process(entry)
    assert result is None


@pytest.mark.asyncio
async def test_base_processor_aprocess():
    """Test async processing."""
    processor = MockProcessor()
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )

    result = await processor.aprocess(entry)
    assert isinstance(result, ProcessedEntry)


def test_base_processor_is_enabled():
    """Test is_enabled method."""
    processor = MockProcessor()
    assert processor.is_enabled() is True

    disabled_processor = MockProcessor(config={"enabled": False})
    assert disabled_processor.is_enabled() is False


def test_base_processor_get_processor_name():
    """Test get_processor_name method."""
    processor = MockProcessor()
    assert processor.get_processor_name() == "TestProcessor"


def test_processed_entry_from_collected():
    """Test ProcessedEntry.from_collected method."""
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test summary",
        published="2024-01-01",
        source_name="Test Source",
        source_type="blog",
    )

    processed = ProcessedEntry.from_collected(entry)
    assert processed.title == "Test"
    assert processed.link == entry.link
    assert processed.summary == "Test summary"
    assert processed.published == "2024-01-01"
    assert processed.source_name == "Test Source"
    assert processed.source_type == "blog"

