# -*- coding: utf-8 -*-
"""Cost tracking and budget management for LLM API calls."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger


class BudgetExceededError(Exception):
    """Raised when budget limit is exceeded."""

    pass


class CostTracker:
    """Tracks LLM API costs and enforces budget limits."""

    def __init__(
        self,
        daily_limit: float = 5.0,
        monthly_budget: float = 50.0,
        cost_file: str | None = None,
    ):
        """Initialize cost tracker.

        Args:
            daily_limit: Maximum cost per day in USD.
            monthly_budget: Maximum cost per month in USD.
            cost_file: Path to cost data file. Defaults to 'data/costs/costs.json'.
        """
        self.daily_limit = daily_limit
        self.monthly_budget = monthly_budget
        self.logger = get_logger(__name__)

        if cost_file is None:
            cost_file = Path(__file__).parent.parent.parent / "data" / "costs" / "costs.json"
        self.cost_file = Path(cost_file)
        self.cost_file.parent.mkdir(parents=True, exist_ok=True)

        self._cost_data: dict[str, Any] = {}
        self._load_cost_data()

    def _load_cost_data(self) -> None:
        """Load cost data from disk."""
        if not self.cost_file.exists():
            self._cost_data = {}
            return

        try:
            with open(self.cost_file, "r", encoding="utf-8") as f:
                self._cost_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Failed to load cost data: {e}, starting fresh")
            self._cost_data = {}

    def _save_cost_data(self) -> None:
        """Save cost data to disk."""
        try:
            with open(self.cost_file, "w", encoding="utf-8") as f:
                json.dump(self._cost_data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            self.logger.error(f"Failed to save cost data: {e}")

    def _get_date_key(self, date: datetime | None = None) -> str:
        """Get date key for cost tracking.

        Args:
            date: Date to get key for. Defaults to today.

        Returns:
            Date key string in YYYY-MM-DD format.
        """
        if date is None:
            date = datetime.now()
        return date.strftime("%Y-%m-%d")

    def _get_month_key(self, date: datetime | None = None) -> str:
        """Get month key for cost tracking.

        Args:
            date: Date to get key for. Defaults to today.

        Returns:
            Month key string in YYYY-MM format.
        """
        if date is None:
            date = datetime.now()
        return date.strftime("%Y-%m")

    def _cleanup_old_data(self) -> None:
        """Remove cost data older than 90 days."""
        cutoff_date = datetime.now() - timedelta(days=90)
        cutoff_key = self._get_date_key(cutoff_date)

        dates_to_remove = [
            key for key in self._cost_data.keys() if key < cutoff_key and len(key) == 10
        ]
        for key in dates_to_remove:
            del self._cost_data[key]

    def check_budget(self, estimated_cost: float = 0.0) -> bool:
        """Check if budget allows an API call.

        Args:
            estimated_cost: Estimated cost of the API call in USD.

        Returns:
            True if budget allows the call, False otherwise.

        Raises:
            BudgetExceededError: If daily limit or monthly budget would be exceeded.
        """
        daily_cost = self.get_daily_cost()
        monthly_cost = self.get_monthly_cost()

        if daily_cost + estimated_cost > self.daily_limit:
            raise BudgetExceededError(
                f"Daily limit exceeded: ${daily_cost:.4f} + ${estimated_cost:.4f} > ${self.daily_limit:.2f}"
            )

        if monthly_cost + estimated_cost > self.monthly_budget:
            raise BudgetExceededError(
                f"Monthly budget exceeded: ${monthly_cost:.4f} + ${estimated_cost:.4f} > ${self.monthly_budget:.2f}"
            )

        return True

    def record_call(
        self,
        cost: float,
        tokens: int,
        model: str = "unknown",
        date: datetime | None = None,
    ) -> None:
        """Record an LLM API call cost.

        Args:
            cost: Actual cost in USD.
            tokens: Total tokens used (prompt + completion).
            model: Model name used.
            date: Date of the call. Defaults to today.
        """
        date_key = self._get_date_key(date)
        month_key = self._get_month_key(date)

        # Initialize date entry if needed
        if date_key not in self._cost_data:
            self._cost_data[date_key] = {"cost": 0.0, "tokens": 0, "calls": 0, "models": {}}

        # Initialize month entry if needed
        if month_key not in self._cost_data:
            self._cost_data[month_key] = {"cost": 0.0, "tokens": 0, "calls": 0}

        # Update date entry
        self._cost_data[date_key]["cost"] += cost
        self._cost_data[date_key]["tokens"] += tokens
        self._cost_data[date_key]["calls"] += 1
        if model not in self._cost_data[date_key]["models"]:
            self._cost_data[date_key]["models"][model] = {"cost": 0.0, "tokens": 0, "calls": 0}
        self._cost_data[date_key]["models"][model]["cost"] += cost
        self._cost_data[date_key]["models"][model]["tokens"] += tokens
        self._cost_data[date_key]["models"][model]["calls"] += 1

        # Update month entry
        self._cost_data[month_key]["cost"] += cost
        self._cost_data[month_key]["tokens"] += tokens
        self._cost_data[month_key]["calls"] += 1

        self._cleanup_old_data()
        self._save_cost_data()

        self.logger.debug(
            f"Recorded LLM call: ${cost:.4f}, {tokens} tokens, model={model}"
        )

    def get_daily_cost(self, date: datetime | None = None) -> float:
        """Get total cost for a specific day.

        Args:
            date: Date to get cost for. Defaults to today.

        Returns:
            Total cost in USD for the day.
        """
        date_key = self._get_date_key(date)
        return self._cost_data.get(date_key, {}).get("cost", 0.0)

    def get_monthly_cost(self, date: datetime | None = None) -> float:
        """Get total cost for a specific month.

        Args:
            date: Date to get cost for. Defaults to current month.

        Returns:
            Total cost in USD for the month.
        """
        month_key = self._get_month_key(date)
        return self._cost_data.get(month_key, {}).get("cost", 0.0)

    def exceeds_daily_limit(self, date: datetime | None = None) -> bool:
        """Check if daily limit is exceeded.

        Args:
            date: Date to check. Defaults to today.

        Returns:
            True if daily limit is exceeded, False otherwise.
        """
        return self.get_daily_cost(date) >= self.daily_limit

    def exceeds_monthly_budget(self, date: datetime | None = None) -> bool:
        """Check if monthly budget is exceeded.

        Args:
            date: Date to check. Defaults to current month.

        Returns:
            True if monthly budget is exceeded, False otherwise.
        """
        return self.get_monthly_cost(date) >= self.monthly_budget

    def get_cost_summary(self) -> dict[str, Any]:
        """Get cost summary for current day and month.

        Returns:
            Dictionary with cost statistics.
        """
        return {
            "daily_cost": self.get_daily_cost(),
            "daily_limit": self.daily_limit,
            "monthly_cost": self.get_monthly_cost(),
            "monthly_budget": self.monthly_budget,
            "daily_remaining": max(0.0, self.daily_limit - self.get_daily_cost()),
            "monthly_remaining": max(0.0, self.monthly_budget - self.get_monthly_cost()),
        }

