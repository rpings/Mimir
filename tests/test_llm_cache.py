# -*- coding: utf-8 -*-
"""Tests for LLM cache module."""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.storages.llm_cache import LLMCache


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def llm_cache(temp_cache_dir):
    """LLM cache instance with temporary directory."""
    return LLMCache(cache_dir=temp_cache_dir, ttl_days=1)


def test_llm_cache_init_default():
    """Test LLM cache initialization with default directory."""
    cache = LLMCache()
    assert cache.cache_dir.exists()
    assert cache.ttl_days == 30
    assert cache.ttl_seconds == 30 * 24 * 60 * 60


def test_llm_cache_init_custom(temp_cache_dir):
    """Test LLM cache initialization with custom directory."""
    cache = LLMCache(cache_dir=temp_cache_dir, ttl_days=7)
    assert cache.cache_dir == Path(temp_cache_dir)
    assert cache.ttl_days == 7
    assert cache.ttl_seconds == 7 * 24 * 60 * 60


def test_llm_cache_get_cache_key(llm_cache):
    """Test cache key generation."""
    key1 = llm_cache._get_cache_key("test content", "summary")
    key2 = llm_cache._get_cache_key("test content", "summary")
    key3 = llm_cache._get_cache_key("test content", "translation")
    key4 = llm_cache._get_cache_key("different content", "summary")
    
    # Same content and feature should generate same key
    assert key1 == key2
    
    # Different feature should generate different key
    assert key1 != key3
    
    # Different content should generate different key
    assert key1 != key4
    
    # Key should be a valid SHA256 hash (64 hex characters)
    assert len(key1) == 64
    assert all(c in '0123456789abcdef' for c in key1)


def test_llm_cache_get_miss(llm_cache):
    """Test cache get on miss."""
    result = llm_cache.get("test content", "summary")
    assert result is None


def test_llm_cache_set_and_get(llm_cache):
    """Test cache set and get."""
    content = "test content"
    feature_type = "summary"
    cached_result = "This is a summary"
    
    # Set cache
    llm_cache.set(content, feature_type, cached_result)
    
    # Get cache
    result = llm_cache.get(content, feature_type)
    assert result == cached_result


def test_llm_cache_get_different_content(llm_cache):
    """Test cache get with different content."""
    llm_cache.set("content 1", "summary", "result 1")
    
    # Different content should return None
    result = llm_cache.get("content 2", "summary")
    assert result is None


def test_llm_cache_get_different_feature(llm_cache):
    """Test cache get with different feature type."""
    llm_cache.set("test content", "summary", "summary result")
    
    # Different feature type should return None
    result = llm_cache.get("test content", "translation")
    assert result is None


def test_llm_cache_empty_string(llm_cache):
    """Test cache with empty string content."""
    llm_cache.set("", "summary", "empty result")
    result = llm_cache.get("", "summary")
    assert result == "empty result"


def test_llm_cache_special_characters(llm_cache):
    """Test cache with special characters."""
    content = "测试内容 with émojis 🚀 and <tags>"
    result_text = "Special result"
    
    llm_cache.set(content, "summary", result_text)
    cached = llm_cache.get(content, "summary")
    assert cached == result_text


def test_llm_cache_long_content(llm_cache):
    """Test cache with very long content."""
    long_content = "A" * 10000
    result_text = "Long content result"
    
    llm_cache.set(long_content, "summary", result_text)
    cached = llm_cache.get(long_content, "summary")
    assert cached == result_text


def test_llm_cache_unicode_content(llm_cache):
    """Test cache with Unicode content."""
    unicode_content = "中文内容 日本語 한국어 العربية"
    result_text = "Unicode result"
    
    llm_cache.set(unicode_content, "summary", result_text)
    cached = llm_cache.get(unicode_content, "summary")
    assert cached == result_text


def test_llm_cache_clear(llm_cache):
    """Test cache clear."""
    # Add some entries
    llm_cache.set("content 1", "summary", "result 1")
    llm_cache.set("content 2", "translation", "result 2")
    
    # Verify entries exist
    assert llm_cache.get("content 1", "summary") == "result 1"
    assert llm_cache.get("content 2", "translation") == "result 2"
    
    # Clear cache
    llm_cache.clear()
    
    # Verify entries are gone
    assert llm_cache.get("content 1", "summary") is None
    assert llm_cache.get("content 2", "translation") is None


def test_llm_cache_get_stats(llm_cache):
    """Test cache statistics."""
    stats = llm_cache.get_stats()
    assert "total_entries" in stats
    assert "ttl_days" in stats
    assert stats["ttl_days"] == 1
    
    # Add entries and check stats
    llm_cache.set("content 1", "summary", "result 1")
    llm_cache.set("content 2", "translation", "result 2")
    
    stats = llm_cache.get_stats()
    assert stats["total_entries"] >= 2


def test_llm_cache_multiple_features(llm_cache):
    """Test cache with multiple feature types."""
    content = "same content"
    
    llm_cache.set(content, "summary", "summary result")
    llm_cache.set(content, "translation", "translation result")
    llm_cache.set(content, "categorization", "categorization result")
    
    assert llm_cache.get(content, "summary") == "summary result"
    assert llm_cache.get(content, "translation") == "translation result"
    assert llm_cache.get(content, "categorization") == "categorization result"


def test_llm_cache_overwrite(llm_cache):
    """Test cache overwrite behavior."""
    content = "test content"
    feature_type = "summary"
    
    # Set initial value
    llm_cache.set(content, feature_type, "initial result")
    assert llm_cache.get(content, feature_type) == "initial result"
    
    # Overwrite with new value
    llm_cache.set(content, feature_type, "updated result")
    assert llm_cache.get(content, feature_type) == "updated result"

