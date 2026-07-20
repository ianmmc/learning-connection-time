"""WP-5 sweep fixes over the shared utility modules (epic #480).

- #436 common.setup_logging idempotence
- #317/#396 nces_cds_crosswalk.bulk_cds_to_nces empty input + single-pass normalize
- #314/#433 district_lookup NaN + regex-injection hardening
"""

import logging
from unittest.mock import MagicMock

import pandas as pd

from infrastructure.utilities.common import setup_logging
from infrastructure.utilities.nces_cds_crosswalk import bulk_cds_to_nces
from infrastructure.scripts.utilities.district_lookup import (
    format_output,
    lookup_by_name,
    search_districts,
)


class TestSetupLoggingIdempotent:
    def test_repeat_calls_do_not_stack_handlers(self):
        """#436: N calls must leave one console handler, not N."""
        root = logging.getLogger()
        saved = root.handlers[:]
        try:
            setup_logging()
            setup_logging()
            setup_logging()
            assert len(root.handlers) == 1
        finally:
            for h in root.handlers[:]:
                root.removeHandler(h)
            for h in saved:
                root.addHandler(h)


class TestBulkCdsToNces:
    def test_empty_input_returns_empty_not_sql_error(self):
        """#317: no codes → {} without touching the DB."""
        session = MagicMock()
        assert bulk_cds_to_nces([], session) == {}
        session.execute.assert_not_called()

    def test_maps_by_normalized_code_once(self):
        """#396: result keyed by original codes; lookup via one normalization."""
        session = MagicMock()
        result_proxy = MagicMock()
        result_proxy.fetchall.return_value = [('0161119', '0612345')]
        session.execute.return_value = result_proxy
        # 14-digit CDS collapses to the 7-digit district code
        mapping = bulk_cds_to_nces(['01611190000000'], session)
        assert mapping == {'01611190000000': '0612345'}


def _df():
    return pd.DataFrame([
        {'district_id': '0612345', 'district_name': 'Test Unified',
         'state': 'CA', 'enrollment_total': float('nan')},
        {'district_id': '0698765', 'district_name': 'Bracket [K-8] District',
         'state': 'CA', 'enrollment_total': 1000.0},
    ])


class TestDistrictLookupHardening:
    def test_nan_enrollment_prints_unknown_not_crash(self, capsys):
        """#314: NaN enrollment must not raise ValueError."""
        format_output(_df().iloc[[0]])
        assert 'Enrollment: Unknown' in capsys.readouterr().out

    def test_bracket_search_term_no_regex_crash(self):
        """#433: '[' in a search term is a literal, not a regex error."""
        result = search_districts(_df(), '[K-8]')
        assert len(result) == 1
        assert result.iloc[0]['district_id'] == '0698765'

    def test_lookup_contains_literal(self):
        result = lookup_by_name(_df(), 'Bracket [K-8]', fuzzy=False)
        assert len(result) == 1
