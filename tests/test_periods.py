"""Period arithmetic — the boundary table is the contract that keeps reports honest."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mimir.periods import CST, cst_today, period_bounds

# (run_date, expected start, expected end, expected label)
TABLE = [
    ("2026-10-05", "2026-09-01", "2026-09-30", "2026-09"),
    ("2026-10-01", "2026-09-01", "2026-09-30", "2026-09"),  # the 1st reports the month just ended
    ("2026-10-04", "2026-09-01", "2026-09-30", "2026-09"),
    ("2026-09-01", "2026-08-01", "2026-08-31", "2026-08"),
    ("2027-01-01", "2026-12-01", "2026-12-31", "2026-12"),  # year rollover
    ("2027-01-04", "2026-12-01", "2026-12-31", "2026-12"),
    ("2024-03-01", "2024-02-01", "2024-02-29", "2024-02"),  # leap February
    ("2026-03-01", "2026-02-01", "2026-02-28", "2026-02"),  # common February
    ("2026-05-01", "2026-04-01", "2026-04-30", "2026-04"),  # 30-day month
]


def _d(value: str) -> date:
    return date.fromisoformat(value)


@pytest.mark.parametrize(("run_date", "start", "end", "label"), TABLE)
def test_default_window(run_date, start, end, label):
    period = period_bounds(run_date=_d(run_date))
    assert (period.start, period.end, period.label) == (_d(start), _d(end), label)


@pytest.mark.parametrize(("run_date", "start", "end", "label"), TABLE)
def test_default_window_is_always_complete(run_date, start, end, label):
    """A scheduled run must never report a window that is still filling up."""
    period = period_bounds(run_date=_d(run_date))
    assert period.end < _d(run_date), f"window {period} is not yet complete"


@pytest.mark.parametrize(
    ("anchor", "start", "end", "label"),
    [
        ("2026-09-15", "2026-09-01", "2026-09-30", "2026-09"),
        ("2026-09-01", "2026-09-01", "2026-09-30", "2026-09"),  # the 1st anchors its own month
        ("2026-09-30", "2026-09-01", "2026-09-30", "2026-09"),  # the last day is still that month
        ("2026-02-15", "2026-02-01", "2026-02-28", "2026-02"),
        ("2024-02-15", "2024-02-01", "2024-02-29", "2024-02"),
        # December is the one month whose end needs the *next* year to compute,
        # and anchoring is the only path that computes it — the default window
        # takes its end straight from the run date.
        ("2026-12-31", "2026-12-01", "2026-12-31", "2026-12"),
        ("2026-12-01", "2026-12-01", "2026-12-31", "2026-12"),
    ],
)
def test_anchor_contains_the_date(anchor, start, end, label):
    period = period_bounds(run_date=_d("2026-10-08"), anchor=_d(anchor))
    assert (period.start, period.end, period.label) == (_d(start), _d(end), label)


def test_anchor_ignores_run_date_for_the_window():
    """Backfill picks the period around the anchor, not around today."""
    period = period_bounds(run_date=_d("2026-10-08"), anchor=_d("2026-07-20"))
    assert period.label == "2026-07"
    assert period.run_date == _d("2026-10-08")


def test_previous_window_is_contiguous():
    """prev is the month immediately before, so one query can cover both."""
    for offset in range(0, 400, 7):
        period = period_bounds(run_date=date(2026, 1, 1) + timedelta(days=offset))
        assert period.prev_end == period.start - timedelta(days=1)
        assert period.prev_start < period.prev_end


def test_previous_crosses_the_year_boundary():
    period = period_bounds(run_date=_d("2027-01-05"))
    assert period.label == "2026-12"
    assert period.prev_label == "2026-11"
    assert period.end == _d("2026-12-31")


def test_windows_span_whole_months():
    for offset in range(0, 400, 3):
        period = period_bounds(run_date=date(2026, 1, 1) + timedelta(days=offset))
        assert period.start.day == 1
        assert (period.end + timedelta(days=1)).day == 1  # end is a month's last day
        assert 28 <= period.days <= 31


def test_cst_today_uses_utc_plus_8():
    # 2026-10-08 17:00 UTC is already the 9th in CST.
    assert cst_today(datetime(2026, 10, 8, 17, 0, tzinfo=UTC)) == _d("2026-10-09")
    assert cst_today(datetime(2026, 10, 8, 15, 59, tzinfo=UTC)) == _d("2026-10-08")


def test_cst_today_treats_naive_input_as_utc():
    assert cst_today(datetime(2026, 10, 8, 17, 0)) == _d("2026-10-09")


def test_cst_offset_is_eight_hours():
    assert CST.utcoffset(None) == timedelta(hours=8)


def test_str_is_readable():
    period = period_bounds(run_date=_d("2026-10-01"))
    assert str(period) == "2026-09 (2026-09-01 → 2026-09-30)"
