# Learning Connection Time Analysis - 2023-24

## Generated: 2025-12-19 22:53:18

This directory contains publication-ready datasets for sharing and discussion.

## Files in This Directory


### districts_2023_24_nces.csv
**Normalized District Data**
- Standardized district information
- Enrollment and staff counts
- Before LCT calculation (all districts, unfiltered)

### districts_2023_24_nces_with_lct_summary.txt
**Summary Statistics**
- Overall statistics for valid districts
- State-by-state averages
- Distribution information

### districts_2023_24_nces_with_lct_valid.csv
**LCT Analysis Results - Publication Ready** ✨
- **VALIDATED DISTRICTS ONLY** - Data quality filters applied
- Excludes districts with: zero enrollment, zero staff, impossible ratios
- Includes: LCT minutes/hours, student-teacher ratios, percentiles, categories
- Ready for: Presentations, policy discussions, public sharing
- **Use this file for all external communications**

### districts_2023_24_nces_with_lct_valid_validation_report.txt
**Data Quality Validation Report**
- How many districts were filtered and why
- Validation criteria applied
- Data quality statistics
- Transparency documentation for methodology


## Data Source
- **NCES Common Core of Data**: 2023-24 school year
- **Directory**: District identification and characteristics
- **Membership**: Student enrollment counts
- **Staff**: Teacher and staff FTE counts

## Methodology
- See: `docs/METHODOLOGY.md` for LCT calculation details
- See: `docs/BELL_SCHEDULE_SAMPLING_METHODOLOGY.md` for enrichment methodology

## Usage Notes

### For Presentations and Public Sharing
**Use the `*_with_lct_valid.csv` file** - This contains only validated districts that passed all data quality checks. This is the publication-ready dataset.

### For Quick Reference
Check the `*_summary.txt` file for overall statistics and distributions.

### For Transparency
Review the `*_validation_report.txt` to see what data was filtered out and why. This supports methodological transparency in discussions.

### For Validation
Compare the normalized data (`*_nces.csv`) with the LCT results to verify calculations.

## Key Metrics in LCT File

- **lct_minutes**: Learning Connection Time in minutes per student per day
- **lct_hours**: LCT converted to hours
- **student_teacher_ratio**: Traditional metric for comparison
- **lct_percentile**: Where this district ranks (0-100)
- **lct_category**: Qualitative category (Very Low, Low, Moderate, High, Very High)

## Next Steps

1. **Review summary statistics** in the summary.txt file
2. **Open CSV in spreadsheet** for detailed district analysis
3. **Filter/sort by state or LCT** to find patterns
4. **Compare districts** to identify equity gaps
5. **Create visualizations** to support policy discussions

## Contact

For questions about methodology or data quality, see project documentation in the main repository.

---

**Project**: Learning Connection Time Analysis
**Mission**: Reframing student-teacher ratios into tangible equity metrics
**Part of**: "Reducing the Ratio" educational equity initiative
