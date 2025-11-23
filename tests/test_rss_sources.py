# -*- coding: utf-8 -*-
"""Tests for RSS source configurations - validate all configured sources."""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from src.utils.config_loader import ConfigLoader
from src.collectors.rss_collector import RSSCollector


@pytest.fixture
def config_loader():
    """Config loader instance."""
    return ConfigLoader()


@pytest.fixture
def rss_sources(config_loader):
    """Load all configured RSS sources."""
    return config_loader.get_rss_sources()


def test_all_rss_sources_loaded(rss_sources):
    """Test that all RSS sources are loaded from configuration."""
    assert len(rss_sources) > 0
    assert all("name" in source for source in rss_sources)
    assert all("url" in source for source in rss_sources)
    assert all("source_type" in source for source in rss_sources)


def test_rss_source_has_required_fields(rss_sources):
    """Test that each RSS source has all required fields."""
    for source in rss_sources:
        assert "name" in source, f"Source missing 'name': {source}"
        assert "url" in source, f"Source missing 'url': {source.get('name', 'Unknown')}"
        assert "source_type" in source, f"Source missing 'source_type': {source.get('name', 'Unknown')}"
        assert source["name"], f"Source has empty 'name': {source}"
        assert source["url"], f"Source has empty 'url': {source.get('name', 'Unknown')}"
        assert source["source_type"], f"Source has empty 'source_type': {source.get('name', 'Unknown')}"


def test_rss_source_urls_valid_format(rss_sources):
    """Test that all RSS source URLs are in valid format."""
    for source in rss_sources:
        url = source["url"]
        assert url.startswith("http://") or url.startswith("https://"), \
            f"Invalid URL format for {source.get('name', 'Unknown')}: {url}"


@pytest.mark.parametrize("source_name,expected_type", [
    ("arXiv cs.CL", "论文"),
    ("arXiv cs.LG", "论文"),
    ("arXiv cs.AI", "论文"),
    ("arXiv cs.CV", "论文"),
    ("OpenAI Blog", "博客"),
    ("OpenAI API Changelog", "官方文档"),
    ("Google DeepMind Blog", "博客"),
    ("Anthropic Blog", "博客"),
    ("Meta AI Blog", "博客"),
    ("Microsoft Research Blog", "博客"),
    ("LangChain Releases", "代码"),
    ("LangGraph Releases", "代码"),
    ("LlamaIndex Releases", "代码"),
    ("DSPy Releases", "代码"),
    ("vLLM Releases", "代码"),
    ("FAISS Releases", "代码"),
    ("Hugging Face Transformers Releases", "代码"),
    ("Text-Embedding Models (sentence-transformers) Releases", "代码"),
    ("Hugging Face Open LLM Leaderboard", "官方文档"),
    ("MTEB Updates", "代码"),
    ("机器之心", "新闻"),
    ("量子位", "新闻"),
    ("AI 前线（InfoQ）", "新闻"),
])
def test_rss_source_type_mapping(rss_sources, source_name, expected_type):
    """Test that each RSS source has correct source_type mapping."""
    source = next((s for s in rss_sources if s["name"] == source_name), None)
    assert source is not None, f"Source '{source_name}' not found in configuration"
    assert source["source_type"] == expected_type, \
        f"Source '{source_name}' has incorrect source_type: expected '{expected_type}', got '{source['source_type']}'"


def test_arxiv_sources(rss_sources):
    """Test arXiv sources configuration."""
    arxiv_sources = [s for s in rss_sources if "arXiv" in s["name"]]
    assert len(arxiv_sources) >= 4, "Should have at least 4 arXiv sources"
    
    for source in arxiv_sources:
        assert "arxiv.org" in source["url"], f"ArXiv source URL should contain arxiv.org: {source['url']}"
        assert source["source_type"] == "论文", f"ArXiv source should have source_type '论文': {source['name']}"


def test_blog_sources(rss_sources):
    """Test blog sources configuration."""
    blog_sources = [s for s in rss_sources if s["source_type"] == "博客"]
    assert len(blog_sources) >= 5, "Should have at least 5 blog sources"
    
    expected_blogs = ["OpenAI Blog", "Google DeepMind Blog", "Anthropic Blog", "Meta AI Blog", "Microsoft Research Blog"]
    blog_names = [s["name"] for s in blog_sources]
    for expected in expected_blogs:
        assert expected in blog_names, f"Expected blog source '{expected}' not found"


def test_code_sources(rss_sources):
    """Test code/release sources configuration."""
    code_sources = [s for s in rss_sources if s["source_type"] == "代码"]
    assert len(code_sources) >= 8, "Should have at least 8 code sources"
    
    # Check for GitHub releases (should be .atom format)
    github_sources = [s for s in code_sources if "github.com" in s["url"]]
    for source in github_sources:
        assert ".atom" in source["url"] or "releases" in source["url"], \
            f"GitHub release source should use .atom format: {source['url']}"


def test_chinese_media_sources(rss_sources):
    """Test Chinese media sources configuration."""
    chinese_sources = [s for s in rss_sources if s["source_type"] == "新闻"]
    assert len(chinese_sources) >= 3, "Should have at least 3 Chinese media sources"
    
    expected_sources = ["机器之心", "量子位", "AI 前线（InfoQ）"]
    chinese_names = [s["name"] for s in chinese_sources]
    for expected in expected_sources:
        assert expected in chinese_names, f"Expected Chinese source '{expected}' not found"


def test_rss_collector_for_each_source(rss_sources):
    """Test that RSSCollector can be initialized for each configured source."""
    with patch("src.collectors.rss_collector.feedparser") as mock_feedparser:
        # Mock feedparser response
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_entry = Mock()
        mock_entry.get = Mock(side_effect=lambda k, d=None: {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "Test summary",
            "published": "2024-01-01T00:00:00Z",
        }.get(k, d))
        mock_entry.published_parsed = None
        mock_feed.entries = [mock_entry]
        mock_feedparser.parse.return_value = mock_feed
        
        for source in rss_sources:
            collector = RSSCollector(feed_config=source)
            assert collector.get_source_name() == source["name"]
            assert collector.feed_config == source
            
            # Test collection (should not raise exception)
            entries = collector.collect()
            assert isinstance(entries, list)


def test_rss_source_urls_unique(rss_sources):
    """Test that all RSS source URLs are unique."""
    urls = [source["url"] for source in rss_sources]
    unique_urls = set(urls)
    assert len(urls) == len(unique_urls), \
        f"Duplicate URLs found: {[url for url in urls if urls.count(url) > 1]}"


def test_rss_source_names_unique(rss_sources):
    """Test that all RSS source names are unique."""
    names = [source["name"] for source in rss_sources]
    unique_names = set(names)
    assert len(names) == len(unique_names), \
        f"Duplicate names found: {[name for name in names if names.count(name) > 1]}"


def test_rss_source_types_valid(rss_sources):
    """Test that all source types are from valid set."""
    valid_types = {"论文", "博客", "官方文档", "代码", "新闻"}
    for source in rss_sources:
        assert source["source_type"] in valid_types, \
            f"Invalid source_type '{source['source_type']}' for source '{source.get('name', 'Unknown')}'"


def test_rss_collector_source_type_preserved(rss_sources):
    """Test that source_type is preserved in collected entries."""
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
        
        # Test a few different source types
        test_sources = [
            s for s in rss_sources 
            if s["source_type"] in ["论文", "博客", "代码"]
        ][:3]
        
        for source in test_sources:
            collector = RSSCollector(feed_config=source)
            entries = collector.collect()
            if entries:
                assert entries[0].source_type == source["source_type"], \
                    f"Source type not preserved for {source['name']}"

