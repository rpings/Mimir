# -*- coding: utf-8 -*-
"""Tests for storages module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.storages.cache_manager import CacheManager
from src.storages.notion_client import NotionStorage


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


def test_cache_manager_persistence(cache_manager):
    """Test cache persistence across instances."""
    url = "https://example.com/persistent"
    cache_manager.add_url(url)

    # Create new instance with same cache dir
    new_manager = CacheManager(
        cache_dir=cache_manager.cache_dir, ttl_days=30
    )
    assert new_manager.has_url(url)


def test_cache_manager_expired_entries(tmp_path):
    """Test expired cache entries are filtered."""
    manager = CacheManager(cache_dir=str(tmp_path / "cache"), ttl_days=1)
    url = "https://example.com/old"
    manager.add_url(url)

    # Manually set old timestamp in cache file
    import json
    from datetime import timedelta
    old_date = (datetime.now() - timedelta(days=2)).isoformat()
    with open(manager.url_cache_file, "w", encoding="utf-8") as f:
        json.dump({url: old_date}, f)

    # Reload should filter expired
    new_manager = CacheManager(
        cache_dir=str(tmp_path / "cache"), ttl_days=1
    )
    assert not new_manager.has_url(url)


def test_cache_manager_clear_expired(cache_manager):
    """Test clearing expired entries."""
    cache_manager.add_url("https://example.com/1")
    removed = cache_manager.clear_expired()
    assert removed >= 0


@pytest.fixture
def notion_storage():
    """Notion storage instance with mocked client."""
    with patch("src.storages.notion_client.Client") as mock_client:
        storage = NotionStorage(
            token="test_token",
            database_id="test_db_id",
            timezone="Asia/Shanghai",
        )
        storage.client = mock_client.return_value
        yield storage


def test_notion_storage_exists_true(notion_storage):
    """Test checking if entry exists (returns True)."""
    entry = {"link": "https://example.com/article"}

    notion_storage.client.databases.query.return_value = {
        "results": [{"id": "test_id"}]
    }

    assert notion_storage.exists(entry) is True
    notion_storage.client.databases.query.assert_called_once()


def test_notion_storage_exists_false(notion_storage):
    """Test checking if entry exists (returns False)."""
    entry = {"link": "https://example.com/article"}

    notion_storage.client.databases.query.return_value = {"results": []}

    assert notion_storage.exists(entry) is False


def test_notion_storage_exists_no_link(notion_storage):
    """Test exists check with no link."""
    entry = {"title": "Test"}
    assert notion_storage.exists(entry) is False


def test_notion_storage_exists_error(notion_storage):
    """Test exists check handles errors gracefully."""
    entry = {"link": "https://example.com/article"}

    notion_storage.client.databases.query.side_effect = Exception("API Error")

    assert notion_storage.exists(entry) is False


def test_notion_storage_save_success(notion_storage):
    """Test successful save to Notion."""
    entry = {
        "title": "Test Article",
        "link": "https://example.com/article",
        "source_type": "博客",
        "topics": ["AI", "RAG"],
        "priority": "High",
        "published": "2024-01-01T00:00:00Z",
    }

    notion_storage.client.pages.create.return_value = {"id": "test_id"}

    result = notion_storage.save(entry)
    assert result is True
    notion_storage.client.pages.create.assert_called_once()


def test_notion_storage_save_missing_fields(notion_storage):
    """Test save with missing required fields."""
    entry = {"title": "Test"}

    with pytest.raises(ValueError, match="Missing required field"):
        notion_storage.save(entry)


def test_notion_storage_save_long_title(notion_storage):
    """Test save truncates long titles."""
    long_title = "A" * 300
    entry = {
        "title": long_title,
        "link": "https://example.com",
        "source_type": "博客",
        "topics": [],
        "priority": "Low",
    }

    notion_storage.client.pages.create.return_value = {"id": "test_id"}

    notion_storage.save(entry)
    call_args = notion_storage.client.pages.create.call_args
    title_content = call_args[1]["properties"]["情报标题"]["title"][0]["text"]["content"]
    assert len(title_content) <= 200


def test_notion_storage_save_invalid_date(notion_storage):
    """Test save handles invalid date format."""
    entry = {
        "title": "Test",
        "link": "https://example.com",
        "source_type": "博客",
        "topics": [],
        "priority": "Low",
        "published": "invalid-date",
    }

    notion_storage.client.pages.create.return_value = {"id": "test_id"}

    result = notion_storage.save(entry)
    assert result is True  # Should use current date as fallback


def test_notion_storage_query(notion_storage):
    """Test querying Notion database."""
    notion_storage.client.databases.query.return_value = {
        "results": [{"id": "1"}, {"id": "2"}]
    }

    results = notion_storage.query(filter={"property": "优先级", "select": {"equals": "High"}})
    assert len(results) == 2
    notion_storage.client.databases.query.assert_called_once()


def test_notion_storage_query_error(notion_storage):
    """Test query handles errors."""
    notion_storage.client.databases.query.side_effect = Exception("API Error")

    results = notion_storage.query()
    assert results == []
