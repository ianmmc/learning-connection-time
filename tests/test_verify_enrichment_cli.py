"""CLI behavior of infrastructure/scripts/verify_enrichment.py.

Pure-mock tests (no DB) — kept out of test_enrichment_verification.py, whose
module-level integration mark would drop them from the DB-free CI lane.
"""

import json
from unittest.mock import Mock, patch

import pytest


class TestVerifyEnrichmentExitCodes:
    """Issue #469: verify_enrichment must exit non-zero on failure in BOTH
    output modes — the old code only exited in the human-readable branch, so
    CI running --json always saw exit 0."""

    def _args(self, **overrides):
        args = Mock()
        args.json = True
        args.year = "2026-27"
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    def test_claim_validation_exits_1_in_json_mode_on_alert(self):
        from infrastructure.scripts import verify_enrichment as ve

        with patch.object(ve, 'get_enrichment_summary',
                          return_value={'enriched_districts': 10}), \
             patch.object(ve, 'detect_count_discrepancy',
                          return_value={'has_discrepancy': True, 'alert': True,
                                        'discrepancy_percent': 90.0,
                                        'severity': 'critical', 'message': 'off'}):
            args = self._args(validate_claim=100)
            with pytest.raises(SystemExit) as exc:
                ve.run_claim_validation(Mock(), args)
            assert exc.value.code == 1

    def test_claim_validation_json_includes_status(self, capsys):
        from infrastructure.scripts import verify_enrichment as ve

        with patch.object(ve, 'get_enrichment_summary',
                          return_value={'enriched_districts': 100}), \
             patch.object(ve, 'detect_count_discrepancy',
                          return_value={'has_discrepancy': False, 'alert': False,
                                        'discrepancy_percent': 0.0,
                                        'severity': 'none', 'message': 'ok'}):
            ve.run_claim_validation(Mock(), self._args(validate_claim=100))
        assert json.loads(capsys.readouterr().out)['status'] == 'valid'

    def test_full_verification_exits_1_in_json_mode_on_violations(self):
        from infrastructure.scripts import verify_enrichment as ve

        with patch.object(ve, 'generate_handoff_report', return_value={}), \
             patch.object(ve, 'check_audit_integrity',
                          return_value={'violations': [{'type': 'orphan',
                                                        'message': 'x'}],
                                        'integrity_status': 'fail',
                                        'completeness_percent': 50.0}), \
             patch.object(ve, 'find_lineage_gaps', return_value=[]):
            with pytest.raises(SystemExit) as exc:
                ve.run_full_verification(Mock(), self._args())
            assert exc.value.code == 1

    def test_full_verification_json_timestamps_are_timezone_aware(self, capsys):
        """Issue #395: verified_at must carry a UTC offset, not a naive stamp."""
        from infrastructure.scripts import verify_enrichment as ve

        with patch.object(ve, 'generate_handoff_report', return_value={}), \
             patch.object(ve, 'check_audit_integrity',
                          return_value={'violations': [],
                                        'integrity_status': 'pass',
                                        'completeness_percent': 100.0}), \
             patch.object(ve, 'find_lineage_gaps', return_value=[]):
            ve.run_full_verification(Mock(), self._args())
        out = json.loads(capsys.readouterr().out)
        assert out['status'] == 'pass'
        assert '+00:00' in out['verified_at']
