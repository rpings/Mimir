# -*- coding: utf-8 -*-
"""Tests for collectors module."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
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


@patch("src.collectors.rss_collector.httpx.Client")
def test_rss_collector_collect_success(mock_client_class, sample_feed_config, mock_feedparser):
    """Test successful RSS feed collection."""
    from src.collectors.base_collector import CollectedEntry
    
    # Mock httpx response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<rss><channel><item><title>Test Article</title><link>https://example.com/article</link></item></channel></rss>"
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get.return_value = mock_response
    mock_client_class.return_value = mock_client
    
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


@patch("src.collectors.rss_collector.httpx.Client")
def test_rss_collector_bozo_warning(mock_client_class, sample_feed_config):
    """Test RSS collector handles parsing warnings."""
    # Mock httpx response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<rss><channel><item><title>Test</title><link>https://example.com</link></item></channel></rss>"
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get.return_value = mock_response
    mock_client_class.return_value = mock_client
    
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


@patch("src.collectors.rss_collector.httpx.Client")
def test_rss_collector_empty_entries(mock_client_class, sample_feed_config):
    """Test RSS collector with empty feed."""
    # Mock httpx response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<rss><channel></channel></rss>"
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get.return_value = mock_response
    mock_client_class.return_value = mock_client
    
    with patch("src.collectors.rss_collector.feedparser") as mock:
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock.parse.return_value = mock_feed

        collector = RSSCollector(feed_config=sample_feed_config)
        entries = collector.collect()
        assert entries == []


@patch("src.collectors.rss_collector.httpx.Client")
def test_rss_collector_entry_without_link(mock_client_class, sample_feed_config):
    """Test RSS collector skips entries without link."""
    # Mock httpx response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<rss><channel><item><title>No Link</title></item><item><title>With Link</title><link>https://example.com</link></item></channel></rss>"
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get.return_value = mock_response
    mock_client_class.return_value = mock_client
    
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


@patch("src.collectors.rss_collector.httpx.Client")
def test_rss_collector_date_parsing_exceptions(mock_client_class, sample_feed_config):
    """Test RSS collector date parsing with various exceptions."""
    # Mock httpx response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<rss><channel><item><title>Test</title><link>https://example.com</link><pubDate>2024-01-01T00:00:00Z</pubDate></item></channel></rss>"
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get.return_value = mock_response
    mock_client_class.return_value = mock_client
    
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


@patch("src.collectors.rss_collector.httpx.Client")
def test_rss_collector_max_entries(mock_client_class, sample_feed_config):
    """Test RSS collector respects max_entries limit."""
    # Mock httpx response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<rss><channel>" + "".join([f"<item><title>Article {i}</title><link>https://example.com/{i}</link></item>" for i in range(50)]) + "</channel></rss>"
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get.return_value = mock_response
    mock_client_class.return_value = mock_client
    
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


@patch("src.collectors.rss_collector.httpx.Client")
def test_rss_collector_connection_error(mock_client_class, sample_feed_config):
    """Test RSS collector handles connection errors."""
    import httpx
    
    # Mock client to raise ConnectError
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get.side_effect = httpx.ConnectError("Connection failed")
    mock_client_class.return_value = mock_client

    collector = RSSCollector(feed_config=sample_feed_config)
    with pytest.raises(ValueError, match="Failed to fetch RSS feed"):
        collector.collect()


@pytest.mark.asyncio
async def test_rss_collector_acollect_success(sample_feed_config):
    """Test successful async RSS collection."""
    with patch("src.collectors.rss_collector.httpx.AsyncClient") as mock_client:
        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.text = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Test Article</title>
      <link>https://example.com/article</link>
      <description>Test summary</description>
    </item>
  </channel>
</rss>"""
        mock_response.raise_for_status = Mock()
        
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        collector = RSSCollector(feed_config=sample_feed_config)
        
        with patch("src.collectors.rss_collector.feedparser") as mock_feedparser:
            mock_feed = Mock()
            mock_feed.bozo = False
            mock_entry = Mock()
            mock_entry.get = Mock(side_effect=lambda k, d=None: {
                "title": "Test Article",
                "link": "https://example.com/article",
                "summary": "Test summary",
            }.get(k, d))
            mock_entry.published_parsed = None
            mock_feed.entries = [mock_entry]
            mock_feedparser.parse.return_value = mock_feed
            
            entries = await collector.acollect()
            
            assert len(entries) == 1
            assert entries[0].title == "Test Article"


@pytest.mark.asyncio
async def test_rss_collector_acollect_http_error(sample_feed_config):
    """Test async collection handles HTTP errors."""
    with patch("src.collectors.rss_collector.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_get = AsyncMock()
        mock_get.side_effect = Exception("HTTP Error")
        mock_client_instance.__aenter__.return_value.get = mock_get
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        collector = RSSCollector(feed_config=sample_feed_config)
        
        with pytest.raises(ValueError, match="Failed to"):
            await collector.acollect()
