"""Reporting period arithmetic — pure, timezone-explicit, no I/O.

The scheduled report never emits a partial period: a run on 2026-10-01 reports
September, not the few hours old October. That is what keeps its numbers equal
to what actually landed in the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

#: China has no DST, so a fixed offset avoids a tzdata dependency.
CST = timezone(timedelta(hours=8), "CST")


@dataclass(frozen=True)
class Period:
    """One reporting window, plus the window it is compared against.

    ``start`` and ``end`` are both inclusive. Boundaries are plain calendar
    dates so they can be compared against the ``YYYY-MM-DD`` stored in Notion's
    date properties; never send these to Notion as datetimes, which would
    switch the comparison to millisecond/UTC semantics.
    """

    start: date
    end: date
    label: str
    prev_start: date
    prev_end: date
    prev_label: str
    run_date: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def __str__(self) -> str:
        return f"{self.label} ({self.start.isoformat()} → {self.end.isoformat()})"


def cst_today(now: datetime | None = None) -> date:
    """Today's calendar date in CST (UTC+8).

    ``notion.py`` stamps ``Collected`` with ``datetime.now(UTC)``, and the daily
    collect cron runs at 00:00 UTC = 08:00 CST, so at automation time the two
    dates agree. The distinction only matters for manual runs, where CST matches
    what the reader means by "today".
    """
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(CST).date()


def period_bounds(*, run_date: date, anchor: date | None = None) -> Period:
    """Resolve the calendar month a report run should cover.

    Without ``anchor``: the most recently *completed* month strictly before
    ``run_date`` — a scheduled run therefore never reports a partial window.
    With ``anchor``: the full month containing that date (``anchor=2026-09-15``
    → September).

    An anchor in year 1 or 9999 has no room for the month before or after it and
    raises ``OverflowError``/``ValueError`` from the ``date`` arithmetic below.
    The CLI rejects those before getting here.
    """
    start, end = _containing(anchor) if anchor is not None else _last_complete(run_date)

    prev_start, prev_end = _previous(start)
    return Period(
        start=start,
        end=end,
        label=start.strftime("%Y-%m"),
        prev_start=prev_start,
        prev_end=prev_end,
        prev_label=prev_start.strftime("%Y-%m"),
        run_date=run_date,
    )


def _month_end(day: date) -> date:
    """Last day of the month containing ``day``."""
    nxt = date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)
    return nxt - timedelta(days=1)


def _last_complete(run_date: date) -> tuple[date, date]:
    end = run_date.replace(day=1) - timedelta(days=1)
    return end.replace(day=1), end


def _containing(anchor: date) -> tuple[date, date]:
    first = anchor.replace(day=1)
    return first, _month_end(first)


def _previous(start: date) -> tuple[date, date]:
    """The month immediately before the one starting at ``start``.

    Contiguous with it (``prev_end == start - 1 day``), so a single query can
    fetch both windows at once.
    """
    prev_end = start - timedelta(days=1)
    return prev_end.replace(day=1), prev_end
