-- ============================================================================
-- Migration 033: CCD school-file staffing + the band-scope teacher attribution
-- Date: 2026-11-01
-- Issue: #1038 (#1022 T4; #1017 phase 2, epic #724)
--
-- The source and the stored derivation for the school-file band scopes
-- (teachers_band_elementary / _middle / _high). Design of record:
-- docs/technical-notes/production-quality-control-research/2026-11-01-school-file-band-scopes-plan.md
--
--   ccd_school_staffing          school x year, loaded VERBATIM from ccd_sch_029 / 052 / 059.
--                                Missing or suppressed stays NULL with its flag, never 0 (REQ-165).
--   lea_school_staffing          district x year: the LEA-level reconciliation (the LEA-file teacher
--                                total, the school sum, LEA-only FTE left unattributed (D5), and the
--                                reported Pre-K FTE that the Pre-K rule allocates (D3)).
--   lea_band_staffing            district x year x band: the band's grade span, coverage, and whether
--                                it clears the publication floor (D4).
--   lea_grade_teacher_fte        district x year x band x grade: the attributed teacher FTE and the
--                                membership of the SAME schools. Band is in the key because, under
--                                school bands (D1/D2), one grade can sit in two bands (grade 6 in a
--                                K-6 elementary and in a 6-8 middle of the same district).
--
-- The three lea_* tables are DERIVED and regenerable from ccd_school_staffing + ccd_lea_059;
-- `method_version` names the derivation that wrote them. Not precious state.
-- No FK to districts: the CCD files carry LEAs the districts table does not.
-- ============================================================================

CREATE TABLE IF NOT EXISTS ccd_school_staffing (
    ncessch             VARCHAR(12) NOT NULL,
    source_year         VARCHAR(10) NOT NULL,          -- '2024-25'
    leaid               VARCHAR(10) NOT NULL,
    state               VARCHAR(2),
    school_name         TEXT,
    sy_status           VARCHAR(40),                   -- 029 SY_STATUS_TEXT
    sch_type            VARCHAR(40),                   -- 029 SCH_TYPE_TEXT
    level               VARCHAR(40),                   -- 029 LEVEL
    gslo                VARCHAR(4),
    gshi                VARCHAR(4),
    teachers_fte        NUMERIC(10, 2),                -- 059 TEACHERS; NULL when not reported
    teachers_dms_flag   VARCHAR(30),                   -- 059 DMS_FLAG (Reported / Missing / Not applicable / ...)
    memb_pk             INTEGER,                       -- 052 'Subtotal 4 - By Grade'; NULL when absent
    memb_kg             INTEGER,
    memb_01             INTEGER,
    memb_02             INTEGER,
    memb_03             INTEGER,
    memb_04             INTEGER,
    memb_05             INTEGER,
    memb_06             INTEGER,
    memb_07             INTEGER,
    memb_08             INTEGER,
    memb_09             INTEGER,
    memb_10             INTEGER,
    memb_11             INTEGER,
    memb_12             INTEGER,
    memb_13             INTEGER,
    memb_ug             INTEGER,
    membership_flags    JSONB,                         -- {grade: DMS_FLAG} for every grade row not 'Reported'
    src_029_sha256      VARCHAR(64) NOT NULL,
    src_052_sha256      VARCHAR(64) NOT NULL,
    src_059_sha256      VARCHAR(64) NOT NULL,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_ccd_school_staffing PRIMARY KEY (ncessch, source_year),
    CONSTRAINT chk_css_teachers_fte CHECK (teachers_fte IS NULL OR teachers_fte >= 0)
);

CREATE INDEX IF NOT EXISTS idx_ccd_school_staffing_lea ON ccd_school_staffing (leaid, source_year);

CREATE TABLE IF NOT EXISTS lea_school_staffing (
    leaid                   VARCHAR(10) NOT NULL,
    source_year             VARCHAR(10) NOT NULL,
    lea_teachers_fte        NUMERIC(10, 2),            -- ccd_lea_059 'Teachers'
    school_teachers_fte     NUMERIC(10, 2) NOT NULL,   -- sum over the district's reporting schools
    unattributed_fte        NUMERIC(10, 2),            -- lea - school sum (D5); NULL when the LEA total is absent
    pk_teachers_reported    NUMERIC(10, 2),            -- ccd_lea_059 'Pre-kindergarten Teachers' (D3)
    pk_teachers_dms_flag    VARCHAR(30),
    pk_membership           INTEGER NOT NULL,          -- sum of memb_pk over the reporting schools
    pk_zero_with_students   BOOLEAN NOT NULL,          -- D3 flag: PK students, reported PK FTE = 0
    method_version          VARCHAR(20) NOT NULL,
    derived_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_lea_school_staffing PRIMARY KEY (leaid, source_year)
);

CREATE TABLE IF NOT EXISTS lea_band_staffing (
    leaid                   VARCHAR(10) NOT NULL,
    source_year             VARCHAR(10) NOT NULL,
    band                    VARCHAR(20) NOT NULL,
    grade_lo                VARCHAR(4) NOT NULL,       -- the span the band's schools serve, K-12 range (D1 cond. 3)
    grade_hi                VARCHAR(4) NOT NULL,
    school_count            INTEGER NOT NULL,          -- reporting schools contributing to the band
    excluded_school_count   INTEGER NOT NULL,          -- schools in the band with no teacher count (D4)
    membership_reporting    INTEGER NOT NULL,          -- K-12 membership of the reporting schools
    membership_total        INTEGER NOT NULL,          -- K-12 membership of every school in the band
    coverage                NUMERIC(6, 5) NOT NULL,    -- membership_reporting / membership_total
    pk_fte_removed          NUMERIC(12, 4) NOT NULL,   -- the reported Pre-K FTE allocated to this band (D3)
    published               BOOLEAN NOT NULL,          -- coverage >= the floor (0.90, D4)
    method_version          VARCHAR(20) NOT NULL,
    derived_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_lea_band_staffing PRIMARY KEY (leaid, source_year, band),
    CONSTRAINT chk_lbs_band CHECK (band IN ('elementary', 'middle', 'high')),
    CONSTRAINT chk_lbs_coverage CHECK (coverage >= 0 AND coverage <= 1)
);

CREATE TABLE IF NOT EXISTS lea_grade_teacher_fte (
    leaid                   VARCHAR(10) NOT NULL,
    source_year             VARCHAR(10) NOT NULL,
    band                    VARCHAR(20) NOT NULL,
    grade                   VARCHAR(4) NOT NULL,       -- 'KG','01'..'12' (PK removed; 13 not an LCT grade)
    teacher_fte             NUMERIC(12, 4) NOT NULL,   -- attributed, Pre-K removed
    membership              INTEGER NOT NULL,          -- the same schools' membership in this grade
    school_count            INTEGER NOT NULL,
    method_version          VARCHAR(20) NOT NULL,
    derived_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_lea_grade_teacher_fte PRIMARY KEY (leaid, source_year, band, grade),
    CONSTRAINT chk_lgtf_band CHECK (band IN ('elementary', 'middle', 'high')),
    CONSTRAINT chk_lgtf_grade CHECK (grade IN ('KG','01','02','03','04','05','06','07','08','09','10','11','12')),
    CONSTRAINT chk_lgtf_fte CHECK (teacher_fte >= 0)
);

COMMENT ON TABLE ccd_school_staffing IS
'CCD school files (029 directory, 052 membership, 059 staff) loaded verbatim per school x year (#1038). Missing or suppressed values are NULL with their DMS flag, never 0. The source for the school-file band scopes (#1022).';
COMMENT ON TABLE lea_grade_teacher_fte IS
'Teacher FTE attributed to (district, band, grade) from ccd_school_staffing: single-band schools whole, combined schools split by grade membership, the LEA-reported Pre-K FTE removed. Membership is from the same schools. Derived; method_version names the derivation (#1022 T6).';
