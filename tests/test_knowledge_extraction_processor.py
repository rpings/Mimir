# -*- coding: utf-8 -*-
"""Tests for KnowledgeExtractionProcessor."""

from unittest.mock import Mock

import pytest

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
from src.processors.knowledge_extraction_processor import KnowledgeExtractionProcessor
from src.processors.processing_context import ProcessingContext


@pytest.fixture
def knowledge_config():
    """Sample knowledge extraction configuration."""
    return {
        "enabled": True,
        "extract_entities": True,
        "extract_relations": True,
        "extract_key_points": True,
        "use_llm": False,
    }


@pytest.fixture
def knowledge_processor(knowledge_config):
    """KnowledgeExtractionProcessor instance."""
    return KnowledgeExtractionProcessor(config=knowledge_config)


def test_knowledge_extraction_processor_init_default():
    """Test KnowledgeExtractionProcessor initialization with defaults."""
    processor = KnowledgeExtractionProcessor()
    assert processor.enabled is True
    assert processor.extract_entities is True
    assert processor.extract_relations is True
    assert processor.extract_key_points is True
    assert processor.use_llm is False


def test_knowledge_extraction_processor_process_collected_entry(knowledge_processor):
    """Test processing CollectedEntry."""
    entry = CollectedEntry(
        title="OpenAI GPT-4 Release",
        link="https://example.com",
        summary="OpenAI introduces GPT-4, a new language model built with PyTorch. This breakthrough demonstrates state of the art performance.",
    )

    result = knowledge_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert len(result.entities) > 0
    assert isinstance(result.relations, list)
    assert len(result.key_points) > 0
    assert result.structured_summary is not None
    assert len(result.auto_tags) > 0


def test_knowledge_extraction_processor_process_short_content(knowledge_processor):
    """Test processing entry with short content."""
    entry = CollectedEntry(
        title="Test",
        link="https://example.com",
        summary="Short",  # Too short
    )

    result = knowledge_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    # Should still process but with minimal extraction
    assert isinstance(result.entities, list)
    assert isinstance(result.relations, list)


def test_knowledge_extraction_processor_extract_entities(knowledge_processor):
    """Test entity extraction."""
    content = "OpenAI uses GPT-4 with PyTorch and HuggingFace."
    entities = knowledge_processor._extract_entities(content)

    assert isinstance(entities, list)
    # Should find some entities
    assert len(entities) > 0
    for entity in entities:
        assert "type" in entity
        assert "name" in entity
        assert "context" in entity


def test_knowledge_extraction_processor_extract_relations(knowledge_processor):
    """Test relation extraction."""
    content = "OpenAI uses PyTorch for training."
    entities = [{"name": "OpenAI", "type": "organization"}]

    relations = knowledge_processor._extract_relations(content, entities)
    assert isinstance(relations, list)


def test_knowledge_extraction_processor_extract_key_points(knowledge_processor):
    """Test key point extraction."""
    content = "This paper introduces a novel approach. The method achieves state of the art results. The breakthrough demonstrates significant improvements."
    key_points = knowledge_processor._extract_key_points(content)

    assert isinstance(key_points, list)
    assert len(key_points) > 0
    assert len(key_points) <= 5  # Should be limited to 5


def test_knowledge_extraction_processor_generate_structured_summary(knowledge_processor):
    """Test structured summary generation."""
    content = "Background information. Method description. Results achieved. Significance of findings."
    summary = knowledge_processor._generate_structured_summary(content)

    assert isinstance(summary, dict)
    assert "background" in summary
    assert "method" in summary
    assert "result" in summary
    assert "significance" in summary


def test_knowledge_extraction_processor_generate_auto_tags(knowledge_processor):
    """Test auto tag generation."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        topics=["AI", "ML"],
        entities=[{"name": "GPT-4", "type": "technology"}],
    )

    tags = knowledge_processor._generate_auto_tags(entry)
    assert isinstance(tags, list)
    assert "AI" in tags or "ML" in tags
    assert len(tags) <= 10


def test_knowledge_extraction_processor_get_processor_name(knowledge_processor):
    """Test get_processor_name method."""
    assert knowledge_processor.get_processor_name() == "KnowledgeExtractionProcessor"

