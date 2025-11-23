# -*- coding: utf-8 -*-
"""Tests for QualityAssessmentProcessor."""

from unittest.mock import Mock

import pytest

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
from src.processors.processing_context import ProcessingContext
from src.processors.quality_assessment_processor import QualityAssessmentProcessor


@pytest.fixture
def quality_config():
    """Sample quality configuration."""
    return {
        "enabled": True,
        "min_quality_score": 0.3,
        "source_whitelist": ["arxiv.org", "github.com"],
        "source_blacklist": [],
        "min_content_length": 50,
    }


@pytest.fixture
def quality_processor(quality_config):
    """QualityAssessmentProcessor instance."""
    return QualityAssessmentProcessor(config=quality_config)


def test_quality_assessment_processor_init_default():
    """Test QualityAssessmentProcessor initialization with defaults."""
    processor = QualityAssessmentProcessor()
    assert processor.enabled is True
    assert processor.min_quality_score == 0.3
    assert processor.source_whitelist == []
    assert processor.source_blacklist == []
    assert processor.min_content_length == 50


def test_quality_assessment_processor_process_collected_entry(quality_processor):
    """Test processing CollectedEntry."""
    entry = CollectedEntry(
        title="Test Title",
        link="https://arxiv.org/abs/1234.5678",
        summary="This is a test summary with sufficient content length.",
        published="2024-01-01T00:00:00Z",
    )

    result = quality_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.quality_scores is not None
    assert "credibility" in result.quality_scores
    assert "completeness" in result.quality_scores
    assert "relevance" in result.quality_scores
    assert "timeliness" in result.quality_scores
    assert result.quality_grade in ["A", "B", "C", "D"]
    assert 0.0 <= result.overall_quality <= 1.0


def test_quality_assessment_processor_process_low_quality(quality_processor):
    """Test processing low quality entry (should be filtered)."""
    # Use a processor with higher threshold to ensure filtering
    high_threshold_processor = QualityAssessmentProcessor(
        config={"min_quality_score": 0.5}
    )
    
    entry = CollectedEntry(
        title="T",  # Very short title
        link="https://example.com",
        summary="S",  # Very short summary
    )

    result = high_threshold_processor.process(entry)
    # Should be filtered if quality is too low
    assert result is None or result.overall_quality < high_threshold_processor.min_quality_score


def test_quality_assessment_processor_assess_credibility_whitelist(quality_processor):
    """Test credibility assessment with whitelist."""
    entry = ProcessedEntry(
        title="Test",
        link="https://arxiv.org/abs/1234.5678",
        summary="Test summary",
    )

    score = quality_processor._assess_credibility(entry)
    assert 0.0 <= score <= 1.0
    # Should be high for arxiv.org (whitelisted)
    assert score >= 0.7


def test_quality_assessment_processor_assess_credibility_blacklist():
    """Test credibility assessment with blacklist."""
    processor = QualityAssessmentProcessor(
        config={"source_blacklist": ["spam.com"]}
    )
    entry = ProcessedEntry(
        title="Test",
        link="https://spam.com/article",
        summary="Test summary",
    )

    score = processor._assess_credibility(entry)
    assert score == 0.0


def test_quality_assessment_processor_assess_completeness(quality_processor):
    """Test completeness assessment."""
    # Short content
    entry1 = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Short",
    )
    score1 = quality_processor._assess_completeness(entry1)
    assert 0.0 <= score1 <= 1.0

    # Long content
    entry2 = ProcessedEntry(
        title="Test Title",
        link="https://example.com",
        summary="A" * 500,
        cleaned_content="B" * 500,
    )
    score2 = quality_processor._assess_completeness(entry2)
    assert score2 > score1


def test_quality_assessment_processor_assess_relevance(quality_processor):
    """Test relevance assessment."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test summary",
        topics=["AI", "ML"],
    )

    score = quality_processor._assess_relevance(entry)
    assert 0.0 <= score <= 1.0
    # Should be higher with topics
    assert score >= 0.7


def test_quality_assessment_processor_assess_timeliness(quality_processor):
    """Test timeliness assessment."""
    from datetime import datetime, timezone, timedelta

    # Recent entry
    recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    entry1 = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        published=recent_date,
    )
    score1 = quality_processor._assess_timeliness(entry1)
    assert score1 >= 0.8

    # Old entry
    old_date = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    entry2 = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        published=old_date,
    )
    score2 = quality_processor._assess_timeliness(entry2)
    assert score2 < score1

    # No date
    entry3 = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )
    score3 = quality_processor._assess_timeliness(entry3)
    assert score3 == 0.5


def test_quality_assessment_processor_get_processor_name(quality_processor):
    """Test get_processor_name method."""
    assert quality_processor.get_processor_name() == "QualityAssessmentProcessor"

