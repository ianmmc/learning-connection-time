"""#991: import_manual_bell_schedules stamps bell_schedules.year from the DOCUMENTS (content_school_year over the
source file names), never from the wall clock. A clock-derived year moves the (district, year, grade_level) dedupe
key at every July-1 rollover, so a re-import duplicated rows and broke the REQ-026 blend window."""
from unittest.mock import MagicMock

import pytest

from infrastructure.scripts.enrich import import_manual_bell_schedules as imp
from infrastructure.scripts.enrich.content_parser import BellScheduleData


def _session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    return s


def _sched():
    return BellScheduleData(start_time="08:00", end_time="15:00", instructional_minutes=420, grade_level="high")


def test_year_comes_from_the_source_files_not_the_clock(monkeypatch):
    # Poison the clock: whatever the wall clock says must not reach the row.
    monkeypatch.setattr(imp, "current_school_year", lambda *a, **k: "2031-32", raising=False)
    s = _session()
    assert imp.import_bell_schedule(s, "0100001", _sched(), ["Lincoln_High_2025-26_bell_schedule.pdf"])
    row = s.add.call_args.args[0]
    assert row.year == "2025-26"


def test_year_is_stable_across_a_rollover(monkeypatch):
    """The same files imported 'before' and 'after' a July-1 rollover stamp the same year."""
    stamped = []
    for clock in ("2025-26", "2027-28"):
        monkeypatch.setattr(imp, "current_school_year", lambda *a, _c=clock, **k: _c, raising=False)
        s = _session()
        imp.import_bell_schedule(s, "0100001", _sched(), ["bell_2025-26.pdf"])
        stamped.append(s.add.call_args.args[0].year)
    assert stamped == ["2025-26", "2025-26"]


def test_no_year_in_any_source_file_fails_loud_and_writes_nothing():
    s = _session()
    with pytest.raises(ValueError, match="school year"):
        imp.import_bell_schedule(s, "0100001", _sched(), ["bell_schedule.pdf", "notes.txt"])
    s.add.assert_not_called()
