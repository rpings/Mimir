# -*- coding: utf-8 -*-
"""Tests for YouTube collector module."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from src.collectors.youtube_collector import YouTubeCollector


@pytest.fixture
def sample_channel_config():
    """Sample YouTube channel configuration."""
    return {
        "name": "Test Channel",
        "channel_id": "UCtest123",
        "source_type": "video",
    }


@pytest.fixture
def sample_channel_config_username():
    """Sample YouTube channel configuration with username."""
    return {
        "name": "Test Channel",
        "username": "testuser",
        "source_type": "video",
    }


def test_youtube_collector_init(sample_channel_config):
    """Test YouTube collector initialization."""
    collector = YouTubeCollector(channel_config=sample_channel_config)
    assert collector.get_source_name() == "Test Channel"
    assert collector.channel_config == sample_channel_config
    assert collector.max_entries == 30


def test_youtube_collector_get_rss_url_channel_id(sample_channel_config):
    """Test RSS URL generation with channel_id."""
    collector = YouTubeCollector(channel_config=sample_channel_config)
    url = collector._get_rss_url()
    assert "channel_id=UCtest123" in url
    assert url.startswith("https://www.youtube.com/feeds/videos.xml")


def test_youtube_collector_get_rss_url_username(sample_channel_config_username):
    """Test RSS URL generation with username."""
    collector = YouTubeCollector(channel_config=sample_channel_config_username)
    url = collector._get_rss_url()
    assert "user=testuser" in url
    assert url.startswith("https://www.youtube.com/feeds/videos.xml")


def test_youtube_collector_get_rss_url_no_config():
    """Test RSS URL generation fails without channel_id or username."""
    collector = YouTubeCollector(channel_config={"name": "Test"})
    with pytest.raises(ValueError, match="Either 'channel_id' or 'username' must be provided"):
        collector._get_rss_url()


@pytest.mark.asyncio
async def test_youtube_collector_acollect_success(sample_channel_config):
    """Test successful async collection from YouTube."""
    with patch("src.collectors.youtube_collector.httpx.AsyncClient") as mock_client:
        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <entry>
    <title>Test Video</title>
    <link href="https://www.youtube.com/watch?v=test123"/>
    <summary>Test video description</summary>
    <published>2024-01-01T00:00:00+00:00</published>
  </entry>
</feed>"""
        mock_response.raise_for_status = Mock()
        
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        collector = YouTubeCollector(channel_config=sample_channel_config)
        
        import feedparser
        with patch.object(feedparser, "parse") as mock_feedparser:
            mock_feed = Mock()
            mock_feed.bozo = False
            mock_entry = Mock()
            mock_entry.get = Mock(side_effect=lambda k, d=None: {
                "title": "Test Video",
                "link": "https://www.youtube.com/watch?v=test123",
                "summary": "Test video description",
                "published": "2024-01-01T00:00:00+00:00",
            }.get(k, d))
            mock_entry.published_parsed = None
            mock_feed.entries = [mock_entry]
            mock_feedparser.return_value = mock_feed
            
            entries = await collector.acollect()
            
            assert len(entries) == 1
            assert entries[0].title == "Test Video"
            assert "test123" in str(entries[0].link)


@pytest.mark.asyncio
async def test_youtube_collector_acollect_http_error(sample_channel_config):
    """Test async collection handles HTTP errors."""
    with patch("src.collectors.youtube_collector.httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_get = AsyncMock()
        mock_get.side_effect = Exception("HTTP Error")
        mock_client_instance.__aenter__.return_value.get = mock_get
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance
        
        collector = YouTubeCollector(channel_config=sample_channel_config)
        
        with pytest.raises(ValueError, match="Failed to"):
            await collector.acollect()


def test_youtube_collector_collect_sync(sample_channel_config):
    """Test synchronous collect method."""
    with patch("src.collectors.youtube_collector.YouTubeCollector.acollect") as mock_acollect:
        mock_acollect.return_value = []
        collector = YouTubeCollector(channel_config=sample_channel_config)
        result = collector.collect()
        assert result == []
        mock_acollect.assert_called_once()


def test_youtube_collector_process_entry(sample_channel_config):
    """Test processing a YouTube entry."""
    collector = YouTubeCollector(channel_config=sample_channel_config)
    
    entry = Mock()
    entry.get = Mock(side_effect=lambda k, d=None: {
        "title": "Test Video",
        "link": "https://www.youtube.com/watch?v=test123",
        "summary": "<p>Test description</p>",
        "published": "2024-01-01T00:00:00+00:00",
    }.get(k, d))
    entry.published_parsed = None
    
    processed = collector._process_entry(entry)
    
    assert processed is not None
    assert processed.title == "Test Video"
    assert "test123" in str(processed.link)
    assert "Test description" in processed.summary
    assert "<p>" not in processed.summary  # HTML should be removed


def test_youtube_collector_process_entry_no_link(sample_channel_config):
    """Test processing entry without link returns None."""
    collector = YouTubeCollector(channel_config=sample_channel_config)
    
    entry = Mock()
    entry.get = Mock(return_value=None)
    
    processed = collector._process_entry(entry)
    assert processed is None


def test_youtube_collector_process_entry_with_date_parsed(sample_channel_config):
    """Test processing entry with published_parsed."""
    from time import struct_time
    
    collector = YouTubeCollector(channel_config=sample_channel_config)
    
    entry = Mock()
    entry.get = Mock(side_effect=lambda k, d=None: {
        "title": "Test Video",
        "link": "https://www.youtube.com/watch?v=test123",
        "summary": "Test",
    }.get(k, d))
    entry.published_parsed = struct_time((2024, 1, 1, 0, 0, 0, 0, 1, 0))
    
    processed = collector._process_entry(entry)
    
    assert processed is not None
    assert processed.published is not None


def test_youtube_collector_get_source_name(sample_channel_config):
    """Test getting source name."""
    collector = YouTubeCollector(channel_config=sample_channel_config)
    assert collector.get_source_name() == "Test Channel"
    
    # Test default name
    collector_no_name = YouTubeCollector(channel_config={"channel_id": "test"})
    assert collector_no_name.get_source_name() == "YouTube Channel"

