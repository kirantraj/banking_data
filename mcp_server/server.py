"""
MCP Server — Banking Data Copilot

This process is spawned as a subprocess by BankingMCPClient.
It communicates over stdin/stdout using the MCP protocol (JSON-RPC 2.0).

Exposes three tools:
  • query_bigquery    — run a SELECT query on BigQuery
  • validate_sql      — safety-check a SQL string before execution
  • search_documents  — keyword search over local .txt files

Architecture note: This file contains NO agent logic.
Reasoning lives in the agents/ package; execution lives here.
"""
import asyncio
import json
import os
import sys

# Make the project root importable when this script is run as a subprocess
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from mcp_server.tools.bigquery_tool import execute_bigquery_query
from mcp_server.tools.validate_sql import validate_sql_query
from mcp_server.tools.search_docs import search_documents
from utils.logger import get_logger

logger = get_logger("mcp_server")

server = Server("banking-copilot-mcp")


# ── Tool registry ─────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Tell any MCP client which tools this server exposes."""
    return [
        types.Tool(
            name="query_bigquery",
            description=(
                "Execute a SELECT SQL query on BigQuery and return the results as JSON. "
                "Only SELECT statements are accepted. A LIMIT clause is enforced "
                "automatically to control cost."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A BigQuery-compatible SELECT statement.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum rows to return. Defaults to 100.",
                        "default": 100,
                    },
                },
                "required": ["sql"],
            },
        ),
        types.Tool(
            name="validate_sql",
            description=(
                "Safety-check a SQL query before execution. "
                "Rejects queries that contain DELETE, DROP, UPDATE, INSERT or other "
                "dangerous operations. Optionally validates column names against a schema."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL query to validate.",
                    },
                    "schema_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Known column names to check against (optional).",
                    },
                },
                "required": ["sql"],
            },
        ),
        types.Tool(
            name="search_documents",
            description=(
                "Search local banking documents (.txt files) for content "
                "matching a query. Returns ranked excerpts with relevance scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search query.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum documents to return. Defaults to 5.",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


# ── Tool dispatcher ───────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent]:
    """Route an incoming tool call to the correct handler and return JSON."""
    logger.info(f"Tool invoked: '{name}' | args_keys={list(arguments.keys())}")

    if name == "query_bigquery":
        result = await execute_bigquery_query(
            sql=arguments["sql"],
            limit=arguments.get("limit", 100),
        )

    elif name == "validate_sql":
        result = validate_sql_query(
            sql=arguments["sql"],
            schema_columns=arguments.get("schema_columns"),
        )

    elif name == "search_documents":
        result = search_documents(
            query=arguments["query"],
            max_results=arguments.get("max_results", 5),
        )

    else:
        result = {"error": f"Unknown tool: '{name}'"}
        logger.error(f"Unknown tool requested: {name}")

    return [types.TextContent(type="text", text=json.dumps(result, default=str))]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="banking-copilot-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
