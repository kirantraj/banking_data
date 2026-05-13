"""
SQL Validator Agent

Receives the raw output from the MCP validate_sql tool and applies
LLM reasoning to decide:
  • "approved"  — SQL is safe, run as-is.
  • "corrected" — SQL had fixable issues; corrected_sql contains the fix.
  • "rejected"  — SQL is fundamentally unsafe; abort.

This two-stage approach (rule-based MCP tool + LLM reasoning) is
intentional: the rule-based tool catches obvious violations cheaply,
while the LLM handles ambiguous warnings and produces corrected SQL.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent


class SQLValidatorAgent(BaseAgent):

    def __init__(self):
        super().__init__("sql_validator")

    # ── Public API ────────────────────────────────────────────────────────────

    def assess_validation(self, sql: str, mcp_validation_result: dict) -> dict:
        """
        Use LLM reasoning to assess the MCP tool's validation report.

        Args:
            sql:                   The SQL string that was validated.
            mcp_validation_result: The dict returned by the validate_sql MCP tool.

        Returns:
            {
                "approved":      bool
                "corrected_sql": str | None   — fixed query if action=="corrected"
                "issues_found":  list[str]
                "action":        "approved" | "corrected" | "rejected"
            }
        """
        self.logger.info(
            f"Assessing validation: valid={mcp_validation_result.get('valid')}, "
            f"errors={mcp_validation_result.get('errors')}"
        )
        return self.generate(
            self._build_prompt(sql, mcp_validation_result), temperature=0.05
        )

    # ── Prompt ────────────────────────────────────────────────────────────────

    def _build_prompt(self, sql: str, validation_result: dict) -> str:
        return f"""You are a SQL safety reviewer for a production banking system.

Original SQL:
```sql
{sql}
```

Automated validation result:
  valid:    {validation_result.get("valid")}
  errors:   {validation_result.get("errors", [])}
  warnings: {validation_result.get("warnings", [])}

Your task:
  • If valid=true and no serious warnings → set action="approved", corrected_sql=null.
  • If valid=true but warnings exist (e.g. missing LIMIT) → set action="corrected",
    provide corrected_sql with the issue fixed.
  • If valid=false → attempt to fix the query into a safe SELECT statement.
    If fixable: action="corrected". If fundamentally unsafe: action="rejected".

Respond with valid JSON only — no markdown, no explanation outside the JSON:
{{
  "approved":      true | false,
  "corrected_sql": "<fixed SQL string>" | null,
  "issues_found":  ["<description>"],
  "action":        "approved" | "corrected" | "rejected"
}}"""

    # ── Mock ──────────────────────────────────────────────────────────────────

    def _mock_response(self, prompt: str) -> dict:
        has_errors = (
            '"valid": false' in prompt
            or '"valid":false' in prompt
            or "false" in prompt.split("valid")[1][:10] if "valid" in prompt else False
        )
        if has_errors:
            return {
                "approved": False,
                "corrected_sql": None,
                "issues_found": ["SQL contains unsafe operations"],
                "action": "rejected",
            }
        # Check if warnings suggest missing LIMIT
        if "LIMIT" in prompt and "No LIMIT" in prompt:
            # Extract the SQL and add LIMIT
            sql_start = prompt.find("```sql\n") + 7
            sql_end = prompt.find("\n```", sql_start)
            original_sql = prompt[sql_start:sql_end].strip() if sql_start > 7 else ""
            corrected = f"{original_sql.rstrip(';')} LIMIT 100" if original_sql else None
            return {
                "approved": False,
                "corrected_sql": corrected,
                "issues_found": ["Missing LIMIT clause — added LIMIT 100"],
                "action": "corrected",
            }
        return {
            "approved": True,
            "corrected_sql": None,
            "issues_found": [],
            "action": "approved",
        }
