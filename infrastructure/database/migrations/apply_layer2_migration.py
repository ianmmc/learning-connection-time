#!/usr/bin/env python3
"""
Apply Layer 2 state-level tables migration.

Creates 4 new tables:
1. ca_sped_district_environments - California SPED actual enrollment
2. district_socioeconomic - Multi-state socioeconomic indicators
3. district_funding - Multi-state funding data
4. ca_lcff_funding - California LCFF funding details
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import get_engine
from infrastructure.database.models import Base, CASpedDistrictEnvironments, DistrictSocioeconomic, DistrictFunding, CALCFFFunding

def main():
    """Create Layer 2 tables."""
    print("Creating Layer 2 state-level enhancement tables...")

    engine = get_engine()

    # Create only the new tables
    tables = [
        CASpedDistrictEnvironments.__table__,
        DistrictSocioeconomic.__table__,
        DistrictFunding.__table__,
        CALCFFFunding.__table__,
    ]

    for table in tables:
        print(f"Creating table: {table.name}")
        table.create(engine, checkfirst=True)

    print("\n✓ Layer 2 tables created successfully!")
    print("\nNew tables:")
    print("  - ca_sped_district_environments")
    print("  - district_socioeconomic")
    print("  - district_funding")
    print("  - ca_lcff_funding")

if __name__ == "__main__":
    main()
