"""
Explainer Agent

Translates raw BigQuery results and/or document search results into
a clear, business-friendly response for non-technical banking executives.

Prompt design:
  • Explicitly forbids SQL jargon.
  • Asks for a formatted markdown table for easy reading.
  • Temperature 0.3 — slightly more expressive than the SQL agents.
"""
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent


class ExplainerAgent(BaseAgent):

    def __init__(self):
        super().__init__("explainer")

    # ── Public API ────────────────────────────────────────────────────────────

    def explain_results(
        self,
        original_query: str,
        sql_executed: str,
        query_result: dict[str, Any],
        doc_results: list[dict] | None = None,
    ) -> dict:
        """
        Convert raw query results into a human-friendly business explanation.

        Returns:
            {
                "summary":           str   — 1-2 sentence executive summary
                "insights":          list  — bulleted key findings with numbers
                "formatted_table":   str   — markdown table of top results
                "recommendations":   str   — optional business recommendation
            }
        """
        self.logger.info("Generating business explanation…")
        return self.generate(
            self._build_prompt(original_query, sql_executed, query_result, doc_results),
            temperature=0.3,
        )

    # ── Prompt ────────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        original_query: str,
        sql_executed: str,
        query_result: dict,
        doc_results: list[dict] | None,
    ) -> str:
        rows = query_result.get("rows", [])
        row_count = query_result.get("row_count", len(rows))
        # Cap rows sent to the prompt to avoid token overflow
        sample = json.dumps(rows[:10], indent=2, default=str)

        doc_section = ""
        if doc_results:
            doc_section = (
                "\n\nDocument search results (top 3):\n"
                + json.dumps(doc_results[:3], indent=2)
            )

        note = ""
        if query_result.get("note"):
            note = f"\nNote: {query_result['note']}"

        return f"""You are a senior banking analyst communicating data insights to non-technical executives.

User's Original Question:
  "{original_query}"

SQL Query Executed:
```sql
{sql_executed or "(no SQL — document search only)"}
```

Query Results ({row_count} total rows, showing first 10):{note}
{sample}
{doc_section}

Your task: Produce a professional, clear business summary.
Rules:
  • Use plain language — no SQL terms, no technical jargon.
  • Format monetary amounts with $ and commas (e.g. $1,234,567).
  • Highlight the single most important finding in the summary.
  • If doc_results are present, integrate relevant document insights.
  • The formatted_table should use markdown pipe syntax with a header row.

Respond with valid JSON only — no markdown fence, no prose outside the JSON:
{{
  "summary":         "<1-2 sentence executive summary with the key finding>",
  "insights": [
    "<Specific insight 1 with actual numbers from the data>",
    "<Specific insight 2>",
    "<Specific insight 3>"
  ],
  "formatted_table": "| Col1 | Col2 |\\n|------|------|\\n| val | val |",
  "recommendations": "<1-2 sentence optional business recommendation>"
}}"""

    # ── Mock ──────────────────────────────────────────────────────────────────

    def _mock_response(self, prompt: str) -> dict:
        import re
        match = re.search(r'User\'s Original Question:\s+"([^"]+)"', prompt)
        q = match.group(1).lower() if match else prompt.lower()

        if "top" in q and "customer" in q:
            return {
                "summary": "Customer C007 leads all clients with $78,000 in transactions, followed by C020 at $110,000 — Home Loan customers dominate the top revenue tier.",
                "insights": [
                    "C020 generated the highest single transaction at $110,000 (Home Loan, West region)",
                    "Home Loan customers account for 4 of the top 5 revenue positions",
                    "North region customers average $14,100 per transaction vs the overall mean of $8,500",
                    "Credit Card debit transactions are the most frequent but lowest-value category",
                ],
                "formatted_table": (
                    "| Customer | Product | Revenue | Region |\n"
                    "|----------|---------|---------|--------|\n"
                    "| C020 | Home Loan | $110,000 | West |\n"
                    "| C007 | Home Loan | $78,000 | East |\n"
                    "| C012 | Home Loan | $95,000 | West |\n"
                    "| C015 | Personal Loan | $42,000 | East |\n"
                    "| C010 | Personal Loan | $35,000 | South |"
                ),
                "recommendations": "Consider a priority relationship-manager programme for Home Loan customers in the West region, who generate the highest revenue per transaction.",
            }

        if "product" in q:
            return {
                "summary": "Home Loans generate the highest total revenue at an average of $80,500 per transaction, while Credit Cards show the highest volume but lowest per-transaction value.",
                "insights": [
                    "Home Loans: 5 transactions totalling ~$402,500 (avg $80,500 each)",
                    "Personal Loans: 4 transactions totalling ~$130,000 (avg $32,500 each)",
                    "Savings Accounts: 5 transactions totalling ~$53,800 (avg $10,760 each)",
                    "Credit Cards: 6 transactions totalling ~$49,900 (avg $8,317 each — lowest avg)",
                ],
                "formatted_table": (
                    "| Product | Total Revenue | Avg per Tx | Count |\n"
                    "|---------|--------------|-----------|-------|\n"
                    "| Home Loan | $402,500 | $80,500 | 5 |\n"
                    "| Personal Loan | $130,000 | $32,500 | 4 |\n"
                    "| Savings Account | $53,800 | $10,760 | 5 |\n"
                    "| Credit Card | $49,900 | $8,317 | 6 |"
                ),
                "recommendations": "Home Loans represent 62% of total revenue from just 25% of transactions — growing this product line should be a strategic priority.",
            }

        if "region" in q:
            return {
                "summary": "The West region leads all geographies in total revenue at $272,500, driven primarily by large Home Loan transactions.",
                "insights": [
                    "West region: $272,500 total (Home Loan + Personal Loan dominant)",
                    "East region: $197,000 total across 5 transactions",
                    "South region: $107,000 with a more balanced product mix",
                    "North region: $55,100 — highest transaction frequency but lowest avg value",
                ],
                "formatted_table": (
                    "| Region | Total Revenue | Transactions |\n"
                    "|--------|--------------|-------------|\n"
                    "| West | $272,500 | 5 |\n"
                    "| East | $197,000 | 5 |\n"
                    "| South | $107,000 | 5 |\n"
                    "| North | $55,100 | 5 |"
                ),
                "recommendations": "Allocate additional loan officers to the West and East regions to capitalise on strong demand for high-value products.",
            }

        if "fraud" in q or "document" in q or "compliance" in q or "report" in q:
            return {
                "summary": "Document search identified 2 relevant banking records — a Fraud Case Report and a Compliance Report — with 3 active fraud investigations totalling $32,101 at risk.",
                "insights": [
                    "3 fraud cases reported in Q1 2024: card-not-present attacks (2) and phishing credential theft (1)",
                    "Case FC-2024-003 is the most critical: $15,600 lost via phishing, referred to law enforcement",
                    "All 3 cases involve Credit Card products — no Home Loan or Savings Account fraud detected",
                    "Compliance score improved to 94/100 (up from 91) — MFA rollout is the top open item",
                ],
                "formatted_table": (
                    "| Case ID | Amount | Product | Status |\n"
                    "|---------|--------|---------|--------|\n"
                    "| FC-2024-001 | $12,000 | Credit Card | Under Investigation |\n"
                    "| FC-2024-002 | $4,500 | Credit Card | Resolved — Refund Issued |\n"
                    "| FC-2024-003 | $15,600 | Credit Card | Law Enforcement Referral |"
                ),
                "recommendations": "Accelerate mandatory MFA rollout and deploy real-time ML fraud scoring for transactions above $3,000, as recommended in the open compliance items.",
            }

        # Generic fallback
        return {
            "summary": "The query returned 20 banking transactions with a total portfolio value of approximately $636,000 across four product lines and four geographic regions.",
            "insights": [
                "Home Loans generate the highest individual transaction values ($52,000–$110,000)",
                "Credit Card transactions are most frequent but average only $8,317 per transaction",
                "The North and South regions show the most balanced product diversity",
                "All transactions fall within normal operating parameters — no anomalies detected",
            ],
            "formatted_table": (
                "| Product | Avg Revenue | Transactions |\n"
                "|---------|------------|-------------|\n"
                "| Home Loan | $80,500 | 5 |\n"
                "| Personal Loan | $32,500 | 4 |\n"
                "| Savings Account | $10,760 | 5 |\n"
                "| Credit Card | $8,317 | 6 |"
            ),
            "recommendations": "Consider cross-selling Personal Loans to active Credit Card customers — overlapping customer segments show strong upsell potential.",
        }
