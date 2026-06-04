# Banking Data Copilot

A multi-agent AI system that lets non-technical users query BigQuery in plain English. Built with Python, MCP (Model Context Protocol), Vertex AI Gemini, and BigQuery.

The agents handle natural-language understanding, SQL generation, validation, and explanation. The MCP layer handles the actual execution against BigQuery and local documents. Reasoning and execution stay strictly separated, which is what makes the system safe to point at real data.

---

## Why this project

I built this to learn how production-pattern agentic systems are actually structured, coming from a data engineering background. Specifically:

* How to separate LLM reasoning from deterministic tool execution
* How MCP fits between agents and tools as a clean protocol boundary
* How to apply defense-in-depth safety around LLM-generated SQL
* How to design narrow, single-responsibility agents instead of one giant prompt

The codebase reflects those goals. It is intentionally simple enough to read end-to-end in 30 minutes, while still showing the patterns I would carry into a real production system.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Query (NL)                          │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT LAYER  (Vertex AI Gemini)              │
│                                                                 │
│   Planner  →  SQL Generator  →  SQL Validator (LLM)             │
│      │              │                  │                        │
│      └──────────────┴──────────────────┘                        │
│                                                                 │
│                       Explainer  ◄── results                    │
└─────────────────────┬───────────────────────────────────────────┘
                      │  list_tools() / call_tool()
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                MCP CLIENT  (BankingMCPClient)                   │
│       Async context manager that spawns the server subprocess   │
└─────────────────────┬───────────────────────────────────────────┘
                      │  stdio (JSON-RPC 2.0)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MCP SERVER  (separate process)                 │
│                                                                 │
│   ┌─────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│   │  query_bigquery │  │  validate_sql  │  │search_documents│  │
│   │  SELECT only    │  │  safety rules  │  │ keyword search │  │
│   │  LIMIT enforced │  │  + table allow │  │ over .txt      │  │
│   └────────┬────────┘  └────────────────┘  └────────────────┘  │
└────────────┼────────────────────────────────────────────────────┘
             │
             ▼
    ┌────────────────┐      ┌──────────────────────────────┐
    │   BigQuery     │      │  data/documents/*.txt        │
    │  banking_demo  │      │  (fraud_cases.txt,           │
    │  .sales_data   │      │   compliance_report.txt)     │
    └────────────────┘      └──────────────────────────────┘
```

### Key design principles

| Principle              | Implementation                                                              |
| ---------------------- | --------------------------------------------------------------------------- |
| Reasoning vs execution | Agents call Gemini. MCP tools run I/O. Never mixed.                         |
| Defense in depth       | LLM validator (semantic) plus deterministic `validate_sql` tool (safety)    |
| Cost control           | Mandatory dry-run, `maximum_bytes_billed` cap, and auto-injected `LIMIT`    |
| Local testability      | `USE_MOCK_DATA=true` runs the full pipeline without GCP credentials         |
| Auditability           | Every agent and tool call is logged with inputs and truncated outputs       |

---

## Quick start (no GCP required)

The fastest way to see the system in action. Mock mode runs the full pipeline end-to-end with no Gemini calls and no BigQuery setup.

```bash
# 1. Clone and enter the project
git clone https://github.com/kirantraj/banking_data.git
cd banking_data

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the example config (mock mode is on by default)
cp .env.example .env

# 5. Run a demo query
python main.py "Top 5 customers by revenue"

# Or run several pre-built demo queries
python main.py --demo

# Or open an interactive session
python main.py
```

In mock mode you will see the full agent pipeline run, with stubbed Gemini responses and a fake BigQuery dataset. This is enough to understand the flow without spending a dollar.

---

## GCP and Vertex AI setup

When you are ready to run against real Gemini and real BigQuery:

```bash
# 1. Update .env
GCP_PROJECT_ID=your-project-id
USE_MOCK_DATA=false

# 2. Authenticate locally
gcloud auth application-default login

# 3. Enable required APIs
gcloud services enable bigquery.googleapis.com aiplatform.googleapis.com

# 4. Create the demo BigQuery dataset and table
python setup_bigquery.py

# 5. Run with real data
python main.py --demo
```

---

## Project structure

```
banking_data/
├── main.py                        # Entry point: interactive, demo, or single query
├── setup_bigquery.py              # One-time BQ dataset and table creation
├── requirements.txt
├── .env.example
│
├── config/
│   └── settings.py                # All configuration via env vars
│
├── agents/                        # LLM reasoning layer (Vertex AI Gemini)
│   ├── base.py                    # BaseAgent with generate() and mock fallback
│   ├── planner.py                 # Routes queries to sql, docs, or both
│   ├── sql_generator.py           # Natural language to BigQuery SQL
│   ├── sql_validator.py           # LLM semantic review of generated SQL
│   └── explainer.py               # Results to business English
│
├── mcp_server/                    # MCP server subprocess (execution only)
│   ├── server.py                  # list_tools and call_tool dispatcher
│   └── tools/
│       ├── bigquery_tool.py       # query_bigquery: dry-run, cost cap, execute
│       ├── validate_sql.py        # validate_sql: sqlparse + regex safety
│       └── search_docs.py         # search_documents: keyword scoring
│
├── mcp_client/
│   └── client.py                  # BankingMCPClient: async context manager
│
├── orchestrator/
│   └── copilot.py                 # BankingCopilot.answer(): the full pipeline
│
├── utils/
│   ├── logger.py                  # Structured console logging
│   └── cache.py                   # In-memory TTL cache (MD5-keyed)
│
└── data/
    ├── documents/                 # Source files for document search
    │   ├── fraud_cases.txt
    │   └── compliance_report.txt
    └── schema/
        └── sales_data.json        # Schema reference for documentation
```

---

## Agent pipeline, step by step

The exact sequence the system runs when you ask a question.

### Example: "Top 10 customers by transaction amount last month"

```
Step 1. User query arrives at the orchestrator.

Step 2. PlannerAgent  [Gemini call #1]
        Decides the route: "sql_query"
        Reasoning: "User asks for ranked data from the database"

Step 3. SQLGeneratorAgent  [Gemini call #2]
        Generates the SQL using the schema in its prompt:

        SELECT customer_id,
               SUM(revenue) AS total_revenue,
               COUNT(*)     AS tx_count
        FROM `project.banking_demo.sales_data`
        WHERE DATE_TRUNC(date, MONTH) =
              DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
        GROUP BY customer_id
        ORDER BY total_revenue DESC
        LIMIT 10

Step 4. SQLValidatorAgent  [Gemini call #3]
        Semantic review: does this SQL actually answer the question?
        Result: approved

Step 5. MCP: validate_sql  [tool call #1]
        Deterministic safety check (sqlparse + regex):
        - Must start with SELECT
        - No DROP, DELETE, UPDATE, TRUNCATE, etc.
        - Table must be in the allowlist
        - LIMIT auto-injected if missing
        Result: valid

Step 6. MCP: query_bigquery  [tool call #2]
        - Re-validates the SQL inside the tool
        - Runs a dry-run to estimate bytes scanned
        - Refuses anything over the cost cap
        - Executes with maximum_bytes_billed set
        Result: 10 rows returned

Step 7. ExplainerAgent  [Gemini call #4]
        Receives the rows and produces a plain-English summary.
        The prompt forbids inventing figures not present in the data.

Step 8. Final response is cached and returned to the user.
```

Total: 4 Gemini calls, 2 MCP tool calls, typically 5 to 8 seconds end to end.

---

## Sample output

```
================================================================
  QUERY    : Show me the top 10 customers by total transaction amount
  PIPELINE : sql_query  |  ROWS: 10  |  TIME: 3.42s
================================================================

SUMMARY
Customer C020 leads all clients with $110,000 in transactions, driven
by a single Home Loan disbursement. Home Loan customers dominate the
top revenue tier, with C012 at $95,000 and C007 at $78,000 rounding
out the top three.

TOP RESULTS
| Customer | Product   | Revenue   | Region |
|----------|-----------|-----------|--------|
| C020     | Home Loan | $110,000  | West   |
| C012     | Home Loan | $95,000   | West   |
| C007     | Home Loan | $78,000   | East   |
| C016     | Home Loan | $67,500   | West   |
| C003     | Home Loan | $52,000   | East   |

SQL EXECUTED
SELECT customer_id, SUM(revenue) AS total_revenue ... LIMIT 10
================================================================
```

The Explainer agent is intentionally constrained to summarize what the data shows. It does not produce business recommendations or projections, because hallucinated advice in a banking context is a real risk. If you want recommendations, that belongs in a separate agent with explicit guardrails.

---

## Safety model

LLMs can be jailbroken, hallucinate, or change behavior between model versions. So the system never relies on the LLM to decide whether a query is safe to run. It relies on deterministic code.

There are four independent layers between a user question and BigQuery:

1. **Prompt-level constraints** in the SQL generator. The model is told it can only produce SELECT statements and must include LIMIT. This is the first filter, not the last.
2. **LLM semantic review** by the validator agent. Catches questions where the SQL is syntactically correct but does not actually match user intent. (Example: user asks for top customers, SQL groups by product.)
3. **Deterministic safety check** in the `validate_sql` MCP tool. Uses `sqlparse` plus regex. Rejects forbidden keywords, multi-statement queries, and non-allowlisted tables. Injects LIMIT if missing. This layer cannot be reasoned with, which is the point.
4. **BigQuery `maximum_bytes_billed`** cap. The last line of defense. Even if everything above failed, BigQuery itself refuses to bill more than the configured ceiling.

If layer 3 is removed, the system is not safe regardless of how good the LLM validator is. Anything that can be reasoned with cannot be a security boundary.

---

## Why MCP?

MCP is an open protocol that defines how an AI system talks to tools. It is what cleanly separates the "thinking" layer from the "doing" layer in this project.

Concretely, MCP gives me:

* **Transport independence**. The MCP server runs as a local subprocess today over stdio. It could move to a remote HTTP/SSE service tomorrow without any agent-side code changes.
* **Runtime tool discovery**. Agents call `list_tools()` to find what is available. New tools appear automatically.
* **Process isolation**. The MCP server is its own OS process. If a tool crashes, the agents keep running.
* **Reusability**. The same MCP server could be plugged into a different MCP-aware client (Claude, another Gemini app, anything) without changes.

For a three-tool demo this is overkill. For a real system with dozens of tools across multiple teams, this is the difference between a clean protocol boundary and an integration nightmare.

---

## Limitations and what I would improve

This is a portfolio project, not a production system. A few things I know are limitations:

* **Impossible questions are handled poorly.** If the user asks about a column that does not exist (e.g., `customer_name` when the schema has none), the SQL generator will hallucinate, the validators will not catch it, BigQuery will return a column-not-found error, and the retry loop will burn Gemini calls without making progress. A better design would have the planner detect impossible questions upfront.
* **The keyword document search is primitive.** It is fine for a demo but would not scale past a few dozen documents. In production this would be a vector store (Vertex AI Matching Engine or pgvector) with embeddings.
* **The cache is in-memory.** Process-local, lost on restart, no multi-user awareness. Production would use Redis.
* **No row-level access control.** All queries run as the same service account. A real banking system would scope BigQuery permissions per user role.
* **No evaluation harness.** I tested manually with a small set of queries. A production version would have a regression suite of NL-to-SQL pairs with automated accuracy scoring.
* **Streaming is not supported.** Long-running queries block the caller. Should be moved to `asyncio.Queue` or server-sent events.

I deliberately left these out to keep the codebase short and readable. They are real and I know where they would go.

---

## Extending the system

### Add a new MCP tool

```python
# mcp_server/tools/my_tool.py
def my_tool(param: str) -> dict:
    return {"result": "..."}

# Then register it in mcp_server/server.py inside list_tools()
# and the call_tool() dispatcher.
```

The agents will discover it automatically via `list_tools()`. No changes needed in the agent layer.

### Add a new agent

```python
# agents/my_agent.py
from agents.base import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__("my_agent")

    def run(self, user_input: str) -> dict:
        return self.generate(self._build_prompt(user_input))

    def _build_prompt(self, user_input: str) -> str:
        return f"... {user_input} ... respond with JSON: {{}}"

    def _mock_response(self, prompt: str) -> dict:
        return {"result": "mock"}
```

Then wire it into `orchestrator/copilot.py` at the point in the pipeline where it should run.

### Add voice input

Replace `input("You: ")` in `main.py` with any speech-to-text library (Google Cloud Speech-to-Text, Whisper). The rest of the pipeline is unchanged because the input contract is just a string.

---

## Dependencies

| Package                   | Purpose                                    |
| ------------------------- | ------------------------------------------ |
| `mcp>=1.0.0`              | Model Context Protocol client and server   |
| `google-cloud-aiplatform` | Vertex AI SDK (Gemini)                     |
| `google-cloud-bigquery`   | BigQuery client                            |
| `python-dotenv`           | `.env` file loading                        |
| `sqlparse`                | SQL parsing for the validator tool         |

---

## Feedback welcome

If you build something similar, or if you spot something I got wrong, open an issue or reach out. Both are useful.
