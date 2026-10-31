"""DB-free tests for the IDEA 618 / CRDC SPED baseline refresh (epic #724: #999 T1, #1000 T2, #960, #1001 T3).

Plan + acceptance properties (A1-A3):
docs/technical-notes/production-quality-control-research/2026-10-31-idea-crdc-sped-baseline-refresh-plan.md
"""

import hashlib

import pytest

from infrastructure.database.migrations.import_sped_baseline import (
    aggregate_crdc_rows,
    build_crdc_lea_baselines,
    build_state_baselines,
    parse_child_count_rows,
    read_child_count_file,
    read_personnel_file,
    safe_int,
)
from infrastructure.database.migrations.sped_baseline_profiles import (
    PROFILE_2017_18,
    PROFILE_2024_25,
    PROFILES,
    SourceFile,
    get_profile,
    verify_source,
)
from infrastructure.utilities.data_guards import DataGuardError

CC24 = PROFILE_2024_25.child_count
HEADERS_24 = ["Year", "State Name", "SEA Education Environment", "SEA Disability Category",
              "Age 3 to 5 (Early Childhood)", "Age 5 (School Age)", "Age 5 (School Age)-21", "Ages 6-21"]


def _row24(env, ec, a5, a521, a621, state="Alabama"):
    return ["2024", state, env, "All Disabilities", ec, a5, a521, a621]


def _good_rows_24():
    return [
        _row24("Inside regular class 80% or more of the day", "-", "40", "640", "600"),
        _row24("Inside regular class 40% through 79% of the day", "-", "5", "205", "200"),
        _row24("Inside regular class less than 40% of the day", "-", "3", "103", "100"),
        _row24("Separate School, School Age", "-", "2", "52", "50"),
        _row24("Residential Facility, School Age", "-", "0", "10", "10"),
        _row24("Homebound/Hospital", "-", "0", "20", "20"),
        _row24("Correctional Facilities", "-", "-", "5", "5"),
        _row24("Parentally Placed in Private Schools", "-", "0", "15", "15"),
        _row24("Total, School Age", "-", "50", "1050", "1000"),
        _row24("Separate Class", "30", "-", "-", "-"),
        _row24("Services in Regular Early Childhood Program (attend at least 10 hours)", "70", "-", "-", "-"),
        _row24("Total, Early Childhood", "100", "-", "-", "-"),
    ]


class TestChildCount2024Profile:
    """#1000: the 2024-25 'School Age' vocabulary parses on BOTH bands, each reconciled (G1)."""

    def test_both_bands_and_the_5k_count(self):
        al = parse_child_count_rows(HEADERS_24, _good_rows_24(), CC24)["AL"]
        assert al["school_age"] == {"6-21": 1000, "5-21": 1050}
        assert al["self_contained"] == {"6-21": 150, "5-21": 155}
        assert al["mainstreamed"] == {"6-21": 800, "5-21": 845}
        assert al["age_5_school_age"] == 50
        assert al["early_childhood"] == 100

    def test_each_band_is_reconciled_separately(self):
        """A 5-21 Total that does not match its own environment rows fails even when 6-21 does."""
        rows = [(_row24("Total, School Age", "-", "50", "2100", "1000") if r[2] == "Total, School Age" else r)
                for r in _good_rows_24()]
        with pytest.raises(DataGuardError, match=r"\(5-21\).*exceeds tolerance"):
            parse_child_count_rows(HEADERS_24, rows, CC24)

    def test_2017_labels_under_the_2024_profile_fail_g2(self):
        rows = [(_row24("Total, Age 6-21", "-", "50", "1050", "1000") if r[2] == "Total, School Age" else r)
                for r in _good_rows_24()]
        with pytest.raises(DataGuardError, match="Total, School Age"):
            parse_child_count_rows(HEADERS_24, rows, CC24)

    def test_unclassified_label_still_fails(self):
        rows = _good_rows_24() + [_row24("Virtual School, School Age", "-", "0", "1", "1")]
        with pytest.raises(DataGuardError, match="does not classify.*Virtual School"):
            parse_child_count_rows(HEADERS_24, rows, CC24)

    def test_suppression_marks_are_missing_not_numbers(self):
        assert safe_int("x") is None and safe_int("*") is None and safe_int("-") is None


class TestProfiles:
    def test_registry_is_keyed_by_baseline_year(self):
        assert set(PROFILES) == {"2017-18", "2024-25"}
        assert get_profile("2017-18") is PROFILE_2017_18
        with pytest.raises(DataGuardError, match="no SPED baseline profile"):
            get_profile("2019-20")

    def test_refresh_pairs_crdc_with_ccd_of_its_own_year(self):
        """#1001: the CRDC denominator is CCD membership of the CRDC's year, never another."""
        for p in PROFILES.values():
            assert p.crdc.data_year == p.ccd.data_year, p.baseline_year

    def test_no_component_is_a_covid_year(self):
        from infrastructure.utilities.school_year import COVID_EXCLUDED_YEARS
        for p in PROFILES.values():
            years = {p.personnel.source.data_year, p.child_count.source.data_year, p.crdc.data_year, p.ccd.data_year}
            assert not years & COVID_EXCLUDED_YEARS, p.baseline_year

    def test_undecided_band_refuses_to_build(self):
        """A vintage whose band is undecided (None) can be measured with an explicit band, never built
        on a default — the guard that held 2024-25 until the T5 call (#1003)."""
        import dataclasses
        undecided = dataclasses.replace(PROFILE_2024_25, school_age_band=None)
        with pytest.raises(DataGuardError, match="not decided"):
            build_state_baselines(undecided)


class TestVerifySource:
    """A2: a file whose bytes differ from the pin, or a pin that disagrees with SOURCE.md, is refused."""

    def _file(self, tmp_path, monkeypatch, body=b"a,b\n1,2\n"):
        import infrastructure.database.migrations.sped_baseline_profiles as m
        monkeypatch.setattr(m, "FEDERAL_DIR", tmp_path)
        (tmp_path / "x").mkdir()
        (tmp_path / "x" / "f.csv").write_bytes(body)
        return hashlib.sha256(body).hexdigest()

    def test_matching_pin_passes(self, tmp_path, monkeypatch):
        sha = self._file(tmp_path, monkeypatch)
        verify_source(SourceFile("x/f.csv", sha, "2024-25"))

    def test_changed_bytes_fail(self, tmp_path, monkeypatch):
        self._file(tmp_path, monkeypatch)
        with pytest.raises(DataGuardError, match="re-pin deliberately"):
            verify_source(SourceFile("x/f.csv", "0" * 64, "2024-25"))

    def test_source_md_disagreement_fails(self, tmp_path, monkeypatch):
        sha = self._file(tmp_path, monkeypatch)
        (tmp_path / "x" / "SOURCE.md").write_text(f"| file | sha256 | source |\n|---|---|---|\n| f.csv | {'1' * 64} | url |\n")
        with pytest.raises(DataGuardError, match="receipt and the code disagree"):
            verify_source(SourceFile("x/f.csv", sha, "2024-25"))

    def test_missing_file_fails(self, tmp_path, monkeypatch):
        self._file(tmp_path, monkeypatch)
        with pytest.raises(DataGuardError, match="missing"):
            verify_source(SourceFile("x/nope.csv", "0" * 64, "2024-25"))


def _crdc(lea, idea_m, idea_f, tot_m, tot_f, x="-10", name="Peabody", state="MA"):
    return {"LEAID": lea, "LEA_NAME": name, "LEA_STATE": state, "SCH_ENR_IDEA_M": idea_m, "SCH_ENR_IDEA_F": idea_f,
            "TOT_ENR_M": tot_m, "TOT_ENR_F": tot_f, "SCH_ENR_IDEA_X": x, "TOT_ENR_X": x}


class TestCrdcReserveCodes:
    """#960 / A3: no negative value reaches sped_lea_baseline; exclusion is pairwise and flagged."""

    def test_reserved_school_is_excluded_from_both_sums(self):
        leas = aggregate_crdc_rows([
            _crdc("2509360", "10", "8", "100", "90"),
            _crdc("2509360", "-9", "-9", "-9", "-9"),      # the 2023-24 shape: all four reserved
            _crdc("2509360", "5", "-5", "50", "40"),       # one reserved cell excludes the whole school
        ])["2509360"]
        assert (leas.sped_m, leas.sped_f, leas.tot_m, leas.tot_f) == (10, 8, 100, 90)
        assert (leas.schools, leas.schools_reserved) == (3, 2)

    def test_nonbinary_minus_10_is_never_read(self):
        a = aggregate_crdc_rows([_crdc("0100001", "1", "1", "10", "10", x="-10")])["0100001"]
        assert a.schools_reserved == 0 and a.tot_m + a.tot_f == 20

    def test_no_negative_reaches_the_baseline_rows(self):
        leas = aggregate_crdc_rows([
            _crdc("2509360", "-5", "-5", "-5", "-5"), _crdc("2509360", "3", "2", "40", "35"),
            _crdc("3904393", "4", "4", "-6", "-6"),
        ])
        rows = build_crdc_lea_baselines(PROFILE_2024_25, leas)
        for r in rows.values():
            for col in ("crdc_sped_enrollment_m", "crdc_sped_enrollment_f", "crdc_sped_enrollment_total",
                        "crdc_total_enrollment_m", "crdc_total_enrollment_f", "crdc_total_enrollment"):
                v = getattr(r, col)
                assert v is None or v >= 0, (r.lea_id, col, v)

    def test_fully_reserved_lea_stores_null_and_is_flagged(self):
        rows = build_crdc_lea_baselines(PROFILE_2024_25, aggregate_crdc_rows([_crdc("3904393", "4", "4", "-6", "-6")]))
        r = rows["3904393"]
        assert r.crdc_sped_enrollment_total is None and r.crdc_total_enrollment is None
        assert r.crdc_schools_reserved == 1 and "no valid school" in r.data_quality_notes

    def test_partial_lea_ratio_uses_the_same_schools_denominator(self):
        """Pairwise: CCD counts the excluded schools too, so a partial LEA divides by CRDC's own total."""
        rows = build_crdc_lea_baselines(PROFILE_2024_25, aggregate_crdc_rows([
            _crdc("2509360", "10", "10", "100", "100"), _crdc("2509360", "-9", "-9", "-9", "-9"),
        ]))
        r = rows["2509360"]
        r.ccd_total_enrollment = 400          # all schools, including the excluded one
        r.calculate_ratio()
        assert float(r.ratio_sped_proportion) == pytest.approx(20 / 200)
        assert r.crdc_year == r.ccd_year == "2023-24" and r.baseline_year == "2024-25"

    def test_full_coverage_lea_keeps_the_ccd_denominator(self):
        rows = build_crdc_lea_baselines(PROFILE_2017_18, aggregate_crdc_rows([_crdc("0100001", "10", "10", "100", "100")]))
        r = rows["0100001"]
        r.ccd_total_enrollment = 250
        r.calculate_ratio()
        assert float(r.ratio_sped_proportion) == pytest.approx(20 / 250)


# ------------------------------------------------------------------------------ real files (gitignored)
def _have(*profiles):
    return all(s.path.exists() for p in profiles
               for s in (p.personnel.source, p.child_count.source, p.crdc, p.ccd))


@pytest.mark.skipif(not _have(PROFILE_2017_18), reason="data/raw is gitignored; real-file checks run where present")
class TestReal2017Files:
    def test_a2_2017_18_parse_is_unchanged(self):
        """A2: 56 states; Σ 6-21 6,122,215; self-contained 985,809 — the pre-refactor numbers."""
        cc = read_child_count_file(PROFILE_2017_18.child_count)
        assert len(cc) == 56
        assert sum(t["school_age"]["6-21"] for t in cc.values()) == 6_122_215
        assert sum(t["self_contained"]["6-21"] for t in cc.values()) == 985_809
        assert all(t["age_5_school_age"] is None for t in cc.values())
        assert len(read_personnel_file(PROFILE_2017_18.personnel)) == 56

    def test_pins_match_the_bytes(self):
        p = PROFILE_2017_18
        for s in (p.personnel.source, p.child_count.source, p.crdc, p.ccd):
            verify_source(s)


@pytest.mark.skipif(not _have(PROFILE_2024_25), reason="data/raw is gitignored; real-file checks run where present")
class TestReal2024Files:
    def test_child_count_reconciles_on_both_bands(self):
        """Measured 2026-10-31: 5-21 7,582,496 · 6-21 7,233,721 · 5K 348,775 (4.6%)."""
        cc = read_child_count_file(CC24)
        assert len(cc) == 56
        assert sum(t["school_age"]["5-21"] for t in cc.values()) == 7_582_496
        assert sum(t["school_age"]["6-21"] for t in cc.values()) == 7_233_721
        assert sum(t["age_5_school_age"] or 0 for t in cc.values()) == 348_775

    def test_personnel_2023_24_loads_every_reporting_state(self):
        fte = read_personnel_file(PROFILE_2024_25.personnel)
        with_teachers = [s for s, v in fte.items() if v.get("teachers_total")]
        assert len(with_teachers) >= 50, sorted(set(fte) - set(with_teachers))

    def test_both_bands_build(self):
        for band in ("6-21", "5-21"):
            rows = build_state_baselines(PROFILE_2024_25, band=band)
            assert {r.school_age_band for r in rows.values()} == {band}
            assert {(r.personnel_year, r.child_count_year) for r in rows.values()} == {("2023-24", "2024-25")}

    def test_pins_match_the_bytes(self):
        p = PROFILE_2024_25
        for s in (p.personnel.source, p.child_count.source, p.crdc, p.ccd):
            verify_source(s)


class TestCrdcCcdReconciliation:
    """#1001 / A3: CRDC M+F vs CCD membership, on the measured tolerance — not a guess."""

    def _rows(self, pairs, reserved=0):
        from infrastructure.database.models import SpedLeaBaseline
        return {f"{i:07d}": SpedLeaBaseline(lea_id=f"{i:07d}", crdc_total_enrollment=c, ccd_total_enrollment=d,
                                            crdc_schools_reserved=reserved)
                for i, (c, d) in enumerate(pairs)}

    def test_measured_shape_passes(self):
        from infrastructure.database.migrations.import_sped_baseline import reconcile_crdc_with_ccd
        r = reconcile_crdc_with_ccd(PROFILE_2024_25, self._rows([(979, 1000)] * 99 + [(500, 1000)]))
        assert r.n_compared == 100 and r.n_disagree == 1

    def test_aggregate_drift_beyond_the_measured_tolerance_fails(self):
        from infrastructure.database.migrations.import_sped_baseline import reconcile_crdc_with_ccd
        with pytest.raises(DataGuardError, match="exceeds tolerance"):
            reconcile_crdc_with_ccd(PROFILE_2024_25, self._rows([(950, 1000)] * 100))

    def test_too_many_lea_outliers_fail_even_when_the_aggregate_holds(self):
        from infrastructure.database.migrations.import_sped_baseline import reconcile_crdc_with_ccd
        rows = self._rows([(1300, 1000)] * 10 + [(700, 1000)] * 10 + [(1000, 1000)] * 80)
        with pytest.raises(DataGuardError, match="rows disagree"):
            reconcile_crdc_with_ccd(PROFILE_2024_25, rows)

    def test_partial_leas_are_not_compared(self):
        from infrastructure.database.migrations.import_sped_baseline import reconcile_crdc_with_ccd
        rows = self._rows([(1000, 1000)] * 10)
        rows.update({k + "p": v for k, v in self._rows([(100, 1000)] * 10, reserved=1).items()})
        assert reconcile_crdc_with_ccd(PROFILE_2024_25, rows).n_compared == 10


@pytest.mark.skipif(not _have(PROFILE_2017_18, PROFILE_2024_25), reason="data/raw is gitignored")
@pytest.mark.parametrize("profile", [PROFILE_2017_18, PROFILE_2024_25], ids=lambda p: p.baseline_year)
def test_real_crdc_passes_its_reconciliation(profile):
    """The guard passes on both real vintages (and the measured numbers it was set from hold)."""
    import csv
    from infrastructure.database.migrations import import_sped_baseline as m
    with open(profile.crdc.path, encoding="utf-8-sig", newline="") as f:
        leas = m.build_crdc_lea_baselines(profile, m.aggregate_crdc_rows(csv.DictReader(f)))
    for lea_id, (n, _, _) in m.read_ccd_lea_totals(profile.ccd.path).items():
        if lea_id in leas:
            leas[lea_id].ccd_total_enrollment = n
    r = m.reconcile_crdc_with_ccd(profile, leas)
    assert 0.97 < r.ratio < 1.0 and r.n_compared > 15_000


def test_schema_sql_trigger_is_migration_030s():
    """#1003: the temporal trigger is declared twice (schema.sql for a fresh DB, migration 030 for a
    migrated one). They drifted before (schema.sql still carried the span<=3 body) — pin them equal."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    mig = (root / "infrastructure/database/migrations/030_temporal_window_sped_ratio_years.sql").read_text()
    sch = (root / "infrastructure/database/schema.sql").read_text()
    body = mig[mig.index("DECLARE"):mig.index("$$ LANGUAGE plpgsql;")]
    fn = sch[sch.index("CREATE FUNCTION public.validate_lct_temporal()"):]
    assert body in fn[:fn.index("$$;")], "schema.sql's validate_lct_temporal differs from migration 030's"
    assert "component_years -> 'sped_ratio'" in body


def test_profiles_carry_the_t5_decisions():
    """#1003 (Ian, 2026-10-31): 5-21 band, CRDC-own denominator; the applied vintage is 2024-25."""
    from infrastructure.utilities.school_year import SPED_BASELINE_YEAR
    assert SPED_BASELINE_YEAR == "2024-25" and SPED_BASELINE_YEAR in PROFILES
    assert PROFILE_2024_25.school_age_band == "5-21" and PROFILE_2024_25.lea_denominator == "crdc"
    assert PROFILE_2017_18.lea_denominator == "ccd"
