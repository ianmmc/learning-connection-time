# Michigan SEA Integration - January 18, 2026

## Summary

Successfully integrated Michigan Department of Education (MDE) data as the 6th state in the SEA integration framework. This completes 1 of the 3 remaining Tier 1 states identified in the December 2025 assessment.

## Completed Work

### 1. Data Acquisition
- **Manual download required**: Michigan's website uses CDN protection (Cloudflare) that blocks automated downloads
- **Files obtained**:
  - `mi_staffing_2023_24.xlsx` - Teacher FTE, SPED instructional staff (891 districts)
  - `Spring_2024_Headcount.xlsx` - K-12 enrollment by grade and demographics (880 districts)
  - `mi_special_ed_2023_24.xlsx` - IEP counts, SPED percentages (882 districts)

### 2. Test File Created
- **File**: `tests/test_michigan_integration.py`
- **Configuration**:
  - State: Michigan (MI)
  - Agency: MDE (Michigan Department of Education)
  - Data year: 2023-24
  - District code format: 5-digit (e.g., 82015 for Detroit)
  - Expected districts: 5 (Detroit, Utica, Dearborn, Ann Arbor, Plymouth-Canton)
- **Tests**: 27 tests (25 passing, 2 skipped)
  - 6 Michigan-specific validations
  - 21 standard SEA integration tests (from mixins)

### 3. Import Script Created
- **File**: `infrastructure/database/migrations/import_michigan_data.py`
- **Tables created**:
  - `mi_district_identifiers` - District codes and names
  - `mi_staff_data` - Teacher FTE, SPED staff, instructional aides
  - `mi_enrollment_data` - K-12 enrollment by grade, demographics
  - `mi_special_ed_data` - IEP counts, SPED percentages
- **Data imported**:
  - 836 district identifiers
  - 836 staff records
  - 835 enrollment records
  - 837 special education records
  - 55 districts skipped (not in NCES crosswalk)

### 4. Documentation Updated
- **SEA_INTEGRATION_GUIDE.md**:
  - Added Michigan to District ID Crosswalk table
  - Added Michigan to Implemented SEA Integrations table
  - Added Michigan files to SEA Data Files section
  - Updated test coverage table (283 total tests)
- **sea_import_utils.py**:
  - Added Michigan to SEA_ID_FORMATS registry

## Key District Data

| District | NCES ID | Enrollment | Teachers | Expected LCT |
|----------|---------|------------|----------|--------------|
| Detroit Public Schools | 2601103 | 47,581 | 2,429.56 | 15.3 min |
| Utica Community Schools | 2634470 | 25,303 | 1,148.25 | 13.6 min |
| Dearborn City SD | 2611600 | 19,524 | 1,134.18 | 17.4 min |
| Ann Arbor Public Schools | 2602820 | 16,918 | 1,048.53 | 18.6 min |
| Plymouth-Canton CS | 2628560 | 16,051 | 800.97 | 15.0 min |

**Detroit highlights:**
- Largest Michigan district (3rd largest in nation)
- 47,581 students, 2,429.56 teachers
- 7,132 students with IEP (14.7% SPED rate)
- 197.4 SPED instructional staff

## Technical Notes

### File Structure
- **Header rows**: All Michigan files use 4-row headers (use `skiprows=4`)
- **Missing values**: Michigan uses `'.'` for missing values (handled by `safe_float()`)
- **Column names**:
  - Staffing: `DCODE`, `DNAME`, `TEACHER`, `SE_INSTR`, `INST_AID`, `INST_SUP`
  - Enrollment: `District Code`, `District Name`, `tot_all`, `k_totl`, `g1_totl`, ... `g12_totl`
  - Special Ed: `DCODE.1`, `DNAME`, `StudwI E P` (IEP count), `SpEd%`

### Enrollment File Discovery
- Correct sheet name: `"Fall Dist K-12 Total Data"`
- Contains 40 columns including grade-level breakdowns
- Demographic breakdowns by race/ethnicity and gender
- Total enrollment in `tot_all` column

### Crosswalk
- Michigan crosswalk already populated in `state_district_crosswalk` table (882 entries)
- Source: NCES CCD `ST_LEAID` field
- All 5 test districts found in crosswalk

## Test Results

**Before import**: 25 passed, 2 skipped
**After import**: 25 passed, 2 skipped

**Total SEA integration tests**: 283 passing, 10 skipped across 6 states

## Lessons Learned

### 1. CDN Protection
- Michigan's website uses Cloudflare/CDN protection
- Automated downloads (curl, wget) fail with HTTP 403 Access Denied
- Manual browser download required
- **Recommendation**: Document this pattern for PA, VA, MA integrations

### 2. Multi-Sheet Excel Files
- Michigan enrollment file has 66+ sheets
- Important to identify correct sheet name early
- Use `pd.ExcelFile(path).sheet_names` to discover available sheets
- District-level data in `"Fall Dist K-12 Total Data"` sheet

### 3. Reusable Framework Success
- SEA integration base class worked perfectly
- No modifications needed to base class or mixins
- All 21 standard tests passed immediately
- Only 6 Michigan-specific tests needed

### 4. Import Script Pattern
- Illinois import script was excellent template
- Copy-paste-adapt approach very efficient
- Shared utilities (`sea_import_utils.py`) eliminated code duplication
- Total development time: ~2 hours including data discovery

## Next Steps

### Immediate (Tier 1 States Remaining)
1. **Pennsylvania** - PIMS data system
2. **Virginia** - VDOE data
3. **Massachusetts** - DESE data

### Expected Challenges
- PA: Large state, may have CDN protection
- VA: Need to research data portal access
- MA: Similar size to Michigan, likely straightforward

### Documentation Needs
- Create CDN bypass guide for manual downloads
- Document multi-sheet Excel file discovery pattern
- Add state-specific data source URLs to guide

## Files Created/Modified

**Created:**
- `tests/test_michigan_integration.py` (27 tests)
- `infrastructure/database/migrations/import_michigan_data.py`
- `docs/chat-history/michigan_integration_2026-01-18.md` (this file)

**Modified:**
- `docs/SEA_INTEGRATION_GUIDE.md` (added Michigan to tables)
- `infrastructure/database/migrations/sea_import_utils.py` (added MI to SEA_ID_FORMATS)

**Database tables created:**
- `mi_district_identifiers`
- `mi_staff_data`
- `mi_enrollment_data`
- `mi_special_ed_data`

## References

- **MDE Data Portal**: https://www.michigan.gov/cepi/MISchoolData
- **Staffing file**: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2023-24/Staffing_2023-24_01062025.xlsx
- **Enrollment file**: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2023-24/Spring_2024_Headcount.xlsx
- **Special Ed file**: https://www.michigan.gov/cepi/-/media/Project/Websites/cepi/MISchoolData/2023-24/Special_Education_Count_Fall_2023.xlsx

---

*Completed: January 18, 2026*
*Integration Time: ~2 hours*
*Test Coverage: 27 tests (25 passing)*
*Districts Imported: 836 (95% coverage)*
