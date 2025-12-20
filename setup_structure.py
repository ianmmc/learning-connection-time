#!/usr/bin/env python3
"""
Create the directory structure for learning-connection-time project
"""

from pathlib import Path

def create_structure():
    """Create all directories for the project"""
    
    base = Path(__file__).parent
    
    # Define all directories
    directories = [
        # Config
        "config",
        
        # Data directories
        "data/raw/federal/nces-ccd",
        "data/raw/federal/crdc",
        "data/raw/federal/metadata/data-dictionaries",
        "data/raw/federal/metadata/schemas",
        "data/raw/state/california",
        "data/raw/state/texas",
        "data/raw/state/new-york",
        "data/raw/state/florida",
        "data/processed/normalized",
        "data/processed/merged",
        "data/processed/validated",
        "data/enriched/lct-calculations",
        "data/enriched/district-profiles",
        "data/enriched/comparative-analysis",
        "data/exports/csv",
        "data/exports/json",
        "data/exports/reports",
        
        # Documentation
        "docs/data-dictionaries",
        "docs/analysis-reports",
        "docs/chat-history",
        
        # Infrastructure
        "infrastructure/scripts/download",
        "infrastructure/scripts/extract",
        "infrastructure/scripts/transform",
        "infrastructure/scripts/analyze",
        "infrastructure/quality-assurance/tests",
        "infrastructure/utilities",
        
        # Notebooks
        "notebooks/exploratory",
        "notebooks/validation",
        "notebooks/visualization",
        
        # Source code
        "src/python/processors",
        "src/python/calculators",
        "src/python/exporters",
        "src/sql/queries",
        
        # Pipelines
        "pipelines",
        
        # Outputs
        "outputs/visualizations",
        "outputs/reports",
        "outputs/datasets",
    ]
    
    # Create all directories
    for directory in directories:
        dir_path = base / directory
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"✓ Created: {directory}")
    
    print(f"\n✅ Created {len(directories)} directories")

if __name__ == "__main__":
    create_structure()
