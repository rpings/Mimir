# -*- coding: utf-8 -*-
"""Tests for cost tracker module."""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.utils.cost_tracker import BudgetExceededError, CostTracker


@pytest.fixture
def cost_tracker(tmp_path):
    """Cost tracker instance with temporary cost file."""
    cost_file = tmp_path / "costs.json"
    return CostTracker(
        daily_limit=5.0,
        monthly_budget=50.0,
        cost_file=str(cost_file),
    )


def test_cost_tracker_init(cost_tracker):
    """Test cost tracker initialization."""
    assert cost_tracker.daily_limit == 5.0
    assert cost_tracker.monthly_budget == 50.0
    assert cost_tracker.get_daily_cost() == 0.0
    assert cost_tracker.get_monthly_cost() == 0.0


def test_cost_tracker_record_call(cost_tracker):
    """Test recording an API call."""
    cost_tracker.record_call(cost=0.5, tokens=1000, model="gpt-4o-mini")

    assert cost_tracker.get_daily_cost() == 0.5
    assert cost_tracker.get_monthly_cost() == 0.5


def test_cost_tracker_multiple_calls(cost_tracker):
    """Test recording multiple calls."""
    cost_tracker.record_call(cost=0.5, tokens=1000, model="gpt-4o-mini")
    cost_tracker.record_call(cost=0.3, tokens=600, model="gpt-4o-mini")

    assert cost_tracker.get_daily_cost() == 0.8
    assert cost_tracker.get_monthly_cost() == 0.8


def test_cost_tracker_check_budget_success(cost_tracker):
    """Test budget check when within limits."""
    cost_tracker.record_call(cost=2.0, tokens=4000, model="gpt-4o-mini")
    
    # Should not raise
    cost_tracker.check_budget(estimated_cost=2.0)


def test_cost_tracker_check_budget_daily_limit(cost_tracker):
    """Test budget check when daily limit exceeded."""
    cost_tracker.record_call(cost=4.5, tokens=9000, model="gpt-4o-mini")
    
    with pytest.raises(BudgetExceededError, match="Daily limit exceeded"):
        cost_tracker.check_budget(estimated_cost=1.0)


def test_cost_tracker_check_budget_monthly_limit(cost_tracker):
    """Test budget check when monthly budget exceeded."""
    # Record cost that's within daily limit but close to monthly budget
    # Daily limit is 5.0, so use 4.0 to stay under daily limit
    cost_tracker.record_call(cost=4.0, tokens=8000, model="gpt-4o-mini")
    # Add more to get close to monthly budget (50.0)
    # We need to simulate multiple days, but monthly tracking aggregates by month key
    # So we can directly set monthly cost in the data
    month_key = cost_tracker._get_month_key()
    if month_key not in cost_tracker._cost_data:
        cost_tracker._cost_data[month_key] = {"cost": 0.0, "tokens": 0, "calls": 0}
    cost_tracker._cost_data[month_key]["cost"] = 49.5
    
    # Now 49.5 + 1.0 = 50.5 > 50.0, should raise monthly budget error
    with pytest.raises(BudgetExceededError, match="Monthly budget exceeded"):
        cost_tracker.check_budget(estimated_cost=1.0)


def test_cost_tracker_exceeds_daily_limit(cost_tracker):
    """Test exceeds_daily_limit check."""
    assert not cost_tracker.exceeds_daily_limit()
    
    cost_tracker.record_call(cost=5.0, tokens=10000, model="gpt-4o-mini")
    assert cost_tracker.exceeds_daily_limit()


def test_cost_tracker_exceeds_monthly_budget(cost_tracker):
    """Test exceeds_monthly_budget check."""
    assert not cost_tracker.exceeds_monthly_budget()
    
    cost_tracker.record_call(cost=50.0, tokens=100000, model="gpt-4o-mini")
    assert cost_tracker.exceeds_monthly_budget()


def test_cost_tracker_persistence(cost_tracker, tmp_path):
    """Test cost data persistence."""
    cost_tracker.record_call(cost=1.0, tokens=2000, model="gpt-4o-mini")
    
    # Create new instance with same file
    new_tracker = CostTracker(
        daily_limit=5.0,
        monthly_budget=50.0,
        cost_file=str(cost_tracker.cost_file),
    )
    
    assert new_tracker.get_daily_cost() == 1.0
    assert new_tracker.get_monthly_cost() == 1.0


def test_cost_tracker_get_cost_summary(cost_tracker):
    """Test cost summary generation."""
    cost_tracker.record_call(cost=2.0, tokens=4000, model="gpt-4o-mini")
    
    summary = cost_tracker.get_cost_summary()
    assert summary["daily_cost"] == 2.0
    assert summary["daily_limit"] == 5.0
    assert summary["monthly_cost"] == 2.0
    assert summary["monthly_budget"] == 50.0
    assert summary["daily_remaining"] == 3.0
    assert summary["monthly_remaining"] == 48.0


def test_cost_tracker_date_keys(cost_tracker):
    """Test date and month key generation."""
    today = datetime.now()
    date_key = cost_tracker._get_date_key(today)
    month_key = cost_tracker._get_month_key(today)
    
    assert date_key == today.strftime("%Y-%m-%d")
    assert month_key == today.strftime("%Y-%m")


def test_cost_tracker_cleanup_old_data(cost_tracker):
    """Test cleanup of old cost data."""
    # Add old data (90+ days ago)
    old_date = datetime.now() - timedelta(days=100)
    old_key = cost_tracker._get_date_key(old_date)
    cost_tracker._cost_data[old_key] = {"cost": 1.0, "tokens": 2000, "calls": 1, "models": {}}
    
    # Add current data
    cost_tracker.record_call(cost=1.0, tokens=2000, model="gpt-4o-mini")
    
    # Old data should be cleaned up
    assert old_key not in cost_tracker._cost_data


def test_cost_tracker_invalid_json(tmp_path):
    """Test handling of invalid JSON in cost file."""
    cost_file = tmp_path / "costs.json"
    cost_file.write_text("invalid json")
    
    # Should start fresh without error
    tracker = CostTracker(
        daily_limit=5.0,
        monthly_budget=50.0,
        cost_file=str(cost_file),
    )
    
    assert tracker.get_daily_cost() == 0.0

