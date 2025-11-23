# -*- coding: utf-8 -*-
"""Tests for processor pipeline."""

from unittest.mock import Mock

import pytest

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import BaseProcessor, ProcessedEntry
from src.processors.keyword_processor import KeywordProcessor
from src.processors.processor_pipeline import ProcessorPipeline, SkipMarker
from src.processors.processing_context import ProcessingContext

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def sample_rules():
    """Sample classification rules."""
    return {
        "topics": {
            "AI": ["artificial intelligence", "machine learning"],
        },
        "priority": {
            "High": ["release", "breaking"],
        },
    }


@pytest.fixture
def keyword_processor(sample_rules):
    """Keyword processor instance."""
    return KeywordProcessor(rules=sample_rules)


def test_processor_pipeline_single_processor(keyword_processor):
    """Test pipeline with single processor."""
    pipeline = ProcessorPipeline(processors=[keyword_processor])
    
    entry = CollectedEntry(
        title="AI Breakthrough",
        link="https://example.com",
        summary="Machine learning advances",
    )
    
    result = pipeline.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert "AI" in result.topics
    assert result.priority in ["High", "Medium", "Low"]


def test_processor_pipeline_chaining(keyword_processor):
    """Test pipeline chaining works correctly."""
    # Test that pipeline correctly chains processors
    # In practice, you'd chain different processors (e.g., keyword -> LLM)
    pipeline = ProcessorPipeline(processors=[keyword_processor])
    
    entry = CollectedEntry(
        title="Machine Learning Release",
        link="https://example.com",
        summary="Breaking changes in artificial intelligence",
    )
    
    result = pipeline.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert "AI" in result.topics  # Should match "artificial intelligence" and "machine learning"
    assert result.priority == "High"  # Should match "breaking"
    assert result.processing_method == "keyword"


def test_processor_pipeline_empty(keyword_processor):
    """Test pipeline with no processors (should pass through)."""
    pipeline = ProcessorPipeline(processors=[])
    
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
    )
    
    result = pipeline.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.title == "Test"


@pytest.mark.asyncio
async def test_processor_pipeline_async(keyword_processor):
    """Test async processing."""
    pipeline = ProcessorPipeline(processors=[keyword_processor])
    
    entry = CollectedEntry(
        title="AI Article",
        link="https://example.com",
        summary="Machine learning content",
    )
    
    result = await pipeline.aprocess(entry)
    assert isinstance(result, ProcessedEntry)
    assert "AI" in result.topics


def test_processor_pipeline_with_context(keyword_processor):
    """Test pipeline with processing context."""
    context = ProcessingContext(config={"test": "value"})
    pipeline = ProcessorPipeline(processors=[keyword_processor], context=context)
    
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test summary",
    )
    
    result = pipeline.process(entry)
    assert isinstance(result, ProcessedEntry)


def test_processor_pipeline_skip_mechanism():
    """Test pipeline skip mechanism."""
    class SkippingProcessor(BaseProcessor):
        def process(self, entry, context=None):
            return None  # Skip
        
        def get_processor_name(self):
            return "SkippingProcessor"
    
    processor = SkippingProcessor()
    pipeline = ProcessorPipeline(processors=[processor])
    
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )
    
    result = pipeline.process(entry)
    assert result is None


def test_processor_pipeline_disabled_processor(keyword_processor):
    """Test pipeline with disabled processor."""
    disabled_processor = KeywordProcessor(rules={}, config={"enabled": False})
    pipeline = ProcessorPipeline(processors=[disabled_processor, keyword_processor])
    
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )
    
    result = pipeline.process(entry)
    assert isinstance(result, ProcessedEntry)


def test_skip_marker():
    """Test SkipMarker class."""
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )
    
    marker = SkipMarker(entry)
    assert marker.entry == entry


def test_processor_pipeline_error_recovery():
    """Test pipeline error recovery."""
    class FailingProcessor(BaseProcessor):
        def process(self, entry, context=None):
            raise ValueError("Test error")
        
        def get_processor_name(self):
            return "FailingProcessor"
    
    class PassingProcessor(BaseProcessor):
        def process(self, entry, context=None):
            return ProcessedEntry.from_collected(entry)
        
        def get_processor_name(self):
            return "PassingProcessor"
    
    # Pipeline should continue even if one processor fails
    pipeline = ProcessorPipeline(processors=[FailingProcessor(), PassingProcessor()])
    
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )
    
    result = pipeline.process(entry)
    # Should still process through passing processor
    assert isinstance(result, ProcessedEntry)

