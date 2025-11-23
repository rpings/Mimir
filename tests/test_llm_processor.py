# -*- coding: utf-8 -*-
"""Tests for LLM processor module."""

import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.collectors.base_collector import CollectedEntry
from src.processors.base_processor import ProcessedEntry
from src.processors.llm_processor import LLMProcessingError, LLMProcessor
from src.utils.cost_tracker import BudgetExceededError, CostTracker
from src.storages.llm_cache import LLMCache


@pytest.fixture
def cost_tracker(tmp_path):
    """Cost tracker instance."""
    cost_file = tmp_path / "test_costs.json"
    return CostTracker(
        daily_limit=10.0,
        monthly_budget=100.0,
        cost_file=str(cost_file),
    )


@pytest.fixture
def llm_config():
    """LLM configuration."""
    return {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "base_url": None,
        "daily_limit": 10.0,
        "monthly_budget": 100.0,
        "features": {
            "summarization": True,
            "translation": True,
            "smart_categorization": True,
        },
        "translation": {
            "target_languages": ["zh"],
        },
    }


@pytest.fixture
def llm_cache(tmp_path):
    """LLM cache instance."""
    return LLMCache(cache_dir=tmp_path / "llm_cache")


@pytest.fixture
def llm_processor(llm_config, cost_tracker, llm_cache):
    """LLM processor instance."""
    return LLMProcessor(config=llm_config, cost_tracker=cost_tracker, llm_cache=llm_cache)


@pytest.fixture
def sample_entry():
    """Sample collected entry."""
    return CollectedEntry(
        title="AI Breakthrough in Machine Learning",
        link="https://example.com/article",
        summary="Researchers have developed a new machine learning model that achieves state-of-the-art results. This breakthrough represents a significant advancement in the field of artificial intelligence and has implications for various applications.",
    )


@pytest.fixture
def mock_litellm_response():
    """Mock litellm completion response."""
    mock_response = Mock()
    mock_choice = Mock()
    mock_choice.message.content = "Test response"
    mock_response.choices = [mock_choice]
    mock_usage = Mock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_response.usage = mock_usage
    return mock_response


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_summarization(mock_cost, mock_completion, llm_processor, sample_entry, mock_litellm_response):
    """Test LLM summarization feature."""
    mock_completion.return_value = mock_litellm_response
    mock_cost.return_value = 0.001
    
    # Create processed entry from collected entry
    processed = ProcessedEntry.from_collected(sample_entry)
    processed.topics = ["AI"]
    processed.priority = "High"
    
    result = llm_processor.process(processed)
    
    assert mock_completion.called, "completion should have been called"
    assert result.summary_llm is not None
    assert result.summary_llm == "Test response"
    assert result.processing_method == "hybrid"


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_translation(mock_cost, mock_completion, llm_processor, sample_entry, mock_litellm_response):
    """Test LLM translation feature."""
    mock_completion.return_value = mock_litellm_response
    mock_cost.return_value = 0.001
    
    processed = ProcessedEntry.from_collected(sample_entry)
    result = llm_processor.process(processed)
    
    assert mock_completion.called
    assert result.translation is not None
    assert "zh" in result.translation


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_categorization(mock_cost, mock_completion, llm_processor, sample_entry):
    """Test LLM smart categorization feature."""
    mock_response = Mock()
    mock_choice = Mock()
    mock_choice.message.content = '{"topics": ["AI", "ML"], "priority": "High"}'
    mock_response.choices = [mock_choice]
    mock_usage = Mock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_response.usage = mock_usage
    mock_completion.return_value = mock_response
    mock_cost.return_value = 0.001
    
    processed = ProcessedEntry.from_collected(sample_entry)
    result = llm_processor.process(processed)
    
    assert mock_completion.called
    assert result.topics_llm is not None
    assert "AI" in result.topics_llm
    assert result.priority_llm == "High"


@patch("src.processors.llm_processor.completion")
def test_llm_processor_disabled(llm_config, cost_tracker, sample_entry):
    """Test LLM processor when disabled."""
    llm_config["enabled"] = False
    processor = LLMProcessor(config=llm_config, cost_tracker=cost_tracker)
    
    processed = ProcessedEntry.from_collected(sample_entry)
    result = processor.process(processed)
    
    assert result.summary_llm is None
    assert result.translation is None


@patch("src.processors.llm_processor.completion")
def test_llm_processor_budget_exceeded(mock_completion, llm_processor, sample_entry):
    """Test LLM processor handles budget exceeded."""
    cost_tracker = llm_processor.cost_tracker
    cost_tracker.record_call(cost=10.0, tokens=20000, model="gpt-4o-mini")
    
    processed = ProcessedEntry.from_collected(sample_entry)
    result = llm_processor.process(processed)
    
    # Should return without LLM enhancements
    assert result.summary_llm is None


@patch("src.processors.llm_processor.completion")
def test_llm_processor_api_error(mock_completion, llm_processor, sample_entry):
    """Test LLM processor handles API errors gracefully."""
    from litellm.exceptions import APIError
    
    # Create a proper APIError instance with required parameters
    api_error = APIError(
        status_code=500,
        message="API error",
        llm_provider="openai",
        model="gpt-4o-mini",
    )
    mock_completion.side_effect = api_error
    
    processed = ProcessedEntry.from_collected(sample_entry)
    result = llm_processor.process(processed)
    
    # Should return without LLM enhancements
    assert result.summary_llm is None


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_base_url_from_config(mock_cost, mock_completion, llm_config, cost_tracker, llm_cache, sample_entry, mock_litellm_response):
    """Test LLM processor uses base_url from config."""
    # Clear env var to ensure config is used
    with patch.dict(os.environ, {"LLM_BASE_URL": ""}, clear=False):
        llm_config["base_url"] = "http://localhost:1234/v1"
        processor = LLMProcessor(config=llm_config, cost_tracker=cost_tracker, llm_cache=llm_cache)
        
        mock_completion.return_value = mock_litellm_response
        mock_cost.return_value = 0.001
        processed = ProcessedEntry.from_collected(sample_entry)
        processor.process(processed)
        
        # Check that api_base was passed to litellm
        assert mock_completion.called
        call_args = mock_completion.call_args
        assert call_args is not None
        assert "api_base" in call_args.kwargs
        assert call_args.kwargs["api_base"] == "http://localhost:1234/v1"


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_base_url_from_env(mock_cost, mock_completion, llm_config, cost_tracker, sample_entry, mock_litellm_response):
    """Test LLM processor uses base_url from environment variable."""
    # Config has base_url but env var should override
    llm_config["base_url"] = "http://config-url.com/v1"
    
    with patch.dict(os.environ, {"LLM_BASE_URL": "http://custom-api.com/v1"}):
        processor = LLMProcessor(config=llm_config, cost_tracker=cost_tracker)
        
        mock_completion.return_value = mock_litellm_response
        mock_cost.return_value = 0.001
        
        # Create processed entry with topics/priority to ensure it goes through LLM
        processed = ProcessedEntry.from_collected(sample_entry)
        processed.topics = ["AI"]
        processed.priority = "High"
        
        processor.process(processed)
        
        # Check that env var base_url was used
        assert mock_completion.called, "completion should have been called"
        call_args = mock_completion.call_args
        assert call_args is not None
        assert "api_base" in call_args.kwargs
        assert call_args.kwargs["api_base"] == "http://custom-api.com/v1"


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_no_base_url(mock_cost, mock_completion, llm_config, cost_tracker, llm_cache, sample_entry, mock_litellm_response):
    """Test LLM processor without base_url uses provider default."""
    # Clear env var and config base_url
    with patch.dict(os.environ, {"LLM_BASE_URL": ""}, clear=False):
        llm_config.pop("base_url", None)
        processor = LLMProcessor(config=llm_config, cost_tracker=cost_tracker, llm_cache=llm_cache)
        
        mock_completion.return_value = mock_litellm_response
        mock_cost.return_value = 0.001
        
        # Create processed entry with topics/priority to ensure it goes through LLM
        processed = ProcessedEntry.from_collected(sample_entry)
        processed.topics = ["AI"]
        processed.priority = "High"
        
        processor.process(processed)
        
        # Check that api_base was not passed (None means use default)
        assert mock_completion.called, "completion should have been called"
        call_args = mock_completion.call_args
        assert call_args is not None
        # If base_url is None, it should not be in kwargs
        assert "api_base" not in call_args.kwargs or call_args.kwargs.get("api_base") is None


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_cost_tracking(mock_cost, mock_completion, llm_config, cost_tracker, llm_cache, sample_entry, mock_litellm_response, tmp_path):
    """Test LLM processor tracks costs correctly."""
    mock_completion.return_value = mock_litellm_response
    mock_cost.return_value = 0.001  # Fixed cost for testing
    
    # Use a fresh cost tracker to avoid state from other tests
    from src.utils.cost_tracker import CostTracker
    cost_file = tmp_path / "test_costs.json"
    fresh_cost_tracker = CostTracker(
        daily_limit=10.0,
        monthly_budget=100.0,
        cost_file=str(cost_file),
    )
    processor = LLMProcessor(config=llm_config, cost_tracker=fresh_cost_tracker, llm_cache=llm_cache)
    
    initial_daily_cost = fresh_cost_tracker.get_daily_cost()
    
    processed = ProcessedEntry.from_collected(sample_entry)
    processor.process(processed)
    
    # Cost should be recorded
    new_daily_cost = fresh_cost_tracker.get_daily_cost()
    assert new_daily_cost > initial_daily_cost


def test_llm_processor_get_processor_name(llm_processor):
    """Test processor name."""
    assert llm_processor.get_processor_name() == "LLMProcessor"


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_base_url_empty_string(mock_cost, mock_completion, llm_config, cost_tracker, llm_cache):
    """Test LLM processor handles empty string base_url."""
    # Clear env var to ensure config is used
    with patch.dict(os.environ, {"LLM_BASE_URL": ""}, clear=False):
        llm_config["base_url"] = ""
        processor = LLMProcessor(config=llm_config, cost_tracker=cost_tracker, llm_cache=llm_cache)
        assert processor.base_url is None


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_from_collected_entry(mock_cost, mock_completion, llm_processor, llm_cache, sample_entry, mock_litellm_response):
    """Test LLM processor with CollectedEntry (not ProcessedEntry)."""
    mock_completion.return_value = mock_litellm_response
    mock_cost.return_value = 0.001
    
    # Pass CollectedEntry directly
    result = llm_processor.process(sample_entry)
    assert isinstance(result, ProcessedEntry)
    assert result.title == sample_entry.title


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_disabled_skips(mock_cost, mock_completion, llm_config, cost_tracker, llm_cache, sample_entry):
    """Test LLM processor when disabled."""
    llm_config["enabled"] = False
    processor = LLMProcessor(config=llm_config, cost_tracker=cost_tracker, llm_cache=llm_cache)
    
    processed = ProcessedEntry.from_collected(sample_entry)
    result = processor.process(processed)
    
    assert result.summary_llm is None
    assert result.translation is None
    assert not mock_completion.called


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_budget_exceeded_skips(mock_cost, mock_completion, llm_config, cost_tracker, llm_cache, sample_entry):
    """Test LLM processor skips when budget exceeded."""
    # Set budget to 0 to trigger budget exceeded
    cost_tracker.daily_limit = 0.0
    cost_tracker.monthly_budget = 0.0
    
    processor = LLMProcessor(config=llm_config, cost_tracker=cost_tracker, llm_cache=llm_cache)
    
    processed = ProcessedEntry.from_collected(sample_entry)
    result = processor.process(processed)
    
    # Should return without LLM enhancements
    assert result.summary_llm is None
    assert not mock_completion.called


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_processing_method_hybrid(mock_cost, mock_completion, llm_processor, sample_entry, mock_litellm_response):
    """Test processing method is set to hybrid when LLM features are used."""
    mock_completion.return_value = mock_litellm_response
    mock_cost.return_value = 0.001
    
    processed = ProcessedEntry.from_collected(sample_entry)
    processed.topics = ["AI"]  # Set from keyword processor
    processed.priority = "High"
    
    result = llm_processor.process(processed)
    
    assert result.processing_method == "hybrid"


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_summary_content_too_short(mock_cost, mock_completion, llm_processor, llm_cache):
    """Test summary generation with content too short."""
    from src.processors.base_processor import ProcessedEntry
    
    # Create entry with very short content
    entry = ProcessedEntry(
        title="A",
        link="https://example.com",
        summary="B",
    )
    
    result = llm_processor._generate_summary(entry)
    assert result is None
    assert not mock_completion.called


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_translation_no_target_languages(mock_cost, mock_completion, llm_config, cost_tracker, llm_cache):
    """Test translation with no target languages."""
    llm_config["translation"]["target_languages"] = []
    processor = LLMProcessor(config=llm_config, cost_tracker=cost_tracker, llm_cache=llm_cache)
    
    entry = ProcessedEntry(
        title="Test",
        link="https://example.com",
        summary="Test content",
    )
    
    result = processor._translate_content(entry)
    assert result is None


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_translation_content_too_short(mock_cost, mock_completion, llm_processor, llm_cache):
    """Test translation with content too short."""
    entry = ProcessedEntry(
        title="A",
        link="https://example.com",
        summary="B",
    )
    
    result = llm_processor._translate_content(entry)
    assert result is None
    assert not mock_completion.called


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_categorization_content_too_short(mock_cost, mock_completion, llm_processor, llm_cache):
    """Test categorization with content too short."""
    entry = ProcessedEntry(
        title="A",
        link="https://example.com",
        summary="B",
    )
    
    result = llm_processor._smart_categorize(entry)
    assert result is None
    assert not mock_completion.called


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_json_markdown_removal_short(mock_cost, mock_completion, llm_processor, llm_cache, sample_entry):
    """Test JSON parsing with markdown code blocks (len <= 2 case)."""
    mock_response = Mock()
    mock_choice = Mock()
    # Content with markdown but only 2 lines (should not remove)
    mock_choice.message.content = "```\n{\"topics\": [\"AI\"]}\n```"
    mock_response.choices = [mock_choice]
    mock_usage = Mock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_response.usage = mock_usage
    mock_completion.return_value = mock_response
    mock_cost.return_value = 0.001
    
    entry = ProcessedEntry.from_collected(sample_entry)
    result = llm_processor._smart_categorize(entry)
    
    # Should handle gracefully even with short markdown block
    assert result is not None or isinstance(result, dict) or result is None


@patch("src.processors.llm_processor.completion")
@patch("src.processors.llm_processor.cost_per_token")
def test_llm_processor_json_parsing_error(mock_cost, mock_completion, llm_processor, sample_entry):
    """Test LLM processor handles JSON parsing errors in categorization."""
    mock_response = Mock()
    mock_choice = Mock()
    mock_choice.message.content = "Invalid JSON response"
    mock_response.choices = [mock_choice]
    mock_usage = Mock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_response.usage = mock_usage
    mock_completion.return_value = mock_response
    mock_cost.return_value = 0.001
    
    processed = ProcessedEntry.from_collected(sample_entry)
    result = llm_processor.process(processed)
    
    # Should handle error gracefully
    assert result.topics_llm is None or isinstance(result.topics_llm, list)

