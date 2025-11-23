# -*- coding: utf-8 -*-
"""Tests for InformationVerificationProcessor."""

from unittest.mock import Mock

import pytest

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
from src.processors.information_verification_processor import InformationVerificationProcessor
from src.processors.processing_context import ProcessingContext


@pytest.fixture
def verification_config():
    """Sample verification configuration."""
    return {
        "enabled": True,
        "verify_source": True,
        "cross_verify": False,
        "fact_check_llm": False,
        "source_whitelist": ["arxiv.org"],
    }


@pytest.fixture
def verification_processor(verification_config):
    """InformationVerificationProcessor instance."""
    return InformationVerificationProcessor(config=verification_config)


def test_information_verification_processor_init_default():
    """Test InformationVerificationProcessor initialization with defaults."""
    processor = InformationVerificationProcessor()
    assert processor.enabled is True
    assert processor.verify_source is True
    assert processor.cross_verify is False
    assert processor.fact_check_llm is False


def test_information_verification_processor_process_collected_entry(verification_processor):
    """Test processing CollectedEntry."""
    entry = CollectedEntry(
        title="Test Title",
        link="https://arxiv.org/abs/1234.5678",
        summary="Test summary",
    )

    result = verification_processor.process(entry)
    assert isinstance(result, ProcessedEntry)
    assert result.verification_status in ["verified", "unverified", "suspicious"]
    assert 0.0 <= result.verification_score <= 1.0
    assert isinstance(result.verification_warnings, list)


def test_information_verification_processor_process_suspicious(verification_processor):
    """Test processing suspicious content (should be filtered)."""
    entry = CollectedEntry(
        title="Test",
        link="http://spam.tk/article",  # Suspicious domain, non-HTTPS
        summary="Test summary",
    )

    result = verification_processor.process(entry)
    # Should have low verification score
    assert result is not None
    assert result.verification_score < 0.4
    assert result.verification_status in ["suspicious", "unverified"]


def test_information_verification_processor_verify_source_whitelist(verification_processor):
    """Test source verification with whitelist."""
    entry = ProcessedEntry(
        title="Test",
        link="https://arxiv.org/abs/1234.5678",
        summary="Test",
    )

    score, warnings = verification_processor._verify_source(entry)
    assert 0.0 <= score <= 1.0
    assert score >= 0.9  # Should be high for whitelisted domain
    assert isinstance(warnings, list)


def test_information_verification_processor_verify_source_suspicious():
    """Test source verification with suspicious domain."""
    processor = InformationVerificationProcessor()
    entry = ProcessedEntry(
        title="Test",
        link="http://spam.tk/article",
        summary="Test",
    )

    score, warnings = processor._verify_source(entry)
    assert score <= 0.3
    assert len(warnings) > 0


def test_information_verification_processor_verify_source_https():
    """Test source verification with HTTPS."""
    processor = InformationVerificationProcessor()
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com/article",
        summary="Test",
    )

    score1, warnings1 = processor._verify_source(entry)

    entry2 = ProcessedEntry(
        title="Test",
        link="http://example.com/article",  # Non-HTTPS
        summary="Test",
    )

    score2, warnings2 = processor._verify_source(entry2)
    assert score1 > score2
    assert len(warnings2) > 0
    assert any("HTTPS" in w or "http" in w.lower() for w in warnings2)


def test_information_verification_processor_cross_verify(verification_processor):
    """Test cross-verification."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )

    score = verification_processor._cross_verify(entry)
    assert 0.0 <= score <= 1.0


def test_information_verification_processor_fact_check_llm(verification_processor):
    """Test fact-checking with LLM."""
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test",
    )
    context = ProcessingContext()

    score = verification_processor._fact_check_llm(entry, context)
    # Should return None if not implemented
    assert score is None


def test_information_verification_processor_get_processor_name(verification_processor):
    """Test get_processor_name method."""
    assert verification_processor.get_processor_name() == "InformationVerificationProcessor"

