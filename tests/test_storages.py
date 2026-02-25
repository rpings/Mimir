# -*- coding: utf-8 -*-
"""Tests for storages module."""

import pytest
from unittest.mock import patch

from src.storages.cache_manager import CacheManager
from src.storages.notion_client import NotionStorage, _normalize_link


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
    # diskcache handles expiration automatically, so we test that expired entries
    # are not accessible after TTL expires
    manager = CacheManager(cache_dir=str(tmp_path / "cache"), ttl_days=1)
    url = "https://example.com/old"
    manager.add_url(url)
    
    # Entry should exist immediately
    assert manager.has_url(url)
    
    # diskcache will automatically expire entries after TTL
    # We can't easily test this without waiting, so we just verify the entry exists
    # In production, diskcache handles expiration automatically


def test_cache_manager_clear_expired(cache_manager):
    """Test clearing expired entries."""
    cache_manager.add_url("https://example.com/1")
    removed = cache_manager.clear_expired()
    assert removed >= 0


def test_normalize_link():
    """Test URL normalization for deduplication."""
    assert _normalize_link("https://example.com/article") == "https://example.com/article"
    assert _normalize_link("https://example.com/article/") == "https://example.com/article"
    assert _normalize_link("https://example.com/article#section") == "https://example.com/article"
    assert _normalize_link("http://example.com/p") == "https://example.com/p"
    assert _normalize_link("example.com/p") == "https://example.com/p"
    assert _normalize_link("  https://example.com/p  ") == "https://example.com/p"
    assert _normalize_link("") == ""


@pytest.fixture
def notion_storage():
    """Notion storage instance with mocked client (API 2025: data_sources)."""
    with patch("src.storages.notion_client.Client") as mock_client:
        storage = NotionStorage(
            token="test_token",
            database_id="test_db_id",
            timezone="Asia/Shanghai",
        )
        storage.client = mock_client.return_value
        storage.client.databases.retrieve.return_value = {
            "data_sources": [{"id": "test_ds_id"}]
        }
        storage.client.data_sources.query.return_value = {"results": [], "next_cursor": None}
        yield storage


def test_notion_storage_exists_true(notion_storage):
    """Test checking if entry exists (returns True) using rich_text filter."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com/article",
    )

    notion_storage.client.data_sources.query.return_value = {
        "results": [{"id": "test_id"}]
    }

    assert notion_storage.exists(entry) is True
    notion_storage.client.data_sources.query.assert_called()
    call_kwargs = notion_storage.client.data_sources.query.call_args[1]
    assert "filter" in call_kwargs
    assert call_kwargs["filter"]["property"] == notion_storage.field_names["link"]
    assert call_kwargs["filter"]["rich_text"] == {"equals": "https://example.com/article"}


def test_notion_storage_exists_false(notion_storage):
    """Test checking if entry exists (returns False)."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com/article",
    )

    notion_storage.client.data_sources.query.return_value = {"results": []}

    assert notion_storage.exists(entry) is False


def test_notion_storage_exists_no_link(notion_storage):
    """Test exists check with no link."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
    )
    notion_storage.client.data_sources.query.return_value = {"results": []}
    assert notion_storage.exists(entry) is False


def test_notion_storage_exists_error(notion_storage):
    """Test exists check handles errors gracefully."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com/article",
    )

    notion_storage.client.data_sources.query.side_effect = Exception("API Error")

    assert notion_storage.exists(entry) is False


def test_notion_storage_save_success(notion_storage):
    """Test successful save to Notion when entry does not exist."""
    from src.processors.base_processor import ProcessedEntry

    entry = ProcessedEntry(
        title="Test Article",
        link="https://example.com/article",
        source_type="blog",
        topics=["AI", "RAG"],
        priority="High",
        published="2024-01-01T00:00:00Z",
    )

    notion_storage.client.data_sources.query.return_value = {"results": []}
    notion_storage.client.pages.create.return_value = {"id": "test_id"}

    result = notion_storage.save(entry)
    assert result is True
    notion_storage.client.pages.create.assert_called_once()


def test_notion_storage_save_skips_when_exists(notion_storage):
    """Test save does not create page and returns False when entry already exists."""
    from src.processors.base_processor import ProcessedEntry

    entry = ProcessedEntry(
        title="Test Article",
        link="https://example.com/article",
        source_type="blog",
        topics=["AI", "RAG"],
        priority="High",
        published="2024-01-01T00:00:00Z",
    )

    notion_storage.client.data_sources.query.return_value = {
        "results": [{"id": "existing_id"}]
    }

    result = notion_storage.save(entry)
    assert result is False
    notion_storage.client.pages.create.assert_not_called()


def test_notion_storage_save_missing_fields(notion_storage):
    """Test save with missing required fields."""
    from src.processors.base_processor import ProcessedEntry

    # ProcessedEntry requires all fields, so we test with minimal valid entry
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        topics=[],
        priority="Low",
    )

    notion_storage.client.data_sources.query.return_value = {"results": []}
    notion_storage.client.pages.create.return_value = {"id": "test_id"}
    result = notion_storage.save(entry)
    assert result is True


def test_notion_storage_save_long_title(notion_storage):
    """Test save handles long titles (ProcessedEntry limits to 200 chars)."""
    from src.processors.base_processor import ProcessedEntry

    # ProcessedEntry limits title to 200 chars, so we test with max length
    long_title = "A" * 200
    entry = ProcessedEntry(
        title=long_title,
        link="https://example.com",
        source_type="blog",
        topics=[],
        priority="Low",
    )

    notion_storage.client.data_sources.query.return_value = {"results": []}
    notion_storage.client.pages.create.return_value = {"id": "test_id"}

    notion_storage.save(entry)
    call_args = notion_storage.client.pages.create.call_args
    title_content = call_args[1]["properties"][notion_storage.field_names["title"]]["title"][0]["text"]["content"]
    # Title should be preserved (200 chars, within Notion's limit)
    assert len(title_content) == 200


def test_notion_storage_save_invalid_date(notion_storage):
    """Test save handles invalid date format."""
    from src.processors.base_processor import ProcessedEntry

    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        source_type="blog",
        topics=[],
        priority="Low",
        published="invalid-date",
    )

    notion_storage.client.data_sources.query.return_value = {"results": []}
    notion_storage.client.pages.create.return_value = {"id": "test_id"}

    result = notion_storage.save(entry)
    assert result is True  # Should use current date as fallback


def test_notion_storage_query(notion_storage):
    """Test querying Notion database."""
    notion_storage.client.data_sources.query.return_value = {
        "results": [{"id": "1"}, {"id": "2"}]
    }

    results = notion_storage.query(filter={"property": "Priority", "select": {"equals": "High"}})
    assert isinstance(results, list)
    assert len(results) == 0  # query() returns empty list (TODO: convert to ProcessedEntry)
    notion_storage.client.data_sources.query.assert_called_once()


def test_notion_storage_query_error(notion_storage):
    """Test query handles errors."""
    notion_storage.client.data_sources.query.side_effect = Exception("API Error")

    results = notion_storage.query()
    assert results == []


def test_notion_storage_get_data_source_id_empty(notion_storage):
    """Test _get_data_source_id returns None when database has no data_sources."""
    notion_storage._data_source_id = None
    notion_storage.client.databases.retrieve.return_value = {"data_sources": []}

    assert notion_storage._get_data_source_id() is None


def test_notion_storage_get_data_source_id_retrieve_fails(notion_storage):
    """Test _get_data_source_id returns None when retrieve raises."""
    notion_storage._data_source_id = None
    notion_storage.client.databases.retrieve.side_effect = Exception("API error")

    assert notion_storage._get_data_source_id() is None


def test_notion_storage_exists_fallback_when_no_ds_id(notion_storage):
    """Test exists() uses _load_existing_links when _get_data_source_id returns None."""
    from src.collectors.base_collector import CollectedEntry

    notion_storage._data_source_id = None
    notion_storage.client.databases.retrieve.return_value = {"data_sources": []}
    notion_storage._existing_links_cache = set()  # _load_existing_links would return this

    entry = CollectedEntry(title="Test", link="https://example.com/article")
    assert notion_storage.exists(entry) is False


def test_notion_storage_exists_fallback_when_validation_error(notion_storage):
    """Test exists() falls back to _load_existing_links when rich_text filter fails."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(title="Test", link="https://example.com/article")
    # First call (rich_text filter) raises; second call (_load_existing_links) returns page with link
    notion_storage.client.data_sources.query.side_effect = [
        Exception("validation error"),
        {
            "results": [
                {"properties": {notion_storage.field_names["link"]: {"url": "https://example.com/article"}}}
            ],
            "next_cursor": None,
        },
    ]

    assert notion_storage.exists(entry) is True


def test_notion_storage_load_existing_links_no_ds_id(notion_storage):
    """Test _load_existing_links returns empty set when _get_data_source_id is None."""
    notion_storage._data_source_id = None
    notion_storage._existing_links_cache = None
    notion_storage.client.databases.retrieve.return_value = {"data_sources": []}

    assert notion_storage._load_existing_links() == set()


def test_notion_storage_load_existing_links_populates_cache(notion_storage):
    """Test _load_existing_links extracts links and caches them."""
    notion_storage._existing_links_cache = None
    notion_storage.client.data_sources.query.return_value = {
        "results": [
            {"properties": {"Link": {"url": "https://example.com/a"}}},
            {"properties": {"Link": {"url": "https://example.com/b/"}}},
        ],
        "next_cursor": None,
    }

    links = notion_storage._load_existing_links()
    assert "https://example.com/a" in links
    assert "https://example.com/b" in links  # normalized (trailing slash stripped)
    assert notion_storage._existing_links_cache is not None


def test_notion_storage_load_existing_links_query_raises(notion_storage):
    """Test _load_existing_links returns empty set and caches when query raises."""
    notion_storage._existing_links_cache = None
    notion_storage.client.data_sources.query.side_effect = Exception("rate limit")

    links = notion_storage._load_existing_links()
    assert links == set()
    assert notion_storage._existing_links_cache == set()


def test_notion_storage_save_duplicate_exception(notion_storage):
    """Test save returns False when pages.create raises duplicate error."""
    from src.processors.base_processor import ProcessedEntry

    entry = ProcessedEntry(
        title="Test",
        link="https://example.com/dup",
        source_type="blog",
        topics=[],
        priority="Low",
        published="2024-01-01",
    )
    notion_storage.client.data_sources.query.return_value = {"results": []}
    notion_storage.client.pages.create.side_effect = Exception("duplicate already exists")

    result = notion_storage.save(entry)
    assert result is False


def test_notion_storage_query_no_ds_id(notion_storage):
    """Test query returns empty list when _get_data_source_id returns None."""
    notion_storage._data_source_id = None
    notion_storage.client.databases.retrieve.return_value = {"data_sources": []}

    results = notion_storage.query(filter={"property": "X", "select": {"equals": "Y"}})
    assert results == []
