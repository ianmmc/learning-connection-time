"""DB-free tests for infrastructure/utilities/data_guards.py (the #970 / #972 generalizations)."""

import pytest

from infrastructure.utilities.data_guards import (
    DataGuardError,
    reconcile_total,
    require_labels_seen,
    require_nonempty_selection,
)


class TestReconcileTotal:
    def test_passes_within_tolerance_and_returns_receipt(self):
        r = reconcile_total(1003, 1000, label="x", n_compared=50, n_disagree=2)
        assert r.ratio == pytest.approx(1.003)
        assert (r.n_compared, r.n_disagree) == (50, 2)

    def test_exact_double_is_reported_as_the_970_signature(self):
        # The #970 shape: 24,522,548 vs 12,261,274 — exactly 2.000×
        with pytest.raises(DataGuardError, match="integer multiple.*#970"):
            reconcile_total(24_522_548, 12_261_274, label="idea child count")

    def test_exact_triple_is_also_the_signature(self):
        with pytest.raises(DataGuardError, match="3.000×"):
            reconcile_total(3000, 1000, label="x")

    def test_generic_drift_is_a_plain_tolerance_failure(self):
        with pytest.raises(DataGuardError, match="exceeds tolerance") as e:
            reconcile_total(1200, 1000, label="x")
        assert "#970" not in str(e.value)

    def test_near_but_not_exact_multiple_is_drift_not_signature(self):
        with pytest.raises(DataGuardError, match="exceeds tolerance"):
            reconcile_total(2050, 1000, label="x")

    def test_zero_or_missing_reference_fails_loud(self):
        with pytest.raises(DataGuardError, match="nothing to reconcile"):
            reconcile_total(10, 0, label="x")
        with pytest.raises(DataGuardError):
            reconcile_total(10, None, label="x")

    def test_guard_error_is_a_nonzero_system_exit(self):
        """An unguarded CLI must exit non-zero with the message, not print and continue."""
        with pytest.raises(SystemExit) as e:
            reconcile_total(2000, 1000, label="x")
        assert e.value.code.startswith("DATA GUARD:")


class TestRequireLabelsSeen:
    def test_all_present_is_silent(self):
        require_labels_seen({"a", "b"}, ["b", "a", "c"], label="x")

    def test_missing_label_names_it(self):
        with pytest.raises(DataGuardError, match=r"\['Separate School'\]"):
            require_labels_seen(
                {"Separate School", "Inside regular class less than 40% of the day"},
                ["Separate School, Age 6-21", "Inside regular class less than 40% of the day"],
                label="idea environments",
            )


class TestRequireNonemptySelection:
    def test_nonempty_is_silent(self):
        require_nonempty_selection([1], what="x", available=["2024-25"])

    def test_empty_lists_the_available_keys(self):
        with pytest.raises(DataGuardError, match=r"matched 0 rows.*2023-24"):
            require_nonempty_selection([], what="districts for 2024-25", available=["2023-24"])
