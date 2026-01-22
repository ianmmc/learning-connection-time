#!/usr/bin/env python3
"""
Generate State Education Agency (SEA) Integration Scaffolding

This script helps bootstrap new state integrations by:
1. Analyzing Excel/CSV files to discover column names
2. Suggesting column mappings for staff and enrollment data
3. Generating test file scaffolding
4. Generating import script scaffolding

All processing is done locally using pandas/openpyxl - no API calls required.

Usage:
    # Analyze a state data file
    python generate_sea_integration.py --analyze data/raw/state/ohio/ohio_staff.xlsx

    # Generate scaffolding for a new state
    python generate_sea_integration.py --state OH --agency ODE --year 2023-24

    # Full workflow with data file analysis
    python generate_sea_integration.py --state OH --agency ODE --analyze data/raw/state/ohio/

Examples:
    python generate_sea_integration.py --state MA --agency DESE --year 2023-24
    python generate_sea_integration.py --analyze data/raw/state/massachusetts/staff.xlsx
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import re

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# State name mapping
STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia',
}

# Common column name patterns for staff data
STAFF_COLUMN_PATTERNS = {
    'district_id': [r'district.*id', r'lea.*id', r'agency.*id', r'dist.*code', r'leaid'],
    'district_name': [r'district.*name', r'lea.*name', r'agency.*name'],
    'total_teachers': [r'total.*teacher', r'teacher.*fte', r'teachers$', r'certified.*teacher'],
    'total_staff': [r'total.*staff', r'all.*staff', r'instructional.*staff'],
    'enrollment': [r'enrollment', r'students', r'membership', r'adm'],
}

# Common column name patterns for enrollment data
ENROLLMENT_COLUMN_PATTERNS = {
    'district_id': [r'district.*id', r'lea.*id', r'agency.*id', r'dist.*code'],
    'district_name': [r'district.*name', r'lea.*name', r'agency.*name'],
    'total_enrollment': [r'total.*enrollment', r'total.*students', r'membership', r'adm'],
    'k12_enrollment': [r'k-?12', r'grades.*k.*12'],
    'sped_enrollment': [r'sped', r'special.*ed', r'iep', r'disability'],
}


def analyze_excel_file(file_path: Path) -> Dict:
    """
    Analyze an Excel file and return column information.

    Uses pandas/openpyxl for local processing.
    """
    try:
        import pandas as pd
    except ImportError:
        print("Error: pandas is required. Install with: pip install pandas openpyxl")
        sys.exit(1)

    results = {
        'file': str(file_path),
        'sheets': [],
        'suggested_mappings': {},
    }

    if file_path.suffix.lower() in ['.xlsx', '.xls']:
        xl = pd.ExcelFile(file_path)
        sheet_names = xl.sheet_names

        for sheet_name in sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=5)
            columns = list(df.columns)

            sheet_info = {
                'name': sheet_name,
                'columns': columns,
                'row_count': len(pd.read_excel(file_path, sheet_name=sheet_name)),
                'sample_data': df.head(3).to_dict(),
            }
            results['sheets'].append(sheet_info)

            # Suggest column mappings
            mappings = suggest_column_mappings(columns)
            if mappings:
                results['suggested_mappings'][sheet_name] = mappings

    elif file_path.suffix.lower() == '.csv':
        df = pd.read_csv(file_path, nrows=5)
        columns = list(df.columns)

        results['sheets'].append({
            'name': 'CSV',
            'columns': columns,
            'row_count': len(pd.read_csv(file_path)),
            'sample_data': df.head(3).to_dict(),
        })

        mappings = suggest_column_mappings(columns)
        if mappings:
            results['suggested_mappings']['CSV'] = mappings

    return results


def suggest_column_mappings(columns: List[str]) -> Dict[str, str]:
    """
    Suggest column mappings based on common patterns.
    """
    mappings = {}
    columns_lower = [c.lower() for c in columns]

    # Check staff patterns
    for target, patterns in STAFF_COLUMN_PATTERNS.items():
        for pattern in patterns:
            for i, col in enumerate(columns_lower):
                if re.search(pattern, col, re.IGNORECASE):
                    mappings[target] = columns[i]
                    break
            if target in mappings:
                break

    # Check enrollment patterns if staff patterns didn't match
    for target, patterns in ENROLLMENT_COLUMN_PATTERNS.items():
        if target not in mappings:
            for pattern in patterns:
                for i, col in enumerate(columns_lower):
                    if re.search(pattern, col, re.IGNORECASE):
                        mappings[target] = columns[i]
                        break
                if target in mappings:
                    break

    return mappings


def generate_test_file(state_code: str, agency_name: str, year: str) -> str:
    """
    Generate test file scaffolding for a new state.
    """
    state_name = STATE_NAMES.get(state_code, state_code)
    state_lower = state_name.lower().replace(' ', '_')

    template = f'''"""
Integration Tests for {state_name} State Education Agency ({agency_name}) Data.

These tests validate the {state_name} state data integration against actual {agency_name} files.
Inherits from SEAIntegrationTestBase to leverage common patterns.

IMPORTANT: These tests require actual {agency_name} data files in:
  data/raw/state/{state_lower}/

Run with: pytest tests/test_{state_lower}_integration.py -v
"""

import pytest
from pathlib import Path
from typing import Dict, Optional, Any
import pandas as pd

from tests.test_sea_integration_base import (
    SEAIntegrationTestBase,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEADataQualityTests,
    SEARegressionPreventionTests,
    calculate_lct,
)


# =============================================================================
# {state_code}-SPECIFIC CONFIGURATION
# =============================================================================

{agency_name}_DATA_DIR = Path("data/raw/state/{state_lower}")
{agency_name}_FILES_PRESENT = {agency_name}_DATA_DIR.exists() and any({agency_name}_DATA_DIR.glob("*.*"))

pytestmark = pytest.mark.skipif(
    not {agency_name}_FILES_PRESENT,
    reason="{agency_name} data files not present in data/raw/state/{state_lower}/"
)


class {state_name.replace(' ', '')}SEAConfig(SEAIntegrationTestBase):
    """{state_name}-specific SEA configuration."""

    STATE_CODE = "{state_code}"
    STATE_NAME = "{state_name}"
    SEA_NAME = "{agency_name}"
    DATA_YEAR = "{year}"

    # {state_name} default instructional minutes (update based on state requirements)
    DEFAULT_INSTRUCTIONAL_MINUTES = 360

    # NCES LEAID -> State District ID mapping
    # TODO: Populate with actual crosswalk data from state_district_crosswalk table
    CROSSWALK = {{
        # "NCES_ID": "STATE_DISTRICT_ID",
    }}

    # Expected values from {agency_name} {year} data files
    # TODO: Populate with actual values from largest districts
    EXPECTED_DISTRICTS = {{
        # "DISTRICT_NAME": {{
        #     "state_district_id": "XXX",
        #     "nces_leaid": "XXXXXXX",
        #     "enrollment": 50000,
        #     "total_teachers": 2500,
        #     "expected_lct_teachers_only": 18.0,
        #     "instructional_minutes": 360,
        # }},
    }}

    def get_data_files(self) -> Dict[str, Path]:
        """Return paths to {agency_name} data files."""
        return {{
            # TODO: Update with actual file names
            # "staff": {agency_name}_DATA_DIR / "{state_lower}_staff_{year.replace('-', '_')}.xlsx",
            # "enrollment": {agency_name}_DATA_DIR / "{state_lower}_enrollment_{year.replace('-', '_')}.xlsx",
        }}

    def load_staff_data(self) -> pd.DataFrame:
        """Load {agency_name} staffing data."""
        files = self.get_data_files()
        if 'staff' not in files or not files['staff'].exists():
            return pd.DataFrame()
        # TODO: Update sheet_name and parsing logic based on actual file structure
        return pd.read_excel(files["staff"])

    def load_enrollment_data(self) -> pd.DataFrame:
        """Load {agency_name} enrollment data."""
        files = self.get_data_files()
        if 'enrollment' not in files or not files['enrollment'].exists():
            return pd.DataFrame()
        # TODO: Update sheet_name and parsing logic based on actual file structure
        return pd.read_excel(files["enrollment"])


# =============================================================================
# {state_code}-SPECIFIC TESTS (MIXIN)
# =============================================================================

class {state_name.replace(' ', '')}SpecificValidations:
    """{state_name}-specific validation tests (mixin - not run standalone)."""

    # TODO: Add state-specific tests here
    # Example:
    # def test_largest_district_is_expected(self):
    #     """Verify the largest district is as expected."""
    #     pass


# =============================================================================
# MAIN TEST CLASS
# =============================================================================

class Test{state_name.replace(' ', '')}Integration(
    {state_name.replace(' ', '')}SEAConfig,
    SEADataLoadingTests,
    SEACrosswalkTests,
    SEAStaffValidationTests,
    SEAEnrollmentValidationTests,
    SEALCTCalculationTests,
    SEADataIntegrityTests,
    SEADataQualityTests,
    SEARegressionPreventionTests,
    {state_name.replace(' ', '')}SpecificValidations,
):
    """
    Comprehensive integration tests for {state_name} ({agency_name}) data.

    Combines:
    - Standard SEA integration tests (from mixins)
    - {state_code}-specific validations
    """
    pass
'''
    return template


def generate_import_script(state_code: str, agency_name: str, year: str) -> str:
    """
    Generate import script scaffolding for a new state.
    """
    state_name = STATE_NAMES.get(state_code, state_code)
    state_lower = state_name.lower().replace(' ', '_')
    state_var = state_code.lower()

    template = f'''#!/usr/bin/env python3
"""
Import {state_name} Data to Database

This script imports {agency_name} data from Excel files into the database:
1. District identifiers (crosswalk) - uses state_district_crosswalk table
2. Staff data
3. Enrollment data

Uses shared utilities from sea_import_utils.py for common operations.

Usage:
    python import_{state_lower}_data.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope
from sqlalchemy import text
import pandas as pd
import logging

# Import shared SEA utilities
from infrastructure.database.migrations.sea_import_utils import (
    safe_float, safe_int,
    load_state_crosswalk, get_district_name,
    format_state_id, log_import_summary,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# State configuration
STATE_CODE = '{state_code}'

# Data file paths
{state_var.upper()}_DATA_DIR = project_root / "data" / "raw" / "state" / "{state_lower}"
# TODO: Update with actual file names
# STAFF_FILE = {state_var.upper()}_DATA_DIR / "{state_lower}_staff_{year.replace('-', '_')}.xlsx"
# ENROLLMENT_FILE = {state_var.upper()}_DATA_DIR / "{state_lower}_enrollment_{year.replace('-', '_')}.xlsx"


def load_{state_var}_crosswalk(session) -> dict:
    """Load {state_name} crosswalk from database.

    Returns:
        Dict mapping {agency_name} state district ID -> NCES ID
    """
    result = session.execute(text("""
        SELECT state_district_id, nces_id
        FROM state_district_crosswalk
        WHERE state = :state
          AND id_system = 'st_leaid'
    """), {{"state": STATE_CODE}})
    return {{row[0]: row[1] for row in result.fetchall()}}


def create_{state_var}_tables():
    """Create {state_name}-specific tables if they don't exist."""
    logger.info("Creating {state_name}-specific tables...")

    with session_scope() as session:
        # Create {state_code} district identifiers table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS {state_var}_district_identifiers (
                nces_id VARCHAR(10) PRIMARY KEY REFERENCES districts(nces_id),
                {state_var}_district_id VARCHAR(20) UNIQUE NOT NULL,
                district_name_{state_var} VARCHAR(255),
                source_year VARCHAR(10),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create {state_code} staff data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS {state_var}_staff_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_teachers NUMERIC(10, 2),
                -- TODO: Add state-specific staff columns
                data_source VARCHAR(50) DEFAULT '{agency_name.lower()}',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        # Create {state_code} enrollment data table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS {state_var}_enrollment_data (
                nces_id VARCHAR(10) REFERENCES districts(nces_id),
                year VARCHAR(10) NOT NULL,
                total_enrollment INTEGER,
                -- TODO: Add state-specific enrollment columns
                data_source VARCHAR(50) DEFAULT '{agency_name.lower()}',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (nces_id, year, data_source)
            )
        """))

        session.commit()
        logger.info("✅ Tables created/verified")


def load_staff_data():
    """Load staff data from Excel file."""
    # TODO: Implement based on actual file structure
    logger.warning("Staff data loading not yet implemented")
    return None


def load_enrollment_data():
    """Load enrollment data from Excel file."""
    # TODO: Implement based on actual file structure
    logger.warning("Enrollment data loading not yet implemented")
    return None


def import_staff_data(df):
    """Import staff data into database."""
    if df is None:
        logger.warning("No staff data to import")
        return 0

    # TODO: Implement based on actual file structure
    logger.warning("Staff data import not yet implemented")
    return 0


def import_enrollment_data(df):
    """Import enrollment data into database."""
    if df is None:
        logger.warning("No enrollment data to import")
        return 0

    # TODO: Implement based on actual file structure
    logger.warning("Enrollment data import not yet implemented")
    return 0


def main():
    """Main import process."""
    logger.info("=" * 80)
    logger.info(f"STARTING {state_name.upper()} DATA IMPORT")
    logger.info("=" * 80)

    # Create tables
    create_{state_var}_tables()

    # Load data
    staff_df = load_staff_data()
    enrollment_df = load_enrollment_data()

    # Import data
    staff_count = import_staff_data(staff_df)
    enrollment_count = import_enrollment_data(enrollment_df)

    log_import_summary(STATE_CODE, 0, staff_count, enrollment_count)


if __name__ == "__main__":
    main()
'''
    return template


def main():
    parser = argparse.ArgumentParser(
        description='Generate SEA integration scaffolding',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--state', '-s', type=str, help='Two-letter state code (e.g., OH)')
    parser.add_argument('--agency', '-a', type=str, help='Agency abbreviation (e.g., ODE)')
    parser.add_argument('--year', '-y', type=str, default='2023-24', help='Data year (default: 2023-24)')
    parser.add_argument('--analyze', type=str, help='Path to Excel/CSV file or directory to analyze')
    parser.add_argument('--output', '-o', type=str, help='Output directory (default: current)')
    parser.add_argument('--dry-run', action='store_true', help='Print output without writing files')

    args = parser.parse_args()

    # Analyze mode
    if args.analyze:
        analyze_path = Path(args.analyze)

        if analyze_path.is_file():
            files = [analyze_path]
        elif analyze_path.is_dir():
            files = list(analyze_path.glob('*.xlsx')) + list(analyze_path.glob('*.csv'))
        else:
            print(f"Error: {analyze_path} not found")
            sys.exit(1)

        print(f"\n{'='*60}")
        print("FILE ANALYSIS REPORT")
        print(f"{'='*60}\n")

        for file_path in files:
            print(f"File: {file_path.name}")
            print("-" * 40)

            results = analyze_excel_file(file_path)

            for sheet in results['sheets']:
                print(f"\nSheet: {sheet['name']}")
                print(f"  Rows: {sheet['row_count']}")
                print(f"  Columns ({len(sheet['columns'])}):")
                for col in sheet['columns'][:20]:
                    print(f"    - {col}")
                if len(sheet['columns']) > 20:
                    print(f"    ... and {len(sheet['columns']) - 20} more")

                if sheet['name'] in results['suggested_mappings']:
                    print(f"\n  Suggested Mappings:")
                    for target, source in results['suggested_mappings'][sheet['name']].items():
                        print(f"    {target}: '{source}'")

            print("\n")

        return

    # Generate mode
    if not args.state or not args.agency:
        parser.print_help()
        print("\nError: --state and --agency are required for generation mode")
        sys.exit(1)

    state_code = args.state.upper()
    if state_code not in STATE_NAMES:
        print(f"Warning: {state_code} not in known state codes")

    state_name = STATE_NAMES.get(state_code, state_code)
    state_lower = state_name.lower().replace(' ', '_')

    print(f"\nGenerating scaffolding for {state_name} ({args.agency})...")
    print("=" * 60)

    # Generate test file
    test_content = generate_test_file(state_code, args.agency, args.year)
    test_file = project_root / 'tests' / f'test_{state_lower}_integration.py'

    # Generate import script
    import_content = generate_import_script(state_code, args.agency, args.year)
    import_file = project_root / 'infrastructure' / 'database' / 'migrations' / f'import_{state_lower}_data.py'

    # Create data directory
    data_dir = project_root / 'data' / 'raw' / 'state' / state_lower

    if args.dry_run:
        print(f"\n[DRY RUN] Would create:")
        print(f"  - {test_file}")
        print(f"  - {import_file}")
        print(f"  - {data_dir}/")
        print(f"\nTest file content ({len(test_content)} chars)")
        print(f"Import script content ({len(import_content)} chars)")
    else:
        # Create data directory
        data_dir.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created: {data_dir}/")

        # Write test file
        if not test_file.exists():
            test_file.write_text(test_content)
            print(f"✅ Created: {test_file}")
        else:
            print(f"⚠️  Skipped (exists): {test_file}")

        # Write import script
        if not import_file.exists():
            import_file.write_text(import_content)
            print(f"✅ Created: {import_file}")
        else:
            print(f"⚠️  Skipped (exists): {import_file}")

    print(f"\n{'='*60}")
    print("NEXT STEPS:")
    print("1. Download {agency} data files to data/raw/state/{state_lower}/")
    print("2. Run: python generate_sea_integration.py --analyze data/raw/state/{state_lower}/")
    print("3. Update TODO sections in generated files with actual column mappings")
    print("4. Query database for crosswalk: SELECT * FROM state_district_crosswalk WHERE state = '{state_code}'")
    print("5. Run tests: pytest tests/test_{state_lower}_integration.py -v")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
