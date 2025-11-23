# -*- coding: utf-8 -*-
"""Tests for base collector module."""

import pytest
from unittest.mock import Mock

from src.collectors.base_collector import BaseCollector, CollectedEntry


class ConcreteCollector(BaseCollector):
    """Concrete collector for testing."""
    
    def collect(self):
        """Collect entries."""
        return [
            CollectedEntry(
                title="Test",
                link="https://example.com",
            )
        ]
    
    def get_source_name(self):
        """Get source name."""
        return "Test Collector"


@pytest.mark.asyncio
async def test_base_collector_acollect_default():
    """Test default async collect implementation."""
    collector = ConcreteCollector()
    entries = await collector.acollect()
    
    assert len(entries) == 1
    assert entries[0].title == "Test"


def test_collected_entry_to_dict():
    """Test CollectedEntry to_dict method."""
    entry = CollectedEntry(
        title="Test Title",
        link="https://example.com",
        summary="Test summary",
        published="2024-01-01T00:00:00Z",
        source_name="Test Source",
        source_type="blog",
    )
    
    result = entry.to_dict()
    
    assert result["title"] == "Test Title"
    # HttpUrl may normalize URLs (add trailing slash)
    assert result["link"].rstrip("/") == "https://example.com"
    assert result["summary"] == "Test summary"
    assert result["published"] == "2024-01-01T00:00:00Z"
    assert result["source_name"] == "Test Source"
    assert result["source_type"] == "blog"

