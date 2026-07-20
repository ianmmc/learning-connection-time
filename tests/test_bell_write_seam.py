"""
Tests for the bell_schedules write seam hardening (issues #19, #26, #66, #68, #72).

Covers:
- 24-hour HH:MM time acceptance in validate_schedule_plausibility (#19/#66)
- non-numeric instructional_minutes returns valid=False instead of raising (#66)
- absent times skip time checks (minutes-only enrichments become copyable) (#68)
- gross plausibility warn band converged on school_year 240-510 (#72)
- add_bell_schedule: COVID/malformed year rejected at the seam, partial update
  preserves fields, minutes_basis set on new writes (#26/#19)
- manual importer: unique-match-or-refuse district matching (#26)
- resolve_grade_level says when it defaulted (#68)

Run: pytest tests/test_bell_write_seam.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from infrastructure.database.verification import validate_schedule_plausibility
from infrastructure.database.school_year import GROSS_MINUTES_MIN, GROSS_MINUTES_MAX


# =============================================================================
# validate_schedule_plausibility — time formats (#19 / #66)
# =============================================================================

class TestTwentyFourHourTimes:
    def test_24_hour_times_accepted(self):
        result = validate_schedule_plausibility({
            'start_time': '08:00',
            'end_time': '14:20',
            'grade_level': 'high',
            'instructional_minutes': 380,
        })
        assert result['valid'], result['errors']

    def test_24_hour_afternoon_hour_parses_as_pm(self):
        # 14:20 must read as 2:20 PM, i.e. inside the plausible end range (no warning)
        result = validate_schedule_plausibility({
            'start_time': '08:00',
            'end_time': '14:20',
            'grade_level': 'high',
            'instructional_minutes': 380,
        })
        assert not any('end time' in w.lower() for w in result['warnings'])

    def test_am_pm_times_still_accepted(self):
        result = validate_schedule_plausibility({
            'start_time': '7:30 AM',
            'end_time': '2:45 PM',
            'grade_level': 'high',
            'instructional_minutes': 395,
        })
        assert result['valid']

    def test_garbage_time_still_rejected(self):
        result = validate_schedule_plausibility({
            'start_time': '0800',  # no colon — neither format
            'end_time': '3:00 PM',
            'grade_level': 'high',
            'instructional_minutes': 390,
        })
        assert not result['valid']

    def test_24_hour_out_of_range_hour_rejected(self):
        result = validate_schedule_plausibility({
            'start_time': '25:00',
            'end_time': '14:00',
            'grade_level': 'high',
            'instructional_minutes': 390,
        })
        assert not result['valid']


class TestNonNumericMinutesNoCrash:
    def test_non_numeric_minutes_returns_invalid_not_raises(self):
        # Previously step 7 re-cast with a bare int() and raised ValueError (#66)
        result = validate_schedule_plausibility({
            'start_time': '8:00 AM',
            'end_time': '3:00 PM',
            'grade_level': 'high',
            'instructional_minutes': 'not_a_number',
        })
        assert not result['valid']
        assert any('instructional_minutes' in e for e in result['errors'])


class TestAbsentTimesSkipTimeChecks:
    def test_minutes_only_schedule_is_valid(self):
        # Enrichments without times must be copyable when minutes exist (#68)
        result = validate_schedule_plausibility({
            'start_time': None,
            'end_time': None,
            'grade_level': 'high',
            'instructional_minutes': 400,
        })
        assert result['valid'], result['errors']

    def test_missing_time_keys_are_valid(self):
        result = validate_schedule_plausibility({
            'grade_level': 'elementary',
            'instructional_minutes': 380,
        })
        assert result['valid'], result['errors']

    def test_provided_but_invalid_time_still_errors(self):
        result = validate_schedule_plausibility({
            'start_time': 'Unknown',
            'end_time': 'Unknown',
            'grade_level': 'high',
            'instructional_minutes': 400,
        })
        assert not result['valid']


class TestGrossWarnBand:
    def test_band_is_the_school_year_band(self):
        from infrastructure.database.verification import PLAUSIBLE_INSTRUCTIONAL_RANGE
        assert PLAUSIBLE_INSTRUCTIONAL_RANGE == (GROSS_MINUTES_MIN, GROSS_MINUTES_MAX)

    def test_inside_band_no_minutes_warning(self):
        result = validate_schedule_plausibility({
            'grade_level': 'high',
            'instructional_minutes': 505,  # inside 240-510, outside old 300-480
        })
        assert result['valid']
        assert not any('minutes' in w.lower() for w in result['warnings'])

    def test_outside_band_warns(self):
        result = validate_schedule_plausibility({
            'grade_level': 'high',
            'instructional_minutes': 520,  # above 510 but inside DB sanity 100-600
        })
        assert result['valid']
        assert any('520' in w for w in result['warnings'])

    def test_outside_db_sanity_band_errors(self):
        result = validate_schedule_plausibility({
            'grade_level': 'high',
            'instructional_minutes': 700,  # above the 100-600 outer bound
        })
        assert not result['valid']


# =============================================================================
# add_bell_schedule — the seam guard (#26) + minutes_basis (#19)
# =============================================================================

def _district_stub(nces_id='0612345'):
    return SimpleNamespace(nces_id=nces_id)


def _session_returning(district, existing):
    """MagicMock session whose first query resolves the District and second the
    existing BellSchedule (None for the create path)."""
    session = MagicMock()
    district_q = MagicMock()
    district_q.filter.return_value.first.return_value = district
    existing_q = MagicMock()
    existing_q.filter.return_value.first.return_value = existing
    session.query.side_effect = [district_q, existing_q]
    return session


class TestAddBellScheduleSeam:
    @pytest.mark.parametrize('year', ['2019-20', '2020-21', '2021-22', '2022-23'])
    def test_covid_year_rejected(self, year):
        from infrastructure.database.queries import add_bell_schedule
        with pytest.raises(ValueError, match='COVID'):
            add_bell_schedule(
                MagicMock(), district_id='0612345', year=year,
                grade_level='high', instructional_minutes=400,
            )

    @pytest.mark.parametrize('year', ['2024-2025', '2024', 'garbage', '', '2024-26'])
    def test_malformed_year_rejected(self, year):
        from infrastructure.database.queries import add_bell_schedule
        with pytest.raises(ValueError):
            add_bell_schedule(
                MagicMock(), district_id='0612345', year=year,
                grade_level='high', instructional_minutes=400,
            )

    def test_new_write_sets_minutes_basis(self):
        from infrastructure.database.queries import add_bell_schedule
        from infrastructure.database.models import BellSchedule
        session = _session_returning(_district_stub(), existing=None)

        schedule = add_bell_schedule(
            session, district_id='0612345', year='2024-25',
            grade_level='high', instructional_minutes=400,
        )
        assert schedule.minutes_basis == 'gross_bell_to_bell'
        added = [c.args[0] for c in session.add.call_args_list
                 if isinstance(c.args[0], BellSchedule)]
        assert added and added[0].minutes_basis == 'gross_bell_to_bell'

    def test_statutory_basis_can_be_passed(self):
        from infrastructure.database.queries import add_bell_schedule
        session = _session_returning(_district_stub(), existing=None)
        schedule = add_bell_schedule(
            session, district_id='0612345', year='2024-25',
            grade_level='high', instructional_minutes=360,
            method='statutory_fallback', minutes_basis='statutory',
        )
        assert schedule.minutes_basis == 'statutory'

    def test_partial_update_preserves_unspecified_fields(self):
        from infrastructure.database.queries import add_bell_schedule
        from infrastructure.database.models import BellSchedule

        existing = BellSchedule(
            district_id='0612345', year='2024-25', grade_level='high',
            instructional_minutes=390, start_time='8:00 AM', end_time='2:30 PM',
            lunch_duration=45, passing_periods=6, recess_duration=15,
            schools_sampled=['A High'], source_urls=['https://example.org'],
            confidence='high', method='human_provided',
            source_description='original source', notes='keep me',
        )
        session = _session_returning(_district_stub(), existing=existing)

        schedule = add_bell_schedule(
            session, district_id='0612345', year='2024-25',
            grade_level='high', instructional_minutes=400,
        )

        assert schedule is existing
        assert existing.instructional_minutes == 400
        # None-valued optionals must NOT erase existing data (#26)
        assert existing.start_time == '8:00 AM'
        assert existing.end_time == '2:30 PM'
        assert existing.lunch_duration == 45
        assert existing.passing_periods == 6
        assert existing.recess_duration == 15
        assert existing.schools_sampled == ['A High']
        assert existing.source_urls == ['https://example.org']
        assert existing.source_description == 'original source'
        assert existing.notes == 'keep me'
        # A rewrite is a new labeled write
        assert existing.minutes_basis == 'gross_bell_to_bell'

    def test_update_overwrites_fields_actually_passed(self):
        from infrastructure.database.queries import add_bell_schedule
        from infrastructure.database.models import BellSchedule

        existing = BellSchedule(
            district_id='0612345', year='2024-25', grade_level='high',
            instructional_minutes=390, lunch_duration=45, notes='old',
            confidence='high', method='human_provided',
        )
        session = _session_returning(_district_stub(), existing=existing)

        add_bell_schedule(
            session, district_id='0612345', year='2024-25',
            grade_level='high', instructional_minutes=405,
            lunch_duration=30, notes='new note',
        )
        assert existing.lunch_duration == 30
        assert existing.notes == 'new note'
        assert existing.instructional_minutes == 405


# =============================================================================
# Manual importer district matching — unique or refuse (#26)
# =============================================================================

class TestManualImporterMatching:
    def _session_with_stage_results(self, stage_results):
        session = MagicMock()
        q = session.query.return_value.filter.return_value.order_by.return_value
        q.all.side_effect = stage_results
        return session

    def test_unique_match_accepted(self):
        from infrastructure.scripts.enrich.import_manual_bell_schedules import match_district
        d = _district_stub('0612345')
        session = self._session_with_stage_results([[d]])
        district, reason = match_district(session, 'CA', 'Springfield')
        assert district is d
        assert reason is None

    def test_ambiguous_match_refused_never_first_of_many(self):
        from infrastructure.scripts.enrich.import_manual_bell_schedules import match_district
        d1 = SimpleNamespace(nces_id='0600001', name='Springfield Elementary SD')
        d2 = SimpleNamespace(nces_id='0600002', name='Springfield Union High SD')
        session = self._session_with_stage_results([[d1, d2]])
        district, reason = match_district(session, 'CA', 'Springfield')
        assert district is None
        assert 'ambiguous' in reason
        assert '0600001' in reason and '0600002' in reason

    def test_no_match_reported(self):
        from infrastructure.scripts.enrich.import_manual_bell_schedules import match_district
        # 'Springfield' is one word / not suffixed: exactly 2 stages run
        session = self._session_with_stage_results([[], []])
        district, reason = match_district(session, 'CA', 'Springfield')
        assert district is None
        assert reason == 'no matching district'

    def test_exact_nces_id_in_folder_name_wins(self):
        from infrastructure.scripts.enrich.import_manual_bell_schedules import match_district
        d = _district_stub('0612345')
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = d
        district, reason = match_district(
            session, 'CA', 'Springfield', folder_name='Springfield 0612345 (CA)'
        )
        assert district is d
        assert reason is None

    def test_nces_id_in_folder_name_not_in_db_refused(self):
        from infrastructure.scripts.enrich.import_manual_bell_schedules import match_district
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        district, reason = match_district(
            session, 'CA', 'Springfield', folder_name='Springfield 9999999'
        )
        assert district is None
        assert '9999999' in reason


# =============================================================================
# enrichment_utils — grade-level defaulting is explicit (#68)
# =============================================================================

class TestResolveGradeLevel:
    def test_signal_present_not_defaulted(self):
        from infrastructure.database.enrichment_utils import resolve_grade_level
        assert resolve_grade_level('high_school') == ('high', False)
        assert resolve_grade_level('middle_school') == ('middle', False)
        assert resolve_grade_level('elementary') == ('elementary', False)

    def test_schools_sampled_signal_not_defaulted(self):
        from infrastructure.database.enrichment_utils import resolve_grade_level
        grade, defaulted = resolve_grade_level('all', [{'level': 'Elementary'}])
        assert (grade, defaulted) == ('elementary', False)

    @pytest.mark.parametrize('schedule_type', ['all', 'district_average'])
    def test_no_signal_defaults_to_high_and_says_so(self, schedule_type):
        from infrastructure.database.enrichment_utils import resolve_grade_level
        grade, defaulted = resolve_grade_level(schedule_type)
        assert grade == 'high'
        assert defaulted is True

    def test_backward_compatible_wrapper(self):
        from infrastructure.database.enrichment_utils import map_schedule_type_to_grade_level
        assert map_schedule_type_to_grade_level('district_average') == 'high'


class TestCopyEnrichmentTransactionality:
    def _mock_session_for_copy(self, tier_result):
        enrichment = SimpleNamespace(
            status='completed', current_tier=1, tier_1_result=tier_result,
            tier_2_result=None, tier_3_result=None, tier_4_result=None,
            tier_5_result=None, district_id='0612345',
        )
        session = MagicMock()
        enr_q = MagicMock()
        # queue lookup matches raw OR padded id via .filter(in_()) (issue #284)
        enr_q.filter.return_value.first.return_value = enrichment
        bell_q = MagicMock()
        bell_q.filter_by.return_value.first.return_value = None
        session.query.side_effect = [enr_q, bell_q]
        return session

    def test_minutes_only_enrichment_copies_and_flags_default(self):
        from infrastructure.database.enrichment_utils import copy_enrichment_to_bell_schedules
        session = self._mock_session_for_copy({
            'total_minutes': 400, 'year': '2024-25', 'schedule_type': 'all',
        })
        ok, message = copy_enrichment_to_bell_schedules(session, '0612345')
        assert ok, message
        added = session.add.call_args[0][0]
        assert added.start_time is None
        assert added.end_time is None
        assert "defaulted to 'high'" in added.notes

    def test_commit_false_flushes_instead(self):
        from infrastructure.database.enrichment_utils import copy_enrichment_to_bell_schedules
        session = self._mock_session_for_copy({
            'total_minutes': 400, 'year': '2024-25', 'schedule_type': 'high_school',
        })
        ok, _ = copy_enrichment_to_bell_schedules(session, '0612345', commit=False)
        assert ok
        session.commit.assert_not_called()
        session.flush.assert_called_once()

    def test_commit_true_commits(self):
        from infrastructure.database.enrichment_utils import copy_enrichment_to_bell_schedules
        session = self._mock_session_for_copy({
            'total_minutes': 400, 'year': '2024-25', 'schedule_type': 'high_school',
        })
        ok, _ = copy_enrichment_to_bell_schedules(session, '0612345', commit=True)
        assert ok
        session.commit.assert_called_once()


# =============================================================================
# content_parser — gross band converged on school_year (#72)
# =============================================================================

class TestContentParserGrossBand:
    def test_band_over_510_now_rejected(self):
        from infrastructure.scripts.enrich.content_parser import ContentParser
        parser = ContentParser(use_llm=False)
        # 7:00 AM - 4:00 PM = 540 gross: inside the old 240-540 band, outside 240-510
        result = parser.parse('School hours: 7:00 AM - 4:00 PM', '')
        assert result is None

    def test_band_at_510_accepted(self):
        from infrastructure.scripts.enrich.content_parser import ContentParser
        parser = ContentParser(use_llm=False)
        # 7:00 AM - 3:30 PM = 510 gross: at the REQ-055 cap
        result = parser.parse('School hours: 7:00 AM - 3:30 PM', '')
        assert result is not None
        assert result.instructional_minutes == 510


# =============================================================================
# WP-3 sweep fixes (epic #480: #300 #301 #385 #386 #422 #423; #479: #284)
# =============================================================================

class TestContentParserSweepFixes:
    def _parser(self):
        from infrastructure.scripts.enrich.content_parser import ContentParser
        return ContentParser(use_llm=False)

    def test_reversed_times_rejected_not_wrapped(self):
        """#300: end-before-start must not be accepted as an overnight span."""
        parser = self._parser()
        assert parser._calculate_minutes('2:05 PM', '7:25 AM') is None
        assert parser._calculate_minutes('8:00 AM', '8:00 AM') is None

    def test_pm_start_range_matches(self):
        """#301: a PM-start range (e.g. an afternoon session) is matchable."""
        import re
        parser = self._parser()
        m = re.search(parser.TIME_RANGE_PATTERN, 'Session: 12:30 PM - 3:15 PM',
                      re.IGNORECASE)
        assert m and m.group(1).strip().upper().startswith('12:30')

    def test_until_separator_matches(self):
        """#301: 'until' joins ranges; the old char-class treated it as junk."""
        import re
        parser = self._parser()
        assert re.search(parser.TIME_RANGE_PATTERN,
                         '8:00 AM until 3:00 PM', re.IGNORECASE)

    def test_hour_25_and_minute_60_rejected(self):
        """#423: out-of-range clock values must not parse."""
        parser = self._parser()
        assert parser._parse_time('25:00') is None
        assert parser._parse_time('8:60 AM') is None
        assert parser._parse_time('13:00 PM') is None

    def test_k8_detected_as_elementary(self):
        """#386: K-8 spans no longer fall through to the 'high' default."""
        parser = self._parser()
        assert parser._detect_grade_level('lincoln k-8 school hours') == 'elementary'

    def test_modal_pair_wins_over_first_row(self):
        """#422: with 3 schools at one level, the modal (start,end) is used,
        not whichever row happened to come first."""
        parser = self._parser()
        markdown = """
        | School | Hours |
        |--------|-------|
        | Adams Elementary | 9:00 AM - 3:00 PM |
        | Baker Elementary | 8:00 AM - 2:30 PM |
        | Custer Elementary | 8:00 AM - 2:30 PM |
        """
        results = parser._parse_markdown_tables_all(markdown)
        elem = [r for r in results if r.grade_level == 'elementary']
        assert elem and elem[0].start_time == '8:00 AM'
        assert elem[0].end_time == '2:30 PM'

    def test_schools_sampled_matches_the_reported_modal_pair(self):
        """Max-effort review: schools_sampled must be the rows that actually
        SUPPORT the reported (start, end) pair, not just the first 5 rows for
        the level — those could be a different, non-modal pair entirely."""
        parser = self._parser()
        markdown = """
        | School | Hours |
        |--------|-------|
        | Adams Elementary | 9:00 AM - 3:00 PM |
        | Baker Elementary | 9:05 AM - 3:05 PM |
        | Custer Elementary | 9:10 AM - 3:10 PM |
        | Douglas Elementary | 8:00 AM - 2:30 PM |
        | Elm Elementary | 8:00 AM - 2:30 PM |
        """
        results = parser._parse_markdown_tables_all(markdown)
        elem = [r for r in results if r.grade_level == 'elementary'][0]
        assert elem.start_time == '8:00 AM'
        assert elem.end_time == '2:30 PM'
        # every sampled row must actually show the reported pair
        for raw in elem.schools_sampled:
            assert '8:00' in raw and '2:30' in raw

    def test_llm_fallback_reachable_with_default_levels(self):
        """#385: expected_levels=None must still hand missing levels to the
        LLM step (stubbed today, but the wiring must not dead-end)."""
        from unittest.mock import patch
        parser = self._parser()
        parser.use_llm = True
        with patch.object(parser, '_llm_extraction', return_value=None) as llm:
            parser.parse_all('no schedules here at all', '')
        called_levels = {c.kwargs.get('target_level') or c.args[1]
                        for c in llm.call_args_list}
        assert called_levels == {'elementary', 'middle', 'high'}


class TestCopyEnrichmentZfill:
    def test_unpadded_id_is_normalized(self):
        """#284: an unpadded caller id must be padded before queue lookup and
        bell write."""
        from infrastructure.database.enrichment_utils import copy_enrichment_to_bell_schedules
        enrichment = SimpleNamespace(
            status='completed', current_tier=1,
            tier_1_result={'total_minutes': 400, 'year': '2024-25',
                           'schedule_type': 'high_school'},
            tier_2_result=None, tier_3_result=None, tier_4_result=None,
            tier_5_result=None, district_id='0612345',
        )
        session = MagicMock()
        enr_q = MagicMock()
        enr_q.filter.return_value.first.return_value = enrichment
        bell_q = MagicMock()
        bell_q.filter_by.return_value.first.return_value = None
        session.query.side_effect = [enr_q, bell_q]

        ok, message = copy_enrichment_to_bell_schedules(session, '612345')
        assert ok, message
        added = session.add.call_args[0][0]
        assert added.district_id == '0612345'
        bell_q.filter_by.assert_called_once()
        assert bell_q.filter_by.call_args.kwargs['district_id'] == '0612345'


class TestValidateBellDataCLI:
    def _validator(self, strict=False):
        from infrastructure.scripts.utilities.validate_bell_data import BellScheduleValidator
        return BellScheduleValidator(strict=strict)

    def test_99_99_rejected(self):
        """#394: '99:99 AM' is not a valid time."""
        v = self._validator()
        assert v.validate_time_format('99:99 AM') is False
        assert v.validate_time_format('8:00 AM') is True

    def test_null_district_entry_is_error_not_crash(self):
        """#435: a null district entry reports an error."""
        v = self._validator()
        v.validate_district('0612345', None)
        assert any('must be an object' in e for e in v.errors)

    def test_reversed_times_error(self):
        """#468 (judge-confirmed): start must precede end."""
        v = self._validator()
        v.validate_grade_level('0612345', 'Test', 'high', {
            'instructional_minutes': 400,
            'start_time': '3:00 PM', 'end_time': '8:00 AM',
            'source': 'x',
        })
        assert any('must be before' in e for e in v.errors)

    def test_bounds_align_with_gross_bands(self):
        """Validator bands now mirror the DB sanity band + REQ-055 gross band
        (490 was a hard error under the pre-gross 480 cap)."""
        v = self._validator()
        severity, _ = v.validate_minutes(490, 'high')
        assert severity is None  # inside 240-510: clean pass
        severity, _ = v.validate_minutes(520, 'high')
        assert severity == 'Warning'  # outside gross band, inside DB sanity
        severity, _ = v.validate_minutes(700, 'high')
        assert severity == 'Error'  # outside the 100-600 DB sanity band

    def test_council_extraction_method_accepted(self):
        v = self._validator()
        v.validate_grade_level('0612345', 'Test', 'high', {
            'instructional_minutes': 400, 'method': 'council_extraction',
            'source': 'x',
        })
        assert not any('Invalid method' in w for w in v.warnings)
