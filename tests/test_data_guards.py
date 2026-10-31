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
        # The #970 shape on the importer's 56 states: Σ(environment rows + Total row) 12,244,430 vs the
        # Total row 6,122,215 — exactly 2.000× (the file's own US aggregate row is skipped by STATE_ABBR)
        with pytest.raises(DataGuardError, match="integer multiple.*#970"):
            reconcile_total(12_244_430, 6_122_215, label="idea child count")

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


class TestReconcileTotalRowCap:
    """#976: the aggregate tolerance cannot see a dropped small category; the row cap can."""

    def test_rows_over_the_cap_fail_even_when_the_aggregate_is_within_tolerance(self):
        # dropping 'Grade 13' from the CCD mapping: ratio 0.99996, 150 LEAs differ
        with pytest.raises(DataGuardError, match="150 of 18,499 rows disagree.*#976"):
            reconcile_total(99_996, 100_000, label="x", n_compared=18_499, n_disagree=150, max_disagree=0)

    def test_rows_at_or_under_the_cap_pass(self):
        assert reconcile_total(1000, 1000, label="x", n_compared=10, n_disagree=0, max_disagree=0).n_disagree == 0
        assert reconcile_total(1000, 1000, label="x", n_compared=10, n_disagree=2, max_disagree=2).n_disagree == 2

    def test_no_cap_keeps_the_count_as_bookkeeping(self):
        assert reconcile_total(1000, 1000, label="x", n_compared=10, n_disagree=7).n_disagree == 7


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


class TestNonFiniteInputs:
    """#994: NaN / inf / NA must be a labelled DataGuardError, never a bare ValueError/OverflowError/
    TypeError that an `except Exception` loader would swallow — and never a silent pass."""

    @pytest.mark.parametrize("component, reference", [
        (float("nan"), 1000), (1000, float("nan")), (float("inf"), 1000), (1000, float("inf")),
    ])
    def test_non_finite_floats_fail_as_a_guard(self, component, reference):
        with pytest.raises(DataGuardError, match="not a finite number"):
            reconcile_total(component, reference, label="x")

    def test_decimal_nan_fails_as_a_guard(self):
        from decimal import Decimal
        with pytest.raises(DataGuardError, match="not a finite number"):
            reconcile_total(Decimal("NaN"), 1000, label="x")

    def test_pandas_na_fails_as_a_guard(self):
        pd = pytest.importorskip("pandas")
        with pytest.raises(DataGuardError, match="not a finite number"):
            reconcile_total(pd.NA, 1000, label="x")


class TestDataGuardErrorRoundTrips:
    """#994: pickle / copy replayed the already-prefixed args and doubled 'DATA GUARD: '."""

    def test_pickle_keeps_one_prefix(self):
        import pickle
        e = pickle.loads(pickle.dumps(DataGuardError("x")))
        assert str(e) == "DATA GUARD: x" and e.message == "x"

    def test_copy_keeps_one_prefix(self):
        import copy
        assert str(copy.copy(DataGuardError("x"))) == "DATA GUARD: x"
        assert str(copy.deepcopy(DataGuardError("x"))) == "DATA GUARD: x"


class TestSelectionApi:
    """#995: `available` is evaluated only on failure; membership has its own helper; a non-Sized
    input is a clear programmer error, not a TypeError from len()."""

    def test_callable_available_is_not_called_on_success(self):
        def boom():
            raise AssertionError("available evaluated on a healthy run")
        require_nonempty_selection([1], what="x", available=boom)

    def test_callable_available_is_called_on_failure(self):
        with pytest.raises(DataGuardError, match=r"matched 0 rows.*2023-24"):
            require_nonempty_selection([], what="x", available=lambda: ["2023-24"])

    def test_non_sized_input_is_named(self):
        with pytest.raises(TypeError, match="needs a sized collection"):
            require_nonempty_selection((i for i in []), what="x", available=[])

    def test_year_carried_passes_and_fails_with_the_carried_years(self):
        from infrastructure.utilities.data_guards import require_year_carried
        require_year_carried("2024-25", ["2023-24", "2024-25"], what="ma_staff_data")
        with pytest.raises(DataGuardError, match=r"ma_staff_data.*2024-25.*2025-26"):
            require_year_carried("2024-25", ["2025-26"], what="ma_staff_data")

    def test_year_carried_accepts_a_callable(self):
        from infrastructure.utilities.data_guards import require_year_carried
        with pytest.raises(DataGuardError, match="2025-26"):
            require_year_carried("2024-25", lambda: ["2025-26"], what="t")


class TestDistinctYearsHelper:
    """#995: the ONE 'which years does this table carry' spelling; identifiers are interpolated, so
    anything but a plain identifier is refused before any SQL is built."""

    class _Session:
        def __init__(self, rows):
            self.rows, self.sql, self.params = rows, None, None

        def execute(self, stmt, params):
            self.sql, self.params = str(stmt), params
            return iter(self.rows)

    def test_sorted_non_empty_and_bound_where(self):
        from infrastructure.database.queries import distinct_years
        s = self._Session([("2024-25",), (None,), ("2023-24",), ("",)])
        assert distinct_years(s, "staff_counts", "source_year", where="data_source = :src",
                              params={"src": "nces_ccd"}) == ["2023-24", "2024-25"]
        assert s.sql == "SELECT DISTINCT source_year FROM staff_counts WHERE data_source = :src"
        assert s.params == {"src": "nces_ccd"}

    @pytest.mark.parametrize("table, column", [("t; drop table x", "year"), ("t", "year, 1"), ("T", "y")])
    def test_non_identifiers_are_refused(self, table, column):
        from infrastructure.database.queries import distinct_years
        with pytest.raises(ValueError, match="not a plain SQL identifier"):
            distinct_years(self._Session([]), table, column)
