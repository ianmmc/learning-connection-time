"""Audit-layer behavior of infrastructure/database/verification.py.

DB-free regression tests for the epic #479 sweep fixes (WP-2):
- #414 exact Poisson CI at small counts
- #294 orphan-lineage check actually implemented
- dual entity_id conventions accepted by gap/orphan detection
- #293 validate_date_range single-query shape
- #291/#413 OverrideTracker commit flag + count consistency
- #459/#460 plausibility-validation input hardening
- #292 sanitizer preserves hyphens
- #373 non-string date claim handled
"""

from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.database import verification as v


class TestConfidenceInterval:
    def test_small_count_uses_exact_poisson(self):
        """#414: k=5 → exact 95% CI ≈ [1.6, 11.7]; normal approx gave [0, 10]."""
        lower, upper = v._calculate_confidence_interval(5, 0.95)
        assert lower == 1
        assert upper == 12

    def test_small_count_upper_wider_than_normal_approx(self):
        for k in (1, 3, 10, 29):
            _, upper = v._calculate_confidence_interval(k, 0.95)
            normal_upper = k + 1.96 * (k ** 0.5)
            assert upper >= normal_upper, f"k={k}: exact upper must be >= normal"

    def test_large_count_keeps_normal_approx(self):
        lower, upper = v._calculate_confidence_interval(100, 0.95)
        assert lower == int(100 - 1.96 * 10)
        assert upper == 120

    def test_zero_and_negative(self):
        assert v._calculate_confidence_interval(0, 0.95) == (0, 3)
        assert v._calculate_confidence_interval(-1) == (0, 0)


BellRow = namedtuple('BellRow', 'id district_id year grade_level')


class TestOrphanAndGapDetection:
    def _session_with(self, bells, lineage_ids):
        session = MagicMock()

        def query_side_effect(*cols):
            q = MagicMock()
            colnames = {getattr(c, 'key', str(c)) for c in cols}
            if 'entity_id' in colnames:
                q.filter.return_value.all.return_value = [(e,) for e in lineage_ids]
            else:
                q.all.return_value = bells
                q.filter.return_value.all.return_value = bells
            return q

        session.query.side_effect = query_side_effect
        return session

    def test_orphan_check_fires(self):
        """#294: lineage rows matching no bell row are counted as orphans."""
        bells = [BellRow(1, '0600001', '2024-25', 'high')]
        session = self._session_with(bells, ['1', '999', 'gone/2020-21/high'])
        result = v.check_audit_integrity(session)
        orphan = [x for x in result['violations'] if x['type'] == 'ORPHANED_LINEAGE']
        assert orphan and orphan[0]['count'] == 2

    def test_both_entity_id_conventions_accepted(self):
        """A bell row is covered by numeric id OR composite key lineage."""
        bells = [
            BellRow(1, '0600001', '2024-25', 'high'),      # covered numerically
            BellRow(2, '0600002', '2024-25', 'middle'),    # covered by composite
            BellRow(3, '0600003', '2024-25', 'elementary'),  # uncovered
        ]
        lineage = ['1', '0600002/2024-25/middle']
        session = self._session_with(bells, lineage)

        completeness = v.verify_audit_completeness(session)
        assert completeness['with_lineage'] == 2
        assert completeness['missing_lineage'] == 1

    def test_find_lineage_gaps_composite_covered(self):
        bells = [BellRow(2, '0600002', '2024-25', 'middle')]
        rows = [MagicMock(id=2, district_id='0600002', created_at=None,
                          year='2024-25', grade_level='middle')]
        session = MagicMock()

        def query_side_effect(*cols):
            q = MagicMock()
            colnames = {getattr(c, 'key', str(c)) for c in cols}
            if 'entity_id' in colnames:
                q.filter.return_value.all.return_value = [('0600002/2024-25/middle',)]
            else:
                q.all.return_value = rows
            return q

        session.query.side_effect = query_side_effect
        assert v.find_lineage_gaps(session) == []


class TestDateRangeSingleQuery:
    def test_no_per_day_queries(self):
        """#293: one GROUP BY query regardless of range width."""
        from datetime import date
        session = MagicMock()
        row = MagicMock()
        row.date = date(2026, 1, 2)
        row.count = 4
        session.query.return_value.filter.return_value.group_by.return_value.all.return_value = [row]

        result = v.validate_date_range(session, date(2026, 1, 1), date(2026, 1, 10))

        assert session.query.call_count == 1
        assert result['daily_counts']['2026-01-02'] == 4
        assert result['daily_counts']['2026-01-01'] == 0
        assert len(result['daily_counts']) == 10
        assert '2026-01-02' not in result['gap_dates']
        assert result['has_gaps'] is True


class TestOverrideTracker:
    def test_commit_false_flushes(self):
        """#291: commit=False must flush, never commit the caller's session."""
        session = MagicMock()
        tracker = v.OverrideTracker()
        tracker.log_override(session, 'count_discrepancy', 'reason', commit=False)
        session.flush.assert_called_once()
        session.commit.assert_not_called()

    def test_commit_default_commits(self):
        session = MagicMock()
        v.OverrideTracker().log_override(session, 'count_discrepancy', 'reason')
        session.commit.assert_called_once()

    def test_count_not_incremented_on_failed_commit(self):
        """#413: a failed write must not desync the in-memory count."""
        session = MagicMock()
        session.commit.side_effect = RuntimeError('db down')
        tracker = v.OverrideTracker()
        with pytest.raises(RuntimeError):
            tracker.log_override(session, 'count_discrepancy', 'reason')
        assert tracker.override_count == 0

    def test_entity_ids_unique_across_rapid_calls(self):
        """#412: uuid suffix keeps ids unique even at identical timestamps."""
        session = MagicMock()
        tracker = v.OverrideTracker()
        ids = {
            tracker.log_override(session, 'other', 'a detailed reason here',
                                 commit=False)['override_id']
            for _ in range(5)
        }
        assert len(ids) == 5


class TestPlausibilityHardening:
    def test_missing_grade_level_clear_error(self):
        """#459: absent grade_level gets a required-field error, not ''-invalid."""
        result = v.validate_schedule_plausibility({'instructional_minutes': 400})
        assert 'grade_level is required' in result['errors']

    def test_non_string_times_error_not_crash(self):
        """#460: numeric start/end times are invalid input, not AttributeError."""
        result = v.validate_schedule_plausibility({
            'start_time': 800, 'end_time': 1500,
            'grade_level': 'high', 'instructional_minutes': 400,
        })
        assert any('Invalid start_time' in e for e in result['errors'])
        assert any('Invalid end_time' in e for e in result['errors'])


class TestSanitizeReason:
    def test_hyphens_preserved(self):
        """#292: 'non-compliant' must survive sanitization."""
        assert v._sanitize_reason('district is non-compliant') == 'district is non-compliant'

    def test_sql_keywords_still_blocked(self):
        assert 'DROP' not in v._sanitize_reason('DROP TABLE districts')

    def test_semicolons_still_stripped(self):
        assert ';' not in v._sanitize_reason('a; b')

    def test_sql_comment_syntax_stripped(self):
        """Max-effort review regression: preserving hyphens for 'non-compliant'
        (#292) let SQL comment syntax '--' survive intact through the
        character whitelist, since '-' alone is now an allowed char. Must
        still be removed as its own token."""
        assert '--' not in v._sanitize_reason('a -- DROP TABLE x')
        assert '--' not in v._sanitize_reason('Normal text; DROP TABLE users;--')

    def test_639_whitelist_cannot_reform_comment_token(self):
        """#639: the whitelist deletes a non-whitelisted char BETWEEN two hyphens; the '--' removal
        must run AFTER it (order, not iteration) so the token can't re-form in the output."""
        assert '--' not in v._sanitize_reason('a-\x00-b')          # \x00 removed → would join 'a--b'
        assert '--' not in v._sanitize_reason('x-;-y DROP-\x07-z')
        assert '--' not in v._sanitize_reason('-' * 7)             # hyphen runs reduce to ≤1
        assert v._sanitize_reason('non-compliant') == 'non-compliant'   # #292 still holds

    def test_hyphens_still_preserved_after_comment_fix(self):
        """The comment-stripping fix must not regress #292 itself."""
        assert v._sanitize_reason('non-compliant district') == 'non-compliant district'


class TestHandoffClaimDate:
    def test_non_string_date_is_mismatch_not_crash(self):
        """#373: a non-string date claim reports invalid format."""
        session = MagicMock()
        session.query.return_value.filter.return_value.count.return_value = 0
        session.query.return_value.scalar.return_value = 0
        result = v.validate_handoff_claims(
            {'date': 20260101, 'districts_added': [], 'total_enriched': 0},
            session=session,
        )
        assert any('Invalid date format' in m for m in result['mismatches'])
