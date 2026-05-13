"""
SQL Generator Agent

Converts a natural-language banking question into a valid BigQuery SQL
SELECT statement.

Prompt design choices:
  • Provides the full table + column schema so the LLM can reference real names.
  • Lists common BigQuery date functions so the LLM uses the right syntax.
  • Forces LIMIT in every query to keep costs low.
  • Temperature 0.05 — we want deterministic SQL, not creative output.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
from config.settings import settings


class SQLGeneratorAgent(BaseAgent):

    def __init__(self):
        super().__init__("sql_generator")

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_sql(self, user_query: str) -> dict:
        """
        Convert a natural-language query to BigQuery SQL.

        Returns:
            {
                "sql":               str   — the SELECT statement
                "explanation":       str   — plain-English description
                "columns_used":      list  — columns referenced
                "aggregation_used":  bool  — whether GROUP BY is present
            }
        """
        self.logger.info(f"Generating SQL for: '{user_query[:80]}'")
        return self.generate(self._build_prompt(user_query), temperature=0.05)

    # ── Prompt ────────────────────────────────────────────────────────────────

    def _build_prompt(self, user_query: str) -> str:
        full_table = (
            f"`{settings.project_id}.{settings.dataset_id}.{settings.table_id}`"
        )
        return f"""You are a BigQuery SQL expert for a banking analytics platform.
Convert the user's question into a valid, cost-efficient BigQuery SELECT query.

User Question: "{user_query}"

Table: {full_table}
Schema:
  date              DATE     Transaction date
  product           STRING   'Savings Account' | 'Credit Card' | 'Home Loan' | 'Personal Loan'
  revenue           FLOAT64  Transaction amount in USD
  customer_id       STRING   Unique customer identifier (e.g. 'C001')
  region            STRING   'North' | 'South' | 'East' | 'West'
  transaction_type  STRING   'credit' | 'debit'

BigQuery SQL Rules (MUST follow):
1. ONLY SELECT — never INSERT, UPDATE, DELETE, DROP, CREATE, TRUNCATE.
2. Always include LIMIT (default 100, max 1000).
3. Use BigQuery-specific date functions:
     Last 30 days  →  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
     Last month    →  WHERE DATE_TRUNC(date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
     This year     →  WHERE EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE())
4. For "top N" queries use ORDER BY ... DESC LIMIT N.
5. For summaries use GROUP BY with SUM / AVG / COUNT.
6. Qualify the table name exactly as shown above (backtick-quoted).

Respond with valid JSON only — no markdown, no prose outside the JSON:
{{
  "sql":              "SELECT ... FROM ... WHERE ... ORDER BY ... LIMIT ...",
  "explanation":      "Plain English: what this query does",
  "columns_used":     ["col1", "col2"],
  "aggregation_used": true | false
}}"""

    # ── Mock ──────────────────────────────────────────────────────────────────

    def _mock_response(self, prompt: str) -> dict:
        import re
        match = re.search(r'User Question: "([^"]+)"', prompt)
        q = match.group(1).lower() if match else prompt.lower()
        t = f"`{settings.project_id}.{settings.dataset_id}.{settings.table_id}`"

        if "top" in q and ("customer" in q or "transaction" in q):
            return {
                "sql": (
                    f"SELECT customer_id, SUM(revenue) AS total_revenue, "
                    f"COUNT(*) AS tx_count "
                    f"FROM {t} "
                    f"GROUP BY customer_id "
                    f"ORDER BY total_revenue DESC "
                    f"LIMIT 10"
                ),
                "explanation": "Top 10 customers ranked by total transaction revenue.",
                "columns_used": ["customer_id", "revenue"],
                "aggregation_used": True,
            }

        if "product" in q or "by product" in q:
            return {
                "sql": (
                    f"SELECT product, "
                    f"SUM(revenue) AS total_revenue, "
                    f"COUNT(*) AS transaction_count, "
                    f"AVG(revenue) AS avg_revenue "
                    f"FROM {t} "
                    f"GROUP BY product "
                    f"ORDER BY total_revenue DESC "
                    f"LIMIT 100"
                ),
                "explanation": "Revenue breakdown by product type with transaction counts.",
                "columns_used": ["product", "revenue"],
                "aggregation_used": True,
            }

        if "region" in q:
            return {
                "sql": (
                    f"SELECT region, "
                    f"SUM(revenue) AS total_revenue, "
                    f"COUNT(*) AS transaction_count "
                    f"FROM {t} "
                    f"GROUP BY region "
                    f"ORDER BY total_revenue DESC "
                    f"LIMIT 10"
                ),
                "explanation": "Total revenue and transaction volume per region.",
                "columns_used": ["region", "revenue"],
                "aggregation_used": True,
            }

        if "fraud" in q or "large" in q or "suspicious" in q:
            return {
                "sql": (
                    f"SELECT customer_id, product, revenue, date, region "
                    f"FROM {t} "
                    f"WHERE transaction_type = 'debit' AND revenue > 10000 "
                    f"ORDER BY revenue DESC "
                    f"LIMIT 50"
                ),
                "explanation": "Large debit transactions that may warrant fraud review.",
                "columns_used": ["customer_id", "product", "revenue", "date", "region"],
                "aggregation_used": False,
            }

        if "last month" in q or "last 30" in q:
            return {
                "sql": (
                    f"SELECT * FROM {t} "
                    f"WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) "
                    f"ORDER BY date DESC "
                    f"LIMIT 100"
                ),
                "explanation": "All transactions from the last 30 days.",
                "columns_used": ["date"],
                "aggregation_used": False,
            }

        # Default fallback
        return {
            "sql": f"SELECT * FROM {t} ORDER BY date DESC LIMIT 100",
            "explanation": "Most recent 100 transactions.",
            "columns_used": ["date"],
            "aggregation_used": False,
        }
