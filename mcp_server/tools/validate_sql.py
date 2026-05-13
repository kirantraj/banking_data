"""
MCP Tool: validate_sql

Checks a SQL string for safety before it is executed on BigQuery.

Rules enforced:
1. Must be a SELECT statement (no DML/DDL).
2. No dangerous keywords even when hidden in comments.
3. LIMIT clause required (warning if absent — the BQ tool adds it anyway).
4. Optional column-name check against the known schema.

This is intentionally a pure synchronous function — no I/O, no async.
"""
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger

logger = get_logger("tools.validate_sql")

# Keywords that must never appear in a query sent to production BigQuery
BLOCKED_KEYWORDS = {
    "DELETE", "DROP", "UPDATE", "INSERT", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "MERGE", "EXEC", "EXECUTE",
    "GRANT", "REVOKE", "CALL",
}


def validate_sql_query(sql: str, schema_columns: list[str] | None = None) -> dict[str, Any]:
    """
    Validate a SQL string for safety and basic correctness.

    Args:
        sql:            The query to validate.
        schema_columns: If provided, check that column names in the SELECT
                        clause exist in this list (heuristic — not a full parser).

    Returns:
        {
            "valid":    bool,
            "errors":   list[str],   # block execution if non-empty
            "warnings": list[str],   # advisory — execution allowed
            "sql":      str          # original SQL (stripped)
        }
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not sql or not sql.strip():
        return {"valid": False, "errors": ["SQL is empty"], "warnings": [], "sql": ""}

    sql_clean = sql.strip()

    # Strip comments before keyword scanning (prevents -- COMMENT tricks)
    stripped = re.sub(r"--[^\n]*", " ", sql_clean)
    stripped = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.DOTALL)
    upper = stripped.upper()

    # ── Rule 1: must start with SELECT ───────────────────────────────────────
    first_token = upper.split()[0] if upper.split() else ""
    if first_token != "SELECT":
        errors.append(
            f"Only SELECT statements are permitted. Got first token: '{first_token}'"
        )

    # ── Rule 2: block dangerous keywords ─────────────────────────────────────
    tokens = set(re.findall(r"\b[A-Z]+\b", upper))
    found_dangerous = tokens & BLOCKED_KEYWORDS
    if found_dangerous:
        errors.append(
            f"Blocked keyword(s) detected: {', '.join(sorted(found_dangerous))}"
        )

    # ── Rule 3: LIMIT clause ──────────────────────────────────────────────────
    if "LIMIT" not in tokens:
        warnings.append(
            "No LIMIT clause — query may scan many rows. "
            "The executor will append LIMIT 100 automatically."
        )

    # ── Rule 4: UNION (advisory) ──────────────────────────────────────────────
    if "UNION" in tokens:
        warnings.append("UNION detected — verify this is intentional and not an injection.")

    # ── Rule 5: Optional column validation (heuristic) ───────────────────────
    if schema_columns and errors == []:
        select_match = re.search(r"SELECT\s+(.*?)\s+FROM", upper, re.DOTALL)
        if select_match:
            col_text = select_match.group(1).strip()
            if col_text != "*":
                # Extract bare identifiers from SELECT list (not function names like SUM)
                raw_cols = re.findall(r"\b([A-Z_][A-Z0-9_]*)\b", col_text)
                reserved = {
                    "AS", "DISTINCT", "ALL", "SUM", "AVG", "COUNT", "MAX", "MIN",
                    "CAST", "DATE", "STRING", "INT64", "FLOAT64", "ARRAY", "STRUCT",
                    "EXTRACT", "FORMAT", "TIMESTAMP",
                }
                candidate_cols = [c for c in raw_cols if c not in reserved]
                schema_upper = {c.upper() for c in schema_columns}
                unknown = [c for c in candidate_cols if c not in schema_upper]
                if unknown:
                    warnings.append(
                        f"Possible unknown column(s) (may be aliases): {', '.join(unknown)}"
                    )

    is_valid = len(errors) == 0
    logger.info(f"SQL validation: valid={is_valid}, errors={errors}, warnings={warnings}")

    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "sql": sql_clean,
    }
