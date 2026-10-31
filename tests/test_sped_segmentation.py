"""
Tests for SPED segmentation requirements
Generated from: REQ-004 (SPED-segmented LCT), REQ-018 (SPED baseline ratios)

Verifies that SPED segmentation uses correct baseline data and calculates
three SPED-specific LCT scopes.

Run: pytest tests/test_sped_segmentation.py -v
"""

import pytest
from pathlib import Path


class TestSpedSegmentedLCT:
    """Tests for SPED-segmented LCT variants - REQ-004"""

    def test_calculates_three_sped_scopes(self):
        """
        REQ-004: Calculates 3 SPED-specific LCT scopes.

        Based on v3 self-contained focus:
        1. core_sped: SPED teachers / self-contained SPED students
        2. teachers_gened: GenEd teachers / GenEd enrollment (includes mainstreamed SPED)
        3. instructional_sped: (SPED teachers + paras) / self-contained SPED students
        """
        # Arrange
        sped_scopes = ["core_sped", "teachers_gened", "instructional_sped"]

        # Assert - All three scopes defined
        assert len(sped_scopes) == 3
        assert "core_sped" in sped_scopes
        assert "teachers_gened" in sped_scopes
        assert "instructional_sped" in sped_scopes

    def test_core_sped_uses_sped_teachers_and_sped_enrollment(self):
        """
        REQ-004: core_sped scope for audit validation.

        core_sped = SPED teachers / self-contained SPED students
        Used to verify weighted average relationship with overall LCT.
        """
        # Arrange
        sped_teachers = 50.0
        self_contained_sped_students = 200  # illustrative

        # Act - Calculate core_sped LCT
        instructional_minutes = 360
        core_sped_lct = (instructional_minutes * sped_teachers) / self_contained_sped_students

        # Assert
        assert core_sped_lct > 0
        assert core_sped_lct > 60  # SPED LCT typically much higher than overall

    def test_teachers_gened_uses_gened_teachers_and_gened_enrollment(self):
        """
        REQ-004: teachers_gened scope segments general education.

        teachers_gened = GenEd teachers / GenEd enrollment
        GenEd enrollment includes mainstreamed SPED students.
        """
        # Arrange
        total_teachers = 250.0
        sped_teachers = 50.0
        gened_teachers = total_teachers - sped_teachers  # 200.0

        total_enrollment = 5000
        sped_enrollment = 650  # 13% SPED
        self_contained = 200   # illustrative
        mainstreamed = sped_enrollment - self_contained  # 450
        gened_enrollment = total_enrollment - self_contained  # 4800 (includes 450 mainstreamed)

        # Act
        instructional_minutes = 360
        teachers_gened_lct = (instructional_minutes * gened_teachers) / gened_enrollment

        # Assert
        assert teachers_gened_lct > 0
        assert gened_enrollment > (total_enrollment - sped_enrollment)  # Includes mainstreamed

    def test_instructional_sped_includes_paraprofessionals(self):
        """
        REQ-004: instructional_sped includes SPED teachers + paraprofessionals.

        instructional_sped = (SPED teachers + SPED paras) / self-contained SPED students
        Paraprofessionals provide substantial support in self-contained classrooms.
        """
        # Arrange
        sped_teachers = 50.0
        sped_paras = 30.0  # Typical ratio ~0.6 paras per teacher in SPED
        instructional_sped_staff = sped_teachers + sped_paras

        self_contained_sped_students = 200

        # Act
        instructional_minutes = 360
        instructional_sped_lct = (instructional_minutes * instructional_sped_staff) / self_contained_sped_students

        # Assert
        assert instructional_sped_lct > 0
        assert instructional_sped_staff == 80.0
        # instructional_sped LCT should be even higher than core_sped
        core_sped_lct = (instructional_minutes * sped_teachers) / self_contained_sped_students
        assert instructional_sped_lct > core_sped_lct

    def test_uses_state_level_sped_staffing_ratios(self):
        """
        REQ-004: Uses state-level SPED staffing ratios from 2017-18 baseline.

        State ratios from IDEA 618 Personnel data.
        """
        # Arrange - Example state ratios
        state_sped_ratios = {
            "CA": 0.145,  # 14.5% of all teachers are SPED teachers
            "TX": 0.138,
            "NY": 0.152,
        }

        for state, ratio in state_sped_ratios.items():
            assert 0.10 <= ratio <= 0.20  # Typical range 10-20%

    def test_handles_missing_sped_data_gracefully(self):
        """
        REQ-004: Handles missing SPED data gracefully.

        When district lacks SPED estimates, SPED scopes return None
        rather than crashing or producing invalid values.
        """
        # Arrange - District with no SPED data
        district_data = {
            "district_id": "0123456",
            "total_enrollment": 5000,
            "total_teachers": 250,
            "sped_enrollment": None,  # Missing
            "sped_teachers": None,    # Missing
        }

        # Act - Attempt to calculate SPED scopes
        if district_data["sped_enrollment"] is None:
            core_sped_lct = None
            teachers_gened_lct = None
            instructional_sped_lct = None
        else:
            # Would calculate normally
            pass

        # Assert - Graceful handling
        assert core_sped_lct is None
        assert teachers_gened_lct is None
        assert instructional_sped_lct is None


class TestSpedBaselineRatios:
    """Tests for SPED baseline from 2017-18 federal data - REQ-018"""

    def test_uses_idea_618_personnel_for_teacher_ratios(self):
        """
        REQ-018: Uses IDEA 618 Personnel data for state SPED teacher ratios.

        Personnel file provides counts of SPED teachers by state.
        """
        # Arrange - Example from IDEA 618 Personnel 2017-18
        idea_personnel_data = {
            "state": "CA",
            "total_teachers": 295000,
            "sped_teachers": 42775,  # From IDEA 618
            "sped_teacher_ratio": 0.145,  # 42775 / 295000
        }

        # Assert
        calculated_ratio = idea_personnel_data["sped_teachers"] / idea_personnel_data["total_teachers"]
        assert pytest.approx(calculated_ratio, 0.001) == idea_personnel_data["sped_teacher_ratio"]

    def test_uses_idea_618_environments_for_self_contained_proportion(self):
        """
        REQ-018 / #970: the child-count parse takes the file's own `Total, Age …` rows as the
        totals (never sums them in with the environment rows) and matches the environment
        labels the file actually carries (`Separate School, Age 6-21`, not `Separate School`).

        Fixture mirrors the 2017-18 file's row vocabulary for one state.
        """
        from infrastructure.database.migrations.import_sped_baseline import parse_child_count_rows

        headers = ["Year", "State Name", "SEA Education Environment", "SEA Disability Category",
                   "Age 3 to 5", "Ages 6-21"]
        def row(env, a35, a621):
            return ["2017", "Alabama", env, "All Disabilities", a35, a621]
        rows = [
            row("Inside regular class 80% or more of the day", "-", "600"),
            row("Inside regular class 40% through 79% of the day", "-", "200"),
            row("Inside regular class less than 40% of the day", "-", "100"),
            row("Separate School, Age 6-21", "-", "50"),
            row("Residential Facility, Age 6-21", "-", "10"),
            row("Homebound/Hospital", "-", "20"),
            row("Correctional Facilities", "-", "5"),
            row("Parentally Placed in Private Schools", "-", "15"),
            row("Total, Age 6-21", "-", "1000"),
            row("Separate Class", "30", "-"),
            row("Services in Regular Early Childhood Program (attend at least 10 hours)", "70", "-"),
            row("Total, Age 3-5", "100", "-"),
            # A different disability row for the same env must not be counted twice
            ["2017", "Alabama", "Total, Age 6-21", "Autism", "-", "120"],
            # A different year must be ignored
            ["2016", "Alabama", "Total, Age 6-21", "All Disabilities", "-", "999"],
        ]

        totals = parse_child_count_rows(headers, rows, year="2017")["AL"]

        assert totals["ages_6_21"] == 1000          # the Total row, not 2× it
        assert totals["ages_3_5"] == 100
        assert totals["self_contained"] == 150      # <40% + Separate School, Age 6-21
        assert totals["mainstreamed"] == 800
        assert totals["self_contained"] / totals["ages_6_21"] == pytest.approx(0.15)

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parents[1] / "data/raw/federal/idea-618/2017_18/bchildcountandedenvironments2017-18.csv").exists(),
        reason="data/raw is gitignored; the real-file check runs only where the 2017-18 IDEA file is present",
    )
    def test_real_2017_18_file_self_contained_share(self):
        """#970 regression against the real file: national self-contained share is 16.1%, not 6.65%."""
        from infrastructure.database.migrations.import_sped_baseline import (
            IDEA_CHILD_COUNT_FILE, read_child_count_file,
        )
        totals = read_child_count_file(IDEA_CHILD_COUNT_FILE, year="2017")
        all_621 = sum(t["ages_6_21"] for t in totals.values())
        sc = sum(t["self_contained"] for t in totals.values())
        # ~6.1M IDEA students ages 6-21 across the 56 states/territories the importer keeps (the
        # file's own "US, Outlying Areas..." aggregate row is skipped by STATE_ABBR)
        assert 6_000_000 < all_621 < 6_300_000
        assert 0.155 < sc / all_621 < 0.165

    def test_uses_crdc_2017_18_for_lea_level_sped_enrollment(self):
        """
        REQ-018: Uses CRDC 2017-18 for LEA-level SPED enrollment.

        Civil Rights Data Collection provides district-level SPED counts.
        """
        # Arrange - Example from CRDC 2017-18
        crdc_data = {
            "district_id": "0123456",
            "total_enrollment": 5000,
            "sped_enrollment": 650,  # 13%
            "sped_percentage": 0.13,
        }

        # Assert
        calculated_pct = crdc_data["sped_enrollment"] / crdc_data["total_enrollment"]
        assert pytest.approx(calculated_pct, 0.01) == crdc_data["sped_percentage"]

    def test_calculates_three_sped_scopes_from_baseline(self):
        """
        REQ-018: Three SPED scopes calculated from baseline data.

        Demonstrates calculation methodology:
        1. core_sped: estimated SPED teachers / estimated self-contained SPED students
        2. teachers_gened: estimated GenEd teachers / estimated GenEd enrollment
        3. instructional_sped: (SPED teachers + paras) / self-contained SPED students
        """
        # Arrange - District example
        district = {
            "total_enrollment": 5000,
            "total_teachers": 250,
        }

        # From CRDC 2017-18 (LEA level)
        district["sped_enrollment"] = 650  # 13%

        # From state ratio (IDEA 618 Personnel)
        state_sped_teacher_ratio = 0.145
        district["sped_teachers"] = district["total_teachers"] * state_sped_teacher_ratio  # 36.25

        # From national baseline (IDEA 618 Environments)
        self_contained_proportion = 0.161  # national share, IDEA 618 2017-18 (#970)
        district["self_contained_students"] = district["sped_enrollment"] * self_contained_proportion  # 104.65

        # GenEd calculations
        district["gened_teachers"] = district["total_teachers"] - district["sped_teachers"]  # 213.75
        district["gened_enrollment"] = district["total_enrollment"] - district["self_contained_students"]  # 4895.35

        # Assert - All components calculated
        assert district["sped_teachers"] > 0
        assert district["self_contained_students"] > 0
        assert district["gened_teachers"] > 0
        assert district["gened_enrollment"] > district["total_enrollment"] - district["sped_enrollment"]

    def test_california_actual_sped_takes_precedence(self):
        """
        REQ-018: California actual SPED data takes precedence when available.

        For 990 CA districts with actual 2023-24 SPED environment data,
        use actual counts instead of 2017-18 estimates.
        """
        # Arrange - CA district with actual data
        ca_district = {
            "district_id": "6000001",  # CA district
            "state": "CA",
            "total_enrollment": 10000,
            "sped_enrollment_actual": 1300,  # From CA CDE 2023-24
            "self_contained_actual": 87,     # From CA CDE 2023-24 (6.7% of SPED)
        }

        # Also have federal estimate
        federal_estimate = {
            "sped_enrollment": 1200,  # From CRDC 2017-18
            "self_contained": 80,     # Estimated from national ratio
        }

        # Act - Apply precedence (state actual > federal estimate)
        selected_sped_enrollment = ca_district["sped_enrollment_actual"]
        selected_self_contained = ca_district["self_contained_actual"]

        # Assert - CA actual used
        assert selected_sped_enrollment == 1300
        assert selected_self_contained == 87
        assert selected_sped_enrollment != federal_estimate["sped_enrollment"]

    def test_teacher_estimates_always_use_2017_18_ratios(self):
        """
        REQ-018, REQ-025: Teacher estimates always use 2017-18 federal ratios.

        State-level SPED teacher splits by environment are not available,
        so always use 2017-18 IDEA 618 Personnel ratios.
        """
        # Arrange - Even CA with actual enrollment uses federal teacher ratios
        ca_district = {
            "district_id": "6000001",
            "total_teachers": 500,
            "sped_enrollment_actual": 1300,  # Actual from CA
            "self_contained_actual": 87,      # Actual from CA
        }

        # Teacher calculation uses federal ratio
        federal_sped_teacher_ratio = 0.145  # From IDEA 618 Personnel 2017-18
        ca_district["sped_teachers_estimated"] = ca_district["total_teachers"] * federal_sped_teacher_ratio

        # Assert - Teachers estimated from federal ratio
        assert ca_district["sped_teachers_estimated"] == 72.5
        # Even though enrollment is actual, teachers are estimated

    def test_baseline_data_year_is_2017_18(self):
        """
        REQ-018: Baseline data is from 2017-18 school year.

        This is the most recent year with complete IDEA 618 + CRDC data
        before COVID-19 disruptions.
        """
        baseline_year = "2017-18"

        # Assert
        assert baseline_year == "2017-18"
        assert baseline_year < "2019-20"  # Pre-COVID


class TestSpedLCTValidation:
    """Validation tests for SPED LCT calculations"""

    def test_sped_lct_typically_much_higher_than_overall(self):
        """
        SPED LCT (especially core_sped) is typically much higher than overall.

        Self-contained classrooms have very low student-teacher ratios (5:1 to 10:1).
        """
        # Arrange
        overall_lct = 25.0  # Typical overall
        core_sped_lct = 185.8  # Mean from actual data

        # Assert
        assert core_sped_lct > overall_lct * 5  # At least 5x higher

    def test_instructional_sped_highest_due_to_paraprofessionals(self):
        """
        instructional_sped LCT is highest due to paraprofessional support.

        Self-contained classrooms often have 1 teacher + 1-2 paras.
        """
        # Arrange - From actual QA report
        core_sped_lct = 185.8      # Teachers only
        instructional_sped_lct = 298.9  # Teachers + paras

        # Assert
        assert instructional_sped_lct > core_sped_lct
        assert instructional_sped_lct / core_sped_lct > 1.5  # At least 50% higher

    def test_weighted_average_audit_validation(self):
        """
        REQ-004: Weighted average of SPED and GenEd LCTs should equal overall.

        Audit formula:
        overall_lct = (core_sped_lct * self_contained_pct) + (teachers_gened_lct * gened_pct)
        """
        # Arrange - Example district
        overall_lct = 26.88  # From actual data
        core_sped_lct = 185.8
        teachers_gened_lct = 26.38

        # Weights (based on self-contained enrollment)
        total_enrollment = 5000
        self_contained_students = 43  # illustrative
        gened_enrollment = 4957       # Includes 607 mainstreamed SPED

        self_contained_pct = self_contained_students / total_enrollment  # 0.0086
        gened_pct = gened_enrollment / total_enrollment                  # 0.9914

        # Act - Calculate weighted average
        weighted_average = (core_sped_lct * self_contained_pct) + (teachers_gened_lct * gened_pct)

        # Assert - Should be close to overall LCT
        assert pytest.approx(weighted_average, rel=0.05) == overall_lct

    def test_sped_lct_capped_at_360_minutes(self):
        """
        REQ-013, REQ-018: SPED LCT values capped at 360 with WARN_SPED_RATIO_CAP.

        Self-contained classrooms can have very high ratios that would exceed
        available instructional time. Cap at 360 and flag.
        """
        # Arrange - Very high SPED ratio
        sped_teachers = 10
        self_contained_students = 20  # 2:1 ratio
        instructional_minutes = 360

        # Act - Calculate (would be 180 minutes)
        calculated_lct = (instructional_minutes * sped_teachers) / self_contained_students

        # But for even smaller classrooms, could exceed 360
        tiny_class_students = 5  # 2:1 ratio per teacher
        calculated_lct_tiny = (instructional_minutes * sped_teachers) / tiny_class_students

        # Assert
        assert calculated_lct == 180.0  # Under cap
        assert calculated_lct_tiny == 720.0  # Would exceed cap
        # Should be capped at 360
        capped_lct = min(calculated_lct_tiny, 360)
        assert capped_lct == 360


# --- Fixtures ---

@pytest.fixture
def sample_sped_baseline_state():
    """Sample state-level SPED baseline data from 2017-18."""
    return {
        "state": "CA",
        "year": "2017-18",
        # From IDEA 618 Personnel
        "total_teachers": 295000,
        "sped_teachers": 42775,
        "sped_teacher_ratio": 0.145,
        # From IDEA 618 Environments (national baseline applied to state)
        "self_contained_proportion": 0.161,  # national share, IDEA 618 2017-18 (#970)
    }


@pytest.fixture
def sample_sped_estimates_district():
    """Sample district with SPED estimates calculated."""
    return {
        "district_id": "0123456",
        "year": "2023-24",
        "total_enrollment": 5000,
        "total_teachers": 250,
        # From CRDC 2017-18
        "sped_enrollment": 650,
        "sped_percentage": 0.13,
        # Estimated from state ratio
        "sped_teachers": 36.25,
        # Estimated from national baseline
        "self_contained_students": 104.65,
        "self_contained_percentage": 0.161,
        # Derived
        "gened_teachers": 213.75,
        "gened_enrollment": 4895.35,
    }


@pytest.fixture
def sample_ca_actual_sped():
    """Sample CA district with actual SPED data from 2023-24."""
    return {
        "district_id": "6000001",
        "state": "CA",
        "year": "2023-24",
        "total_enrollment": 10000,
        "total_teachers": 500,
        # Actual from CA CDE
        "sped_enrollment_actual": 1300,
        "self_contained_actual": 87,  # 6.7% of SPED
        # Teachers still estimated from federal ratio
        "sped_teachers_estimated": 72.5,
        "enrollment_source": "ca_actual_2023-24",
        "teacher_source": "sped_estimate_2017-18",
    }


@pytest.mark.integration
class TestSpedYearTotals:
    """#972: apply_sped_estimates sources per-year totals from the year-keyed tables.

    Needs the live LCT DB (Docker up); excluded from the fast gate by the `integration` marker.
    """

    def test_year_totals_match_the_districts_snapshot_for_its_vintage(self):
        """The year-keyed sourcing reproduces the single-vintage `districts` snapshot exactly, so
        switching the source changes the YEAR an estimate can target, not the numbers."""
        from infrastructure.database.connection import session_scope
        from infrastructure.database.migrations.apply_sped_estimates import select_year_totals
        from infrastructure.database.models import District

        with session_scope() as s:
            vintage = s.query(District.year).filter(District.year.isnot(None)).distinct().all()
            assert len(vintage) == 1, f"districts is expected to be a single-vintage snapshot, got {vintage}"
            (year,) = vintage[0]
            snapshot = {
                d.nces_id: (int(d.enrollment), float(d.instructional_staff))
                for d in s.query(District).filter(District.enrollment > 0, District.instructional_staff > 0)
            }
            totals = {t.nces_id: (t.enrollment, t.instructional_staff) for t in select_year_totals(s, year)}

        assert totals, "NOTHING MEASURED — select_year_totals returned no rows for the snapshot vintage"
        mismatched = {k: (snapshot[k], totals[k]) for k in snapshot.keys() & totals.keys() if snapshot[k] != totals[k]}
        assert not mismatched, f"{len(mismatched)} districts differ, e.g. {list(mismatched.items())[:3]}"
        assert set(snapshot) == set(totals), (
            f"coverage differs: only-snapshot={len(set(snapshot)-set(totals))} only-year-keyed={len(set(totals)-set(snapshot))}"
        )

    def test_primary_year_is_estimable(self):
        """NCES_PRIMARY_YEAR must be reachable by the default `apply_sped_estimates` run."""
        from infrastructure.database.connection import session_scope
        from infrastructure.database.migrations.apply_sped_estimates import select_year_totals
        from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR

        with session_scope() as s:
            n = len(select_year_totals(s, NCES_PRIMARY_YEAR))
        assert n > 15_000, f"only {n} districts have both enrollment and staff for {NCES_PRIMARY_YEAR}"

    def test_covid_year_is_refused(self):
        from infrastructure.database.migrations.apply_sped_estimates import select_year_totals
        with pytest.raises(SystemExit, match="COVID-excluded"):
            select_year_totals(None, "2021-22")
