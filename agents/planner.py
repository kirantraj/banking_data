"""
Planner Agent

Analyses the user's natural-language query and decides which
pipeline to run:
  • sql_query       — analytical data questions (revenue, counts, trends)
  • document_search — policy / fraud / compliance document lookups
  • combined        — needs both live data AND document context

Output drives the orchestrator's branching logic in copilot.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
from config.settings import settings


class PlannerAgent(BaseAgent):

    def __init__(self):
        super().__init__("planner")

    # ── Public API ────────────────────────────────────────────────────────────

    def plan(self, user_query: str) -> dict:
        """
        Return a routing plan dict for the orchestrator.

        Keys:
            pipeline          str   "sql_query" | "document_search" | "combined"
            reasoning         str   One-sentence explanation of the routing decision
            sql_needed        bool
            doc_search_needed bool
            doc_search_terms  list[str]   Search terms if doc_search_needed
        """
        self.logger.info(f"Planning for: '{user_query[:80]}'")
        return self.generate(self._build_prompt(user_query))

    # ── Prompt ────────────────────────────────────────────────────────────────

    def _build_prompt(self, user_query: str) -> str:
        full_table = (
            f"`{settings.project_id}.{settings.dataset_id}.{settings.table_id}`"
        )
        return f"""You are the routing brain of a Banking Data Copilot.
Analyse the user query and decide which processing pipeline to use.

User Query: "{user_query}"

Available pipelines
  "sql_query"       — Use when the question asks for numbers, aggregations, trends,
                      rankings, or any data that lives in the database.
                      Examples: revenue, top customers, transaction counts, averages.
  "document_search" — Use when the question asks about documents, cases, policies,
                      reports, compliance rules, or incident records.
                      Examples: fraud cases, audit reports, compliance policies.
  "combined"        — Use when the question genuinely needs BOTH live data AND documents.

BigQuery table: {full_table}
Columns: date (DATE), product (STRING), revenue (FLOAT64),
         customer_id (STRING), region (STRING), transaction_type (STRING)

Respond with valid JSON only — no markdown, no explanation outside the JSON:
{{
  "pipeline":          "sql_query" | "document_search" | "combined",
  "reasoning":         "<one sentence>",
  "sql_needed":        true | false,
  "doc_search_needed": true | false,
  "doc_search_terms":  ["term1", "term2"]
}}"""

    # ── Mock ──────────────────────────────────────────────────────────────────

    def _mock_response(self, prompt: str) -> dict:
        import re
        # Extract only the user's actual question — avoid matching boilerplate in the prompt
        # template itself (which contains words like "fraud cases", "audit reports", etc.)
        match = re.search(r'User Query: "([^"]+)"', prompt)
        q = match.group(1).lower() if match else prompt.lower()

        doc_keywords = {"fraud", "document", "policy", "compliance", "report", "case", "audit", "incident"}
        sql_keywords = {"revenue", "top", "total", "amount", "sum", "count", "average",
                        "region", "product", "highest", "lowest", "transaction", "customer",
                        "last month", "this year", "credit", "debit", "above", "below"}

        is_doc = any(kw in q for kw in doc_keywords)
        is_sql = any(kw in q for kw in sql_keywords)

        if is_doc and is_sql:
            return {
                "pipeline": "combined",
                "reasoning": "Query references both live data and documents.",
                "sql_needed": True,
                "doc_search_needed": True,
                "doc_search_terms": ["fraud", "compliance"],
            }
        if is_doc and not is_sql:
            return {
                "pipeline": "document_search",
                "reasoning": "Query is about documents or case records.",
                "sql_needed": False,
                "doc_search_needed": True,
                "doc_search_terms": [w for w in q.split() if len(w) > 3][:4],
            }
        return {
            "pipeline": "sql_query",
            "reasoning": "Query asks for analytical data from the database.",
            "sql_needed": True,
            "doc_search_needed": False,
            "doc_search_terms": [],
        }
