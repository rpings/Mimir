# -*- coding: utf-8 -*-
"""Tests for PriorityRankingProcessor."""

from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

import pytest

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
from src.processors.priority_ranking_processor import PriorityRankingProcessor
from src.processors.processing_context import ProcessingContext


@pytest.fixture
def ranking_config():
    """Sample ranking configuration."""
    return {
        "enabled": True,
        "weights": {
            "quality": 0.4,
            "relevance": 0.3,
            "timeliness": 0.2,
            "source": 0.1,
        },
    }


@pytest.fixture
def ranking_processor(ranking_config):
    """PriorityRankingProcessor instance."""
    return PriorityRankingProcessor(config=ranking_config)


def test_priority_ranking_processor_init_default():
    """Test PriorityRankingProcessor initialization with defaults."""
    processor = PriorityRankingProcessor()
    assert processor.enabled is True
    assert processor.weight_quality == 0.4
    assert processor.weight_relevance == 0.3
    assert processor.weight_timeliness == 0.2
    assert processor.weight_source == 0.1


def test_priority_ranking_processor_process_collected_entry(ranking_processor):
    """Test processing CollectedEntry."""
    entry = CollectedEntry(
        title="Test Title",
        link="https://example.com",
        summary="Test summary",
        published=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    )

    result = ranking_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.final_priority in ["High", "Medium", "Low"]
    assert 0.0 <= result.priority_score <= 1.0
    assert result.ranking_reason is not None


def test_priority_ranking_processor_process_high_quality(ranking_processor):
    """Test processing high quality entry."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        overall_quality=0.9,
        topics=["AI", "ML"],
        verification_score=0.8,
        published=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    )

    result = ranking_processor.process(entry)
    assert result.final_priority == "High"
    assert result.priority_score >= 0.7


def test_priority_ranking_processor_process_low_quality(ranking_processor):
    """Test processing low quality entry."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        overall_quality=0.2,
        topics=[],
        verification_score=0.3,
    )

    result = ranking_processor.process(entry)
    assert result.final_priority == "Low"
    assert result.priority_score < 0.4


def test_priority_ranking_processor_calculate_priority_score(ranking_processor):
    """Test priority score calculation."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        overall_quality=0.8,
        topics=["AI"],
        verification_score=0.7,
    )

    score = ranking_processor._calculate_priority_score(entry)
    assert 0.0 <= score <= 1.0


def test_priority_ranking_processor_calculate_timeliness_recent(ranking_processor):
    """Test timeliness calculation for recent entry."""
    recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        published=recent_date,
    )

    score = ranking_processor._calculate_timeliness(entry)
    assert score >= 0.9


def test_priority_ranking_processor_calculate_timeliness_old(ranking_processor):
    """Test timeliness calculation for old entry."""
    old_date = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        published=old_date,
    )

    score = ranking_processor._calculate_timeliness(entry)
    assert score <= 0.3


def test_priority_ranking_processor_calculate_timeliness_no_date(ranking_processor):
    """Test timeliness calculation without date."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )

    score = ranking_processor._calculate_timeliness(entry)
    assert score == 0.5


def test_priority_ranking_processor_generate_ranking_reason(ranking_processor):
    """Test ranking reason generation."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
        overall_quality=0.8,
        topics=["AI", "ML"],
        verification_status="verified",
        published=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    )

    # Set final_priority first
    entry.final_priority = "High"
    reason = ranking_processor._generate_ranking_reason(entry, 0.8)
    assert isinstance(reason, str)
    assert "High" in reason


def test_priority_ranking_processor_get_processor_name(ranking_processor):
    """Test get_processor_name method."""
    assert ranking_processor.get_processor_name() == "PriorityRankingProcessor"

