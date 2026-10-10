"""CLI argument handling — the boundary between a typo and a traceback.

Every test here stays on the reject path: a `--date` that is refused returns
before `_cmd_report` runs, so nothing reaches Notion or the LLM. Importing
``mimir`` loads ``.env``, which means a developer's real credentials are live
during this module — never add a case that would pass the guard.
"""

from __future__ import annotations

from datetime import date

import pytest

from mimir.cli import _MAX_ANCHOR_YEAR, _MIN_ANCHOR_YEAR, main
from mimir.periods import period_bounds


@pytest.fixture
def cfg_file(tmp_path) -> str:
    """A config file complete enough that only ``--date`` can make a run fail."""
    path = tmp_path / "mimir.toml"
    path.write_text(
        '[notion]\ntoken = "t"\nentries_db_id = "e"\nreports_db_id = "r"\n',
        encoding="utf-8",
    )
    return str(path)


@pytest.mark.parametrize("value", ["not-a-date", "2026-13-01", "0001-01-01", "9999-12-15"])
def test_an_unusable_date_is_a_message_and_not_a_traceback(cfg_file, value, capsys):
    """Two ways to be unusable: unparseable, and outside the calendar the
    report's month arithmetic can address. Both have to come back as text.

    The status alone proves nothing — an unusable config file also exits 1 — so
    the assertion is on the message, which names the offending value.
    """
    assert main(["--config", cfg_file, "report", "--date", value]) == 1
    err = capsys.readouterr().err
    assert "--date" in err
    assert value in err


def test_the_accepted_range_is_exactly_what_the_arithmetic_can_address():
    """The bound is only honest if it is tight: the last accepted year in each
    direction must resolve, and one year further out must not.

    Anchoring is what needs the room — it is the only path that computes a
    month end, so December is where the upper bound comes from.
    """
    for year, month in ((_MIN_ANCHOR_YEAR, 1), (_MAX_ANCHOR_YEAR, 12)):
        period = period_bounds(run_date=date(2026, 10, 8), anchor=date(year, month, 1))
        assert period.start == date(year, month, 1)
        assert period.prev_end < period.start

    with pytest.raises(OverflowError):
        period_bounds(run_date=date(2026, 10, 8), anchor=date(_MIN_ANCHOR_YEAR - 1, 1, 1))
    with pytest.raises(ValueError):
        period_bounds(run_date=date(2026, 10, 8), anchor=date(_MAX_ANCHOR_YEAR + 1, 12, 1))
