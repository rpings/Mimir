# -*- coding: utf-8 -*-
"""Tests for Twitter collector module."""

import pytest
from unittest.mock import patch

from src.collectors.twitter_collector import TwitterCollector


@pytest.fixture
def sample_account_config():
    """Sample Twitter account configuration."""
    return {
        "name": "Test Account",
        "username": "testuser",
        "source_type": "social",
    }


def test_twitter_collector_init(sample_account_config):
    """Test Twitter collector initialization."""
    collector = TwitterCollector(account_config=sample_account_config)
    assert collector.get_source_name() == "Test Account"
    assert collector.account_config == sample_account_config
    assert collector.max_entries == 30


@pytest.mark.asyncio
async def test_twitter_collector_acollect_placeholder(sample_account_config):
    """Test async collection returns empty list (placeholder)."""
    collector = TwitterCollector(account_config=sample_account_config)
    entries = await collector.acollect()
    assert entries == []


def test_twitter_collector_collect_sync(sample_account_config):
    """Test synchronous collect method."""
    collector = TwitterCollector(account_config=sample_account_config)
    result = collector.collect()
    assert result == []


def test_twitter_collector_get_source_name(sample_account_config):
    """Test getting source name."""
    collector = TwitterCollector(account_config=sample_account_config)
    assert collector.get_source_name() == "Test Account"
    
    # Test default name
    collector_no_name = TwitterCollector(account_config={"username": "test"})
    assert collector_no_name.get_source_name() == "Twitter Account"

