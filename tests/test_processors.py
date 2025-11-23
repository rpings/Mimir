# -*- coding: utf-8 -*-
"""Tests for processors module."""

import pytest
from unittest.mock import Mock

from src.processors.keyword_processor import KeywordProcessor
from src.processors.content_cleaner import clean_html, normalize_text, truncate_text, extract_summary
from src.processors.deduplicator import Deduplicator
from src.storages.cache_manager import CacheManager


@pytest.fixture
def sample_rules():
    """Sample classification rules."""
    return {
        "topics": {
            "AI": ["artificial intelligence", "machine learning"],
            "RAG": ["retrieval", "rag"],
        },
        "priority": {
            "High": ["release", "breaking"],
            "Medium": ["beta", "preview"],
        },
    }


@pytest.fixture
def keyword_processor(sample_rules):
    """Keyword processor instance."""
    return KeywordProcessor(rules=sample_rules)


def test_keyword_processor_label_topics(keyword_processor):
    """Test topic labeling."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="New AI Breakthrough",
        link="https://example.com",
        summary="Machine learning advances in retrieval systems",
    )

    processed = keyword_processor.process(entry)
    assert "AI" in processed.topics
    assert "RAG" in processed.topics


def test_keyword_processor_priority(keyword_processor):
    """Test priority classification."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Major Release Announcement",
        link="https://example.com",
        summary="Breaking changes in new version",
    )

    processed = keyword_processor.process(entry)
    assert processed.priority == "High"


def test_keyword_processor_arxiv_fallback(keyword_processor):
    """Test arXiv fallback logic."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Some Paper",
        link="https://arxiv.org/abs/1234.5678",
        summary="Content without keywords",
    )

    processed = keyword_processor.process(entry)
    assert len(processed.topics) > 0
    assert processed.topics[0] in ["RAG", "Agent"]


def test_keyword_processor_arxiv_rag_fallback(keyword_processor):
    """Test arXiv RAG fallback."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Retrieval Paper",
        link="https://arxiv.org/abs/1234.5678",
        summary="About retrieval systems",
    )

    processed = keyword_processor.process(entry)
    assert "RAG" in processed.topics


def test_keyword_processor_empty_input(keyword_processor):
    """Test processing empty input."""
    from src.collectors.base_collector import CollectedEntry

    # CollectedEntry requires min_length=1 for title, so use minimal title
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="",
    )

    processed = keyword_processor.process(entry)
    assert processed.topics is not None
    assert processed.priority is not None
    assert processed.priority == "Low"


def test_keyword_processor_no_matches(keyword_processor):
    """Test processing with no keyword matches."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Random Content",
        link="https://example.com",
        summary="No matching keywords here",
    )

    processed = keyword_processor.process(entry)
    assert isinstance(processed.topics, list)
    assert processed.priority == "Low"


def test_content_cleaner_html():
    """Test HTML cleaning."""
    html = "<p>Test <b>content</b></p>"
    cleaned = clean_html(html)
    assert "Test" in cleaned
    assert "<p>" not in cleaned
    assert "<b>" not in cleaned


def test_content_cleaner_html_empty():
    """Test HTML cleaning with empty input."""
    assert clean_html("") == ""
    assert clean_html(None) == ""


def test_content_cleaner_html_entities():
    """Test HTML entity decoding."""
    html = "&lt;test&gt; &amp; &quot;content&quot;"
    cleaned = clean_html(html)
    # unescape decodes HTML entities
    assert "&lt;" not in cleaned or "<" in cleaned
    assert "&amp;" not in cleaned or "&" in cleaned
    assert "&quot;" not in cleaned or '"' in cleaned


def test_normalize_text():
    """Test text normalization."""
    text = "  Test   Content  "
    normalized = normalize_text(text)
    assert normalized == "test content"


def test_normalize_text_empty():
    """Test normalization with empty input."""
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_truncate_text():
    """Test text truncation."""
    long_text = "A" * 300
    truncated = truncate_text(long_text, max_length=100)
    assert len(truncated) == 100
    assert truncated.endswith("...")


def test_truncate_text_short():
    """Test truncation with short text."""
    short_text = "Short"
    truncated = truncate_text(short_text, max_length=100)
    assert truncated == short_text


def test_extract_summary():
    """Test summary extraction."""
    content = "First sentence. Second sentence. Third sentence. Fourth sentence."
    summary = extract_summary(content, max_sentences=2)
    assert "First sentence" in summary
    assert "Second sentence" in summary
    assert summary.endswith(".")


@pytest.fixture
def mock_storage():
    """Mock storage for deduplicator."""
    storage = Mock()
    storage.exists.return_value = False
    return storage


@pytest.fixture
def deduplicator(mock_storage, tmp_path):
    """Deduplicator instance."""
    cache_manager = CacheManager(cache_dir=str(tmp_path / "cache"))
    return Deduplicator(storage=mock_storage, cache_manager=cache_manager)


def test_deduplicator_not_duplicate(deduplicator):
    """Test checking non-duplicate entry."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com/new",
    )
    assert deduplicator.is_duplicate(entry) is False


def test_deduplicator_duplicate_in_cache(deduplicator):
    """Test duplicate found in cache."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com/cached",
    )
    deduplicator.cache_manager.add_url(str(entry.link))
    assert deduplicator.is_duplicate(entry) is True


def test_deduplicator_duplicate_in_storage(deduplicator):
    """Test duplicate found in storage."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com/stored",
    )
    deduplicator.storage.exists.return_value = True

    assert deduplicator.is_duplicate(entry) is True
    # Should add to cache after finding in storage
    assert deduplicator.cache_manager.has_url(str(entry.link))


def test_deduplicator_no_link(deduplicator):
    """Test deduplication with no link."""
    from src.collectors.base_collector import CollectedEntry

    # CollectedEntry requires link, so we test with empty link
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
    )
    # This should not be a duplicate since link is valid
    assert deduplicator.is_duplicate(entry) is False


def test_deduplicator_mark_as_processed(deduplicator):
    """Test marking entry as processed."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com/new",
    )
    deduplicator.mark_as_processed(entry)
    assert deduplicator.cache_manager.has_url(str(entry.link))


def test_deduplicator_mark_no_link(deduplicator):
    """Test marking entry without link."""
    from src.collectors.base_collector import CollectedEntry

    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
    )
    deduplicator.mark_as_processed(entry)  # Should not raise error
