#!/usr/bin/env python3
"""
PostgreSQL MCP Server for Claude Desktop

Enables Claude Desktop to efficiently query the learning_connection_time database
for creating reports, analysis, and visualizations.

Usage:
    python mcp_server_postgres.py

Configuration in claude_desktop_config.json:
    {
      "mcpServers": {
        "postgres-lct": {
          "command": "python",
          "args": ["/path/to/mcp_server_postgres.py"]
        }
      }
    }
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp.server import Server
from mcp.types import Tool, TextContent
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import (
    get_state_campaign_progress,
    get_lct_summary_by_scope,
    get_enrichment_summary,
    get_next_enrichment_candidates,
)

# Initialize MCP server
server = Server("postgres-lct")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="query_campaign_progress",
            description="Get state-by-state enrichment campaign progress",
            inputSchema={
                "type": "object",
                "properties": {
                    "year": {
                        "type": "string",
                        "description": "School year (e.g., '2025-26')",
                        "default": "2025-26"
                    }
                }
            }
        ),
        Tool(
            name="query_lct_summary",
            description="Get LCT statistics for a specific scope",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "description": "LCT scope (teachers_only, teachers_elementary, teachers_secondary, teachers_core, instructional, instructional_plus_support, all)",
                        "default": "teachers_only"
                    },
                    "year": {
                        "type": "string",
                        "description": "School year (e.g., '2023-24')",
                        "default": "2023-24"
                    }
                }
            }
        ),
        Tool(
            name="query_enrichment_summary",
            description="Get overall enrichment statistics",
            inputSchema={
                "type": "object",
                "properties": {
                    "year": {
                        "type": "string",
                        "description": "School year (e.g., '2025-26')",
                        "default": "2025-26"
                    }
                }
            }
        ),
        Tool(
            name="query_next_candidates",
            description="Get next unenriched district candidates for a state",
            inputSchema={
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Two-letter state code (e.g., 'WI')"
                    },
                    "year": {
                        "type": "string",
                        "description": "School year (e.g., '2025-26')",
                        "default": "2025-26"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of candidates to return",
                        "default": 9
                    }
                },
                "required": ["state"]
            }
        ),
        Tool(
            name="database_status",
            description="Get database connection and table status",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    if name == "query_campaign_progress":
        year = arguments.get("year", "2025-26")
        return [await _query_campaign_progress(year)]
    elif name == "query_lct_summary":
        scope = arguments.get("scope", "teachers_only")
        year = arguments.get("year", "2023-24")
        return [await _query_lct_summary(scope, year)]
    elif name == "query_enrichment_summary":
        year = arguments.get("year", "2025-26")
        return [await _query_enrichment_summary(year)]
    elif name == "query_next_candidates":
        state = arguments["state"]
        year = arguments.get("year", "2025-26")
        limit = arguments.get("limit", 9)
        return [await _query_next_candidates(state, year, limit)]
    elif name == "database_status":
        return [await _database_status()]
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _query_campaign_progress(year: str = "2025-26") -> TextContent:
    """
    Get state-by-state enrichment campaign progress.

    Args:
        year: School year (e.g., "2025-26")

    Returns:
        Campaign progress by state with enrichment counts
    """
    try:
        with session_scope() as session:
            progress = get_state_campaign_progress(session, year)
            return TextContent(
                type="text",
                text=json.dumps(progress, indent=2)
            )
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Error querying campaign progress: {str(e)}"
        )


async def _query_lct_summary(scope: str = "teachers_only", year: str = "2023-24") -> TextContent:
    """
    Get LCT statistics for a specific scope.

    Args:
        scope: LCT scope (teachers_only, teachers_elementary, teachers_secondary,
               teachers_core, instructional, instructional_plus_support, all)
        year: School year (e.g., "2023-24")

    Returns:
        Summary statistics: mean, median, std, min, max LCT values
    """
    try:
        with session_scope() as session:
            summary = get_lct_summary_by_scope(session, scope, year)
            return TextContent(
                type="text",
                text=json.dumps(summary, indent=2)
            )
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Error querying LCT summary: {str(e)}"
        )


async def _query_enrichment_summary(year: str = "2025-26") -> TextContent:
    """
    Get overall enrichment statistics.

    Args:
        year: School year (e.g., "2025-26")

    Returns:
        Total enriched districts, enrichment rate, states represented
    """
    try:
        with session_scope() as session:
            summary = get_enrichment_summary(session, year)
            return TextContent(
                type="text",
                text=json.dumps(summary, indent=2)
            )
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Error querying enrichment summary: {str(e)}"
        )


async def _query_next_candidates(state: str, year: str = "2025-26", limit: int = 9) -> TextContent:
    """
    Get next unenriched district candidates for a state.

    Args:
        state: Two-letter state code (e.g., "WI")
        year: School year (e.g., "2025-26")
        limit: Number of candidates to return (default: 9)

    Returns:
        Top districts by enrollment needing enrichment
    """
    try:
        with session_scope() as session:
            candidates = get_next_enrichment_candidates(session, state, year, limit)
            candidate_data = [
                {
                    "nces_id": c.nces_id,
                    "name": c.name,
                    "state": c.state,
                    "enrollment": c.enrollment
                }
                for c in candidates
            ]
            return TextContent(
                type="text",
                text=json.dumps(candidate_data, indent=2)
            )
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Error querying candidates: {str(e)}"
        )


async def _database_status() -> TextContent:
    """
    Get database connection and table status.

    Returns:
        Database health check and row counts
    """
    try:
        with session_scope() as session:
            from infrastructure.database.models import (
                District, BellSchedule, StateRequirement, LCTCalculation
            )

            status = {
                "connected": True,
                "tables": {
                    "districts": session.query(District).count(),
                    "bell_schedules": session.query(BellSchedule).count(),
                    "state_requirements": session.query(StateRequirement).count(),
                    "lct_calculations": session.query(LCTCalculation).count(),
                },
                "enriched_districts": session.query(BellSchedule).distinct(
                    BellSchedule.district_id
                ).count()
            }
            return TextContent(
                type="text",
                text=json.dumps(status, indent=2)
            )
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Database connection error: {str(e)}"
        )


if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )

    asyncio.run(main())