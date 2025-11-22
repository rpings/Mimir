# -*- coding: utf-8 -*-
"""Tests for collectors module."""

import pytest
from unittest.mock import Mock, patch

from src.collectors.rss_collector import RSSCollector


@pytest.fixture
def sample_feed_config():
    """Sample RSS feed configuration."""
    return {
        "name": "Test Feed",
        "url": "https://example.com/rss",
        "source_type": "博客",
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
    collector = RSSCollector(feed_config=sample_feed_config)
    entries = collector.collect()

    assert isinstance(entries, list)
    assert len(entries) > 0
    assert entries[0]["title"] == "Test Article"
    assert entries[0]["link"] == "https://example.com/article"


def test_rss_collector_missing_url():
    """Test RSS collector with missing URL."""
    collector = RSSCollector(feed_config={"name": "Test"})
    with pytest.raises(ValueError, match="Feed URL is required"):
        collector.collect()

