# -*- coding: utf-8 -*-
"""Tests for processors module."""

import pytest

from src.processors.keyword_processor import KeywordProcessor
from src.processors.content_cleaner import clean_html, normalize_text


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
    entry = {
        "title": "New AI Breakthrough",
        "summary": "Machine learning advances in retrieval systems",
        "link": "https://example.com",
    }

    processed = keyword_processor.process(entry)
    assert "AI" in processed["topics"]
    assert "RAG" in processed["topics"]


def test_keyword_processor_priority(keyword_processor):
    """Test priority classification."""
    entry = {
        "title": "Major Release Announcement",
        "summary": "Breaking changes in new version",
        "link": "https://example.com",
    }

    processed = keyword_processor.process(entry)
    assert processed["priority"] == "High"


def test_content_cleaner_html():
    """Test HTML cleaning."""
    html = "<p>Test <b>content</b></p>"
    cleaned = clean_html(html)
    assert "Test" in cleaned
    assert "<p>" not in cleaned
    assert "<b>" not in cleaned


def test_normalize_text():
    """Test text normalization."""
    text = "  Test   Content  "
    normalized = normalize_text(text)
    assert normalized == "test content"

