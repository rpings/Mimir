# -*- coding: utf-8 -*-
"""Tests for collectors module."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from src.collectors.rss_collector import RSSCollector


@pytest.fixture
def sample_feed_config():
    """Sample RSS feed configuration."""
    return {
        "name": "Test Feed",
        "url": "https://example.com/rss",
        "source_type": "blog",
    }


@pytest.fixture
def mock_feedparser():
    """Mock feedparser.parse."""
    with patch("src.collectors.rss_collector.feedparser") as mock:
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "title": "Test Article",
                "link": "https://example.com/article",
                "summary": "Test summary",
                "published": "2024-01-01T00:00:00Z",
            }
        ]
        mock.parse.return_value = mock_feed
        yield mock


def test_rss_collector_init(sample_feed_config):
    """Test RSS collector initialization."""
    collector = RSSCollector(feed_config=sample_feed_config)
    assert collector.get_source_name() == "Test Feed"
    assert collector.feed_config == sample_feed_config


def test_rss_collector_collect_success(sample_feed_config, mock_feedparser):
    """Test successful RSS feed collection."""
    from src.collectors.base_collector import CollectedEntry

    collector = RSSCollector(feed_config=sample_feed_config)
    entries = collector.collect()

    assert isinstance(entries, list)
    assert len(entries) > 0
    assert isinstance(entries[0], CollectedEntry)
    assert entries[0].title == "Test Article"
    assert str(entries[0].link) == "https://example.com/article"


def test_rss_collector_missing_url():
    """Test RSS collector with missing URL."""
    collector = RSSCollector(feed_config={"name": "Test"})
    with pytest.raises(ValueError, match="Feed URL is required"):
        collector.collect()


def test_rss_collector_bozo_warning(sample_feed_config):
    """Test RSS collector handles parsing warnings."""
    with patch("src.collectors.rss_collector.feedparser") as mock:
        mock_feed = Mock()
        mock_feed.bozo = True
        mock_feed.bozo_exception = "Parse error"
        mock_feed.entries = [
            {
                "title": "Test",
                "link": "https://example.com",
                "summary": "Test",
            }
        ]
        mock.parse.return_value = mock_feed

        collector = RSSCollector(feed_config=sample_feed_config)
        entries = collector.collect()
        assert len(entries) > 0  # Should still process entries


def test_rss_collector_empty_entries(sample_feed_config):
    """Test RSS collector with empty feed."""
    with patch("src.collectors.rss_collector.feedparser") as mock:
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock.parse.return_value = mock_feed

        collector = RSSCollector(feed_config=sample_feed_config)
        entries = collector.collect()
        assert entries == []


def test_rss_collector_entry_without_link(sample_feed_config):
    """Test RSS collector skips entries without link."""
    with patch("src.collectors.rss_collector.feedparser") as mock:
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {"title": "No Link", "summary": "Test"},
            {
                "title": "With Link",
                "link": "https://example.com",
                "summary": "Test",
            },
        ]
        mock.parse.return_value = mock_feed

        collector = RSSCollector(feed_config=sample_feed_config)
        entries = collector.collect()
        assert len(entries) == 1
        # HttpUrl normalizes URLs, may add trailing slash
        assert str(entries[0].link).rstrip("/") == "https://example.com"


def test_rss_collector_date_parsing_exceptions(sample_feed_config):
    """Test RSS collector date parsing with various exceptions."""
    with patch("src.collectors.rss_collector.feedparser") as mock:
        from time import struct_time
        mock_feed = Mock()
        mock_feed.bozo = False
        entry = Mock()
        entry.get = Mock(side_effect=lambda k, d=None: {
            "title": "Test",
            "link": "https://example.com",
            "summary": "Test",
            "published": "2024-01-01T00:00:00Z",
        }.get(k, d))
        entry.published_parsed = struct_time((2024, 1, 1, 0, 0, 0, 0, 1, 0))
        mock_feed.entries = [entry]
        mock.parse.return_value = mock_feed

        collector = RSSCollector(feed_config=sample_feed_config)
        entries = collector.collect()
        assert len(entries) > 0
        assert entries[0].published is not None


def test_rss_collector_max_entries(sample_feed_config):
    """Test RSS collector respects max_entries limit."""
    with patch("src.collectors.rss_collector.feedparser") as mock:
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "title": f"Article {i}",
                "link": f"https://example.com/{i}",
                "summary": "Test",
            }
            for i in range(50)
        ]
        mock.parse.return_value = mock_feed

        collector = RSSCollector(feed_config=sample_feed_config, max_entries=10)
        entries = collector.collect()
        assert len(entries) == 10


def test_rss_collector_connection_error(sample_feed_config):
    """Test RSS collector handles connection errors."""
    with patch("src.collectors.rss_collector.feedparser") as mock:
        mock.parse.side_effect = ConnectionError("Connection failed")

        collector = RSSCollector(feed_config=sample_feed_config)
        with pytest.raises(ValueError, match="Failed to parse RSS feed"):
            collector.collect()
