"""
MCP Tool: query_bigquery

Executes a SELECT SQL query on BigQuery and returns rows as a list of dicts.

Design decisions:
- LIMIT is injected if missing — never let a query run unbounded.
- The BigQuery client is run in a thread-pool executor so it doesn't block
  the asyncio event loop (the BQ client is synchronous).
- Falls back to MOCK_ROWS when USE_MOCK_DATA=true so the full pipeline can
  be tested locally without GCP credentials.
"""
import asyncio
import os
import sys
from typing import Any

# Allow imports from the project root when this file is imported by the MCP server subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("tools.bigquery")

# ── Mock data (mirrors the real BQ schema) ────────────────────────────────────
MOCK_ROWS = [
    {"date": "2024-01-15", "product": "Savings Account",  "revenue": 15000.00, "customer_id": "C001", "region": "North", "transaction_type": "credit"},
    {"date": "2024-01-16", "product": "Credit Card",       "revenue":  8500.50, "customer_id": "C002", "region": "South", "transaction_type": "debit"},
    {"date": "2024-01-17", "product": "Home Loan",         "revenue": 52000.00, "customer_id": "C003", "region": "East",  "transaction_type": "credit"},
    {"date": "2024-01-18", "product": "Savings Account",  "revenue":  3200.00, "customer_id": "C004", "region": "West",  "transaction_type": "credit"},
    {"date": "2024-01-19", "product": "Credit Card",       "revenue": 12000.75, "customer_id": "C005", "region": "North", "transaction_type": "debit"},
    {"date": "2024-01-20", "product": "Personal Loan",    "revenue": 25000.00, "customer_id": "C006", "region": "South", "transaction_type": "credit"},
    {"date": "2024-01-21", "product": "Home Loan",         "revenue": 78000.00, "customer_id": "C007", "region": "East",  "transaction_type": "credit"},
    {"date": "2024-01-22", "product": "Credit Card",       "revenue":  4500.25, "customer_id": "C008", "region": "West",  "transaction_type": "debit"},
    {"date": "2024-01-23", "product": "Savings Account",  "revenue":  9800.00, "customer_id": "C009", "region": "North", "transaction_type": "credit"},
    {"date": "2024-01-24", "product": "Personal Loan",    "revenue": 35000.00, "customer_id": "C010", "region": "South", "transaction_type": "credit"},
    {"date": "2024-01-25", "product": "Credit Card",       "revenue":  6200.00, "customer_id": "C011", "region": "East",  "transaction_type": "debit"},
    {"date": "2024-01-26", "product": "Home Loan",         "revenue": 95000.00, "customer_id": "C012", "region": "West",  "transaction_type": "credit"},
    {"date": "2024-01-27", "product": "Savings Account",  "revenue": 18500.00, "customer_id": "C013", "region": "North", "transaction_type": "credit"},
    {"date": "2024-01-28", "product": "Credit Card",       "revenue":  3100.50, "customer_id": "C014", "region": "South", "transaction_type": "debit"},
    {"date": "2024-01-29", "product": "Personal Loan",    "revenue": 42000.00, "customer_id": "C015", "region": "East",  "transaction_type": "credit"},
    {"date": "2024-01-30", "product": "Home Loan",         "revenue": 67500.00, "customer_id": "C016", "region": "West",  "transaction_type": "credit"},
    {"date": "2024-02-01", "product": "Savings Account",  "revenue":  7300.00, "customer_id": "C017", "region": "North", "transaction_type": "credit"},
    {"date": "2024-02-02", "product": "Credit Card",       "revenue": 15600.00, "customer_id": "C018", "region": "South", "transaction_type": "debit"},
    {"date": "2024-02-03", "product": "Personal Loan",    "revenue": 28000.00, "customer_id": "C019", "region": "East",  "transaction_type": "credit"},
    {"date": "2024-02-04", "product": "Home Loan",         "revenue":110000.00, "customer_id": "C020", "region": "West",  "transaction_type": "credit"},
]


async def execute_bigquery_query(sql: str, limit: int = 100) -> dict[str, Any]:
    """
    Execute a SELECT query on BigQuery.

    Args:
        sql:   A SELECT statement (LIMIT injected if absent).
        limit: Maximum rows; injected into SQL if LIMIT clause is missing.

    Returns:
        {
            "success": bool,
            "rows": list[dict],
            "row_count": int,
            "sql_executed": str,
            "error": str | None,       # present only on failure
            "note": str | None         # present in mock mode
        }
    """
    # ── Safety: always enforce LIMIT ──────────────────────────────────────────
    if "LIMIT" not in sql.upper():
        sql = f"{sql.rstrip(';')} LIMIT {limit}"
        logger.info(f"Auto-applied LIMIT {limit}")

    if settings.use_mock_data:
        logger.info("Mock mode active — returning sample rows")
        return _mock_result(sql, limit)

    try:
        from google.cloud import bigquery  # lazy import

        client = bigquery.Client(project=settings.project_id)
        logger.info(f"BQ query: {sql[:140]}")

        # Run the synchronous BQ client in a thread so we don't block the loop
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(
            None, lambda: list(client.query(sql).result())
        )

        results = [dict(row.items()) for row in rows]
        logger.info(f"BQ returned {len(results)} rows")

        return {
            "success": True,
            "rows": results,
            "row_count": len(results),
            "sql_executed": sql,
        }

    except Exception as exc:
        logger.error(f"BigQuery error: {exc}")
        return {
            "success": False,
            "rows": [],
            "row_count": 0,
            "sql_executed": sql,
            "error": str(exc),
        }


def _mock_result(sql: str, limit: int) -> dict[str, Any]:
    rows = MOCK_ROWS[: min(limit, len(MOCK_ROWS))]
    return {
        "success": True,
        "rows": rows,
        "row_count": len(rows),
        "sql_executed": sql,
        "note": "Mock data — connect a real BigQuery project for live results",
    }
