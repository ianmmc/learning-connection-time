#!/usr/bin/env python3
"""
Generate data dictionary from SQLAlchemy models.

Automatically creates Markdown documentation of all database tables,
their columns, relationships, and constraints.

Usage:
    python generate_data_dictionary.py [--output-dir path]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect
from sqlalchemy.orm import class_mapper

from infrastructure.database.models import (
    Base,
    District,
    StateRequirement,
    BellSchedule,
    LCTCalculation,
    CalculationRun,
    DataLineage,
    DataSourceRegistry,
    StaffCounts,
    StaffCountsEffective,
    EnrollmentByGrade,
)


def get_column_info(column) -> Dict[str, Any]:
    """Extract column information from SQLAlchemy column."""
    return {
        "name": column.name,
        "type": str(column.type),
        "nullable": column.nullable,
        "primary_key": column.primary_key,
        "foreign_keys": [str(fk.column) for fk in column.foreign_keys],
        "default": str(column.default.arg) if column.default else None,
    }


def get_model_info(model_class) -> Dict[str, Any]:
    """Extract comprehensive information from SQLAlchemy model."""
    mapper = class_mapper(model_class)
    inspector = inspect(model_class)

    # Get columns
    columns = []
    for column in mapper.columns:
        col_info = get_column_info(column)
        columns.append(col_info)

    # Get relationships
    relationships = []
    for rel in mapper.relationships:
        relationships.append({
            "name": rel.key,
            "target": rel.mapper.class_.__name__,
            "direction": str(rel.direction).split('.')[-1],
        })

    # Get constraints from table args
    constraints = []
    if hasattr(model_class, "__table_args__"):
        table_args = model_class.__table_args__
        if isinstance(table_args, tuple):
            for arg in table_args:
                if hasattr(arg, "name"):
                    constraints.append({
                        "type": type(arg).__name__,
                        "name": arg.name,
                    })

    return {
        "table_name": model_class.__tablename__,
        "docstring": model_class.__doc__ or "",
        "columns": columns,
        "relationships": relationships,
        "constraints": constraints,
    }


def generate_markdown(models: List[type], timestamp: str) -> str:
    """Generate Markdown data dictionary from models."""
    lines = [
        "# Database Data Dictionary",
        "",
        f"*Auto-generated: {timestamp}*",
        "",
        "This document describes all database tables, columns, and relationships",
        "for the Learning Connection Time project.",
        "",
        "## Table of Contents",
        "",
    ]

    # Generate TOC
    for model in models:
        table_name = model.__tablename__
        lines.append(f"- [{table_name}](#{table_name})")
    lines.append("")

    # Generate table documentation
    for model in models:
        info = get_model_info(model)

        lines.append(f"## {info['table_name']}")
        lines.append("")

        # Docstring
        if info['docstring']:
            docstring = info['docstring'].strip().split('\n')
            for line in docstring:
                lines.append(line.strip())
            lines.append("")

        # Columns table
        lines.append("### Columns")
        lines.append("")
        lines.append("| Column | Type | Nullable | Key | Default |")
        lines.append("|--------|------|----------|-----|---------|")

        for col in info['columns']:
            key = ""
            if col['primary_key']:
                key = "PK"
            elif col['foreign_keys']:
                key = f"FK → {col['foreign_keys'][0]}"

            nullable = "Yes" if col['nullable'] else "No"
            default = col['default'] or ""

            lines.append(f"| `{col['name']}` | {col['type']} | {nullable} | {key} | {default} |")

        lines.append("")

        # Relationships
        if info['relationships']:
            lines.append("### Relationships")
            lines.append("")
            for rel in info['relationships']:
                lines.append(f"- **{rel['name']}** → `{rel['target']}` ({rel['direction']})")
            lines.append("")

        # Constraints
        if info['constraints']:
            lines.append("### Constraints")
            lines.append("")
            for constraint in info['constraints']:
                lines.append(f"- `{constraint['name']}` ({constraint['type']})")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Add metadata section
    lines.extend([
        "## Metadata",
        "",
        "### Version History",
        "",
        "| Version | Date | Changes |",
        "|---------|------|---------|",
        "| 2.0 | December 2025 | Added CalculationRun, level-based enrollment/staffing |",
        "| 1.5 | December 2025 | Added StaffCountsEffective with scope calculations |",
        "| 1.0 | December 2025 | Initial PostgreSQL migration |",
        "",
        "### Data Sources",
        "",
        "- **NCES CCD**: Primary source for districts, enrollment, staffing",
        "- **Bell Schedules**: Collected via web scraping and manual research",
        "- **State Requirements**: Compiled from state education codes",
        "",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate data dictionary")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "docs" / "data-dictionaries",
        help="Output directory",
    )
    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Models to document (in logical order)
    models = [
        District,
        StateRequirement,
        BellSchedule,
        StaffCounts,
        StaffCountsEffective,
        EnrollmentByGrade,
        LCTCalculation,
        CalculationRun,
        DataLineage,
        DataSourceRegistry,
    ]

    # Generate timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp_file = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Generate Markdown
    markdown = generate_markdown(models, timestamp)

    # Save with timestamp
    output_file = args.output_dir / f"database_schema_{timestamp_file}.md"
    with open(output_file, 'w') as f:
        f.write(markdown)
    print(f"Generated data dictionary: {output_file}")

    # Also save as "latest" for easy access
    latest_file = args.output_dir / "database_schema_latest.md"
    with open(latest_file, 'w') as f:
        f.write(markdown)
    print(f"Updated latest: {latest_file}")


if __name__ == "__main__":
    main()
