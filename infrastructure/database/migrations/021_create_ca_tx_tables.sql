-- Create California Staff and Enrollment Tables
-- For CDE Staff Ratio and Enrollment data

CREATE TABLE IF NOT EXISTS ca_staff_data (
    nces_id VARCHAR(10) REFERENCES districts(nces_id),
    cds_code VARCHAR(10) NOT NULL,
    year VARCHAR(10) NOT NULL,
    teachers_fte NUMERIC(10, 2),
    admin_fte NUMERIC(10, 2),
    pupil_services_fte NUMERIC(10, 2),
    other_staff_fte NUMERIC(10, 2),
    data_source VARCHAR(50) DEFAULT 'cde_staff_ratios',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (nces_id, year)
);

CREATE TABLE IF NOT EXISTS ca_enrollment_data (
    nces_id VARCHAR(10) REFERENCES districts(nces_id),
    cds_code VARCHAR(10) NOT NULL,
    year VARCHAR(10) NOT NULL,
    total_k12 INTEGER,
    data_source VARCHAR(50) DEFAULT 'cde_staff_ratios',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (nces_id, year)
);

-- Create Texas Staff and Enrollment Tables
-- For TEA TAPR data

CREATE TABLE IF NOT EXISTS tx_staff_data (
    nces_id VARCHAR(10) REFERENCES districts(nces_id),
    tea_district_no VARCHAR(10) NOT NULL,
    year VARCHAR(10) NOT NULL,
    teachers_total_fte NUMERIC(10, 2),
    teachers_special_ed_fte NUMERIC(10, 2),
    teachers_regular_fte NUMERIC(10, 2),
    teachers_bilingual_fte NUMERIC(10, 2),
    teachers_gifted_fte NUMERIC(10, 2),
    data_source VARCHAR(50) DEFAULT 'tea_tapr',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (nces_id, year)
);

CREATE TABLE IF NOT EXISTS tx_enrollment_data (
    nces_id VARCHAR(10) REFERENCES districts(nces_id),
    tea_district_no VARCHAR(10) NOT NULL,
    year VARCHAR(10) NOT NULL,
    total_enrollment INTEGER,
    enrollment_pk INTEGER,
    enrollment_k INTEGER,
    enrollment_g1 INTEGER,
    enrollment_g2 INTEGER,
    enrollment_g3 INTEGER,
    enrollment_g4 INTEGER,
    enrollment_g5 INTEGER,
    enrollment_g6 INTEGER,
    enrollment_g7 INTEGER,
    enrollment_g8 INTEGER,
    enrollment_g9 INTEGER,
    enrollment_g10 INTEGER,
    enrollment_g11 INTEGER,
    enrollment_g12 INTEGER,
    enrollment_sped INTEGER,
    enrollment_ell INTEGER,
    enrollment_econ_disadvantaged INTEGER,
    data_source VARCHAR(50) DEFAULT 'tea_tapr',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (nces_id, year)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ca_staff_year ON ca_staff_data(year);
CREATE INDEX IF NOT EXISTS idx_ca_enrollment_year ON ca_enrollment_data(year);
CREATE INDEX IF NOT EXISTS idx_tx_staff_year ON tx_staff_data(year);
CREATE INDEX IF NOT EXISTS idx_tx_enrollment_year ON tx_enrollment_data(year);

-- Add comments
COMMENT ON TABLE ca_staff_data IS 'California staff data from CDE Staff Ratio files';
COMMENT ON TABLE ca_enrollment_data IS 'California enrollment data from CDE files';
COMMENT ON TABLE tx_staff_data IS 'Texas staff data from TEA TAPR reports';
COMMENT ON TABLE tx_enrollment_data IS 'Texas enrollment data from TEA TAPR reports';
