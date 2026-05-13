"""
Banking Data Copilot — Orchestrator

BankingCopilot.answer() is the single entry point for the whole pipeline.

Flow:
  User Query
    │
    ▼
  PlannerAgent.plan()          — LLM decides: SQL? Docs? Both?
    │
    ├─► SQL Pipeline (if sql_needed)
    │     │
    │     ▼
    │   SQLGeneratorAgent.generate_sql()   — NL → SQL
    │     │
    │     ▼
    │   MCP: validate_sql                  — rule-based safety check
    │     │
    │     ▼
    │   SQLValidatorAgent.assess_validation() — LLM interprets result
    │     │                                    corrects if needed
    │     ▼
    │   MCP: query_bigquery                — execute on BQ
    │
    ├─► Document Pipeline (if doc_search_needed)
    │     │
    │     ▼
    │   MCP: search_documents              — keyword search over local files
    │
    ▼
  ExplainerAgent.explain_results()        — results → business language
    │
    ▼
  Structured response dict

Design rules:
  • BankingMCPClient is opened once per call — one subprocess per query.
  • SQL retries (MAX_SQL_RETRIES) handle transient generation failures.
  • Results are cached by query hash (QueryCache) to avoid re-running identical queries.
"""
import asyncio
import time
from typing import Any

from agents.planner import PlannerAgent
from agents.sql_generator import SQLGeneratorAgent
from agents.sql_validator import SQLValidatorAgent
from agents.explainer import ExplainerAgent
from mcp_client.client import BankingMCPClient
from utils.cache import QueryCache
from utils.logger import get_logger
from config.settings import settings

logger = get_logger("orchestrator")

MAX_SQL_RETRIES = 2
SCHEMA_COLUMNS  = ["date", "product", "revenue", "customer_id", "region", "transaction_type"]


class BankingCopilot:
    """
    Main orchestrator.  Instantiate once and call answer() repeatedly.
    The underlying agents and cache are reused across queries.
    """

    def __init__(self):
        self.planner       = PlannerAgent()
        self.sql_generator = SQLGeneratorAgent()
        self.sql_validator = SQLValidatorAgent()
        self.explainer     = ExplainerAgent()
        self.cache         = QueryCache(ttl_seconds=settings.cache_ttl)

    # ── Public API ────────────────────────────────────────────────────────────

    async def answer(self, user_query: str) -> dict[str, Any]:
        """
        Process a natural-language query end-to-end.

        Returns a structured dict ready for display or API serialisation:
          query, pipeline, sql_executed, row_count,
          summary, insights, formatted_table, recommendations,
          doc_results, elapsed_seconds, from_cache
        """
        t0 = time.perf_counter()
        logger.info(f"{'='*64}")
        logger.info(f"Query: {user_query}")

        # ── Cache check ───────────────────────────────────────────────────────
        cached = self.cache.get(user_query)
        if cached:
            logger.info("Cache hit — skipping pipeline")
            cached["from_cache"] = True
            return cached

        query_result: dict = {"rows": [], "row_count": 0, "sql_executed": ""}
        doc_results:  list = []
        sql_used:     str  = ""

        async with BankingMCPClient() as mcp:
            # ── Step 1: Discover tools (confirms MCP server is up) ────────────
            tools = await mcp.list_tools()
            tool_names = [t["name"] for t in tools]
            logger.info(f"MCP tools online: {tool_names}")

            # ── Step 2: Plan ──────────────────────────────────────────────────
            plan = self.planner.plan(user_query)
            logger.info(
                f"Plan → pipeline='{plan.get('pipeline')}' | "
                f"sql={plan.get('sql_needed')} | "
                f"docs={plan.get('doc_search_needed')} | "
                f"reason: {plan.get('reasoning')}"
            )

            # ── Step 3a: SQL pipeline ─────────────────────────────────────────
            if plan.get("sql_needed"):
                query_result, sql_used = await self._run_sql_pipeline(mcp, user_query)

            # ── Step 3b: Document search pipeline ────────────────────────────
            if plan.get("doc_search_needed"):
                search_query = " ".join(
                    plan.get("doc_search_terms") or [user_query]
                )
                doc_raw = await mcp.call_tool(
                    "search_documents",
                    {"query": search_query, "max_results": 5},  # int literal — no cast needed
                )
                doc_results = doc_raw.get("results", [])
                logger.info(f"Document search returned {len(doc_results)} result(s)")

        # ── Step 4: Explain ───────────────────────────────────────────────────
        explanation = self.explainer.explain_results(
            original_query=user_query,
            sql_executed=sql_used,
            query_result=query_result,
            doc_results=doc_results or None,
        )

        elapsed = round(time.perf_counter() - t0, 2)
        logger.info(f"Pipeline complete in {elapsed}s")

        response: dict[str, Any] = {
            "query":           user_query,
            "pipeline":        plan.get("pipeline", "unknown"),
            "sql_executed":    sql_used,
            "row_count":       query_result.get("row_count", 0),
            "summary":         explanation.get("summary", ""),
            "insights":        explanation.get("insights", []),
            "formatted_table": explanation.get("formatted_table", ""),
            "recommendations": explanation.get("recommendations", ""),
            "doc_results":     doc_results,
            "elapsed_seconds": elapsed,
            "from_cache":      False,
        }

        self.cache.set(user_query, response)
        return response

    # ── Internal pipeline steps ───────────────────────────────────────────────

    async def _run_sql_pipeline(
        self, mcp: BankingMCPClient, user_query: str
    ) -> tuple[dict, str]:
        """
        NL → SQL → validate → execute, with up to MAX_SQL_RETRIES attempts.

        Returns (bq_result_dict, sql_string).
        On all attempts failing, returns an empty-rows dict.
        """
        for attempt in range(1, MAX_SQL_RETRIES + 1):
            logger.info(f"SQL pipeline attempt {attempt}/{MAX_SQL_RETRIES}")

            # ── Generate ──────────────────────────────────────────────────────
            gen = self.sql_generator.generate_sql(user_query)
            if "error" in gen:
                logger.warning(f"SQL generation error: {gen['error']}")
                continue

            sql = gen.get("sql", "").strip()
            if not sql:
                logger.warning("SQL generator returned empty SQL")
                continue

            logger.info(f"Generated: {sql[:140]}")

            # ── Validate (MCP tool — rule-based) ──────────────────────────────
            mcp_val = await mcp.call_tool(
                "validate_sql",
                {"sql": sql, "schema_columns": SCHEMA_COLUMNS},
            )

            # ── Assess (LLM — interprets warnings, corrects if needed) ────────
            assessment = self.sql_validator.assess_validation(sql, mcp_val)
            action = assessment.get("action", "rejected")
            logger.info(
                f"Validation assessment: action='{action}' | "
                f"issues={assessment.get('issues_found', [])}"
            )

            if action == "corrected":
                corrected = assessment.get("corrected_sql")
                if corrected:
                    logger.info(f"Using corrected SQL: {corrected[:140]}")
                    sql = corrected

            elif action == "rejected":
                logger.warning(
                    f"SQL rejected on attempt {attempt}: "
                    f"{assessment.get('issues_found')}"
                )
                if attempt == MAX_SQL_RETRIES:
                    return (
                        {
                            "rows": [],
                            "row_count": 0,
                            "sql_executed": sql,
                            "error": "SQL rejected after all retries",
                        },
                        sql,
                    )
                continue  # regenerate on next attempt

            # ── Execute (MCP tool — hits BigQuery) ────────────────────────────
            bq_result = await mcp.call_tool(
                "query_bigquery",
                {"sql": sql, "limit": int(settings.max_rows)},
            )

            if bq_result.get("success"):
                logger.info(f"Query succeeded: {bq_result.get('row_count')} rows")
                return bq_result, sql

            logger.warning(
                f"BQ execution failed (attempt {attempt}): "
                f"{bq_result.get('error')}"
            )
            if attempt == MAX_SQL_RETRIES:
                return bq_result, sql

        # All retries exhausted
        return {"rows": [], "row_count": 0, "sql_executed": "", "error": "All retries exhausted"}, ""
