# -*- coding: utf-8 -*-
"""Tests for storages module."""

import pytest
from unittest.mock import Mock, patch

from src.storages.cache_manager import CacheManager


@pytest.fixture
def cache_manager(tmp_path):
    """Cache manager instance with temporary directory."""
    return CacheManager(cache_dir=str(tmp_path / "cache"), ttl_days=30)


def test_cache_manager_add_url(cache_manager):
    """Test adding URL to cache."""
    url = "https://example.com/article"
    assert not cache_manager.has_url(url)

    cache_manager.add_url(url)
    assert cache_manager.has_url(url)


def test_cache_manager_url_hash(cache_manager):
    """Test URL hashing."""
    url = "https://example.com/article"
    hash1 = cache_manager.get_url_hash(url)
    hash2 = cache_manager.get_url_hash(url)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex length


def test_cache_manager_stats(cache_manager):
    """Test cache statistics."""
    cache_manager.add_url("https://example.com/1")
    cache_manager.add_url("https://example.com/2")

    stats = cache_manager.get_cache_stats()
    assert stats["total_urls"] == 2
    assert stats["ttl_days"] == 30

