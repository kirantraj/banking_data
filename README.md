# Banking Data Copilot

An enterprise-grade AI agent system built with Python, MCP (Model Context Protocol), Vertex AI Gemini, and BigQuery.
Non-technical banking users can query data using plain English — the system handles SQL generation, validation, execution, and explanation automatically.

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
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │   Planner    │──►│ SQL Generator│──►│  SQL Validator   │   │
│  │   Agent      │   │    Agent     │   │     Agent        │   │
│  │              │   │  NL → SQL    │   │ assess + correct  │   │
│  └──────┬───────┘   └──────────────┘   └──────────────────┘   │
│         │                                                        │
│  ┌──────▼───────┐                                               │
│  │  Explainer   │ ◄── results                                   │
│  │    Agent     │                                               │
│  └──────────────┘                                               │
└─────────────────────┬───────────────────────────────────────────┘
                      │  list_tools() / call_tool()
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                MCP CLIENT  (BankingMCPClient)                   │
│         Async context manager — spawns server subprocess        │
└─────────────────────┬───────────────────────────────────────────┘
                      │  stdio (JSON-RPC 2.0)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MCP SERVER  (server.py subprocess)             │
│                                                                 │
│   ┌─────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│   │  query_bigquery │  │  validate_sql  │  │search_documents│ │
│   │  SELECT only    │  │  safety rules  │  │ keyword search │ │
│   │  LIMIT enforced │  │  + schema check│  │ over .txt files│ │
│   └────────┬────────┘  └────────────────┘  └────────────────┘ │
└────────────┼────────────────────────────────────────────────────┘
             │
             ▼
    ┌────────────────┐      ┌──────────────────────────────┐
    │   BigQuery     │      │  data/documents/*.txt         │
    │  banking_demo  │      │  (fraud_cases.txt,            │
    │  .sales_data   │      │   compliance_report.txt)      │
    └────────────────┘      └──────────────────────────────┘
```

### Key Design Principles

| Principle | Implementation |
|-----------|----------------|
| Reasoning ≠ Execution | Agents only call Gemini. MCP tools only run I/O. Never mixed. |
| Safety first | `validate_sql` blocks DELETE/DROP/UPDATE before any query reaches BQ |
| Cost control | LIMIT auto-injected; BQ client runs in thread-pool (non-blocking) |
| Local testability | `USE_MOCK_DATA=true` runs the full pipeline without GCP credentials |
| Auditability | Every MCP tool call logged with args + truncated result |

---

## Project Structure

```
banking-data-copilot/
├── main.py                        # Entry point (interactive / demo / single query)
├── setup_bigquery.py              # One-time BQ dataset + table creation
├── requirements.txt
├── .env.example
│
├── config/
│   └── settings.py                # All configuration via env vars
│
├── agents/                        # LLM reasoning layer (Vertex AI Gemini)
│   ├── base.py                    # BaseAgent: generate() + mock fallback
│   ├── planner.py                 # Route: sql_query | document_search | combined
│   ├── sql_generator.py           # Natural language → BigQuery SQL
│   ├── sql_validator.py           # LLM assessment of MCP validation result
│   └── explainer.py               # Results → business English
│
├── mcp_server/                    # MCP server subprocess (execution only)
│   ├── server.py                  # MCP Server: list_tools + call_tool dispatcher
│   └── tools/
│       ├── bigquery_tool.py       # execute_bigquery_query()
│       ├── validate_sql.py        # validate_sql_query()  — pure, sync
│       └── search_docs.py         # search_documents()    — sliding-window scoring
│
├── mcp_client/
│   └── client.py                  # BankingMCPClient: async context manager
│
├── orchestrator/
│   └── copilot.py                 # BankingCopilot.answer() — the full pipeline
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
        └── sales_data.json        # Schema reference (for documentation)
```

---

## Quick Start (Local — No GCP Required)

```bash
# 1. Clone and enter the project
cd banking-data-copilot

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (mock mode works out of the box)
cp .env.example .env
# The default USE_MOCK_DATA=true means no GCP credentials needed

# 5. Run demo queries
python main.py --demo

# 6. Interactive mode
python main.py

# 7. Single query
python main.py "Top 5 customers by revenue"
```

---

## GCP / Vertex AI Setup

```bash
# 1. Set your project in .env
GCP_PROJECT_ID=your-project-id
USE_MOCK_DATA=false

# 2. Authenticate
gcloud auth application-default login

# 3. Enable APIs
gcloud services enable bigquery.googleapis.com aiplatform.googleapis.com

# 4. Create BigQuery table with sample data
python setup_bigquery.py

# 5. Run with real data
python main.py --demo
```

---

## Agent Pipeline — Step by Step

### Example: "Top 10 customers by transaction amount last month"

```
Step 1 — User Query
  "Top 10 customers by transaction amount last month"

Step 2 — PlannerAgent  [Gemini call #1]
  → pipeline: "sql_query"
  → sql_needed: true
  → reasoning: "Query asks for ranked data from the database"

Step 3 — SQLGeneratorAgent  [Gemini call #2]
  → sql: """
      SELECT customer_id,
             SUM(revenue) AS total_revenue,
             COUNT(*)     AS tx_count
      FROM `project.banking_demo.sales_data`
      WHERE DATE_TRUNC(date, MONTH) =
            DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
      GROUP BY customer_id
      ORDER BY total_revenue DESC
      LIMIT 10
    """

Step 4 — MCP: validate_sql  [tool call #1]
  → valid: true
  → warnings: []   (LIMIT already present)

Step 5 — SQLValidatorAgent  [Gemini call #3]
  → action: "approved"
  → corrected_sql: null

Step 6 — MCP: query_bigquery  [tool call #2]
  → 10 rows returned
  → top customer: C020 with $110,000

Step 7 — ExplainerAgent  [Gemini call #4]
  → summary: "Customer C020 leads with $110,000 in Home Loan transactions..."
  → insights: [...]
  → formatted_table: markdown

Final Response → displayed to user
```

---

## Sample Output

```
════════════════════════════════════════════════════════════════
  QUERY    : Show me the top 10 customers by total transaction amount
  PIPELINE : sql_query  |  ROWS: 10  |  TIME: 3.42s
════════════════════════════════════════════════════════════════

📊 SUMMARY
Customer C020 leads all clients with $110,000 in transactions, driven by a
single Home Loan disbursement — Home Loan customers dominate the top revenue tier.

💡 KEY INSIGHTS
   1. C020 generated the highest single transaction at $110,000 (Home Loan, West region)
   2. Home Loans account for 4 of the top 5 revenue positions
   3. West region customers average $91,250 per transaction vs the overall mean of $31,800
   4. Credit Card debit transactions are the most frequent but lowest-value category

📋 TOP RESULTS
| Customer | Product | Revenue | Region |
|----------|---------|---------|--------|
| C020 | Home Loan | $110,000 | West |
| C012 | Home Loan | $95,000 | West |
| C007 | Home Loan | $78,000 | East |
| C016 | Home Loan | $67,500 | West |
| C003 | Home Loan | $52,000 | East |

✅ RECOMMENDATION
Consider a priority relationship-manager programme for Home Loan customers
in the West region, who generate the highest revenue per transaction.

🔍 SQL EXECUTED
   SELECT customer_id, SUM(revenue) AS total_revenue ... LIMIT 10
════════════════════════════════════════════════════════════════
```

---

## Extending the System

### Add a New MCP Tool

```python
# mcp_server/tools/my_tool.py
def my_tool(param: str) -> dict:
    return {"result": "..."}

# mcp_server/server.py — add to list_tools() and call_tool() dispatcher
```

### Add a New Agent

```python
# agents/my_agent.py
from agents.base import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__("my_agent")

    def run(self, input: str) -> dict:
        return self.generate(self._build_prompt(input))

    def _build_prompt(self, input: str) -> str:
        return f"... {input} ... respond with JSON: {{}}"

    def _mock_response(self, prompt: str) -> dict:
        return {"result": "mock"}
```

### Add Voice Input

Replace `input("You: ")` in `main.py` with any speech-to-text library
(e.g. Google Cloud Speech-to-Text, Whisper). The rest of the pipeline is unchanged.

### Production Hardening Checklist

- [ ] Replace `QueryCache` with Redis for multi-process caching
- [ ] Add BigQuery row-level access controls per user role
- [ ] Stream results with `asyncio.Queue` for long-running queries
- [ ] Add Vertex AI Model Garden evaluation for SQL quality
- [ ] Replace sliding-window doc search with Vertex AI Matching Engine
- [ ] Add OpenTelemetry tracing across agent + MCP calls
- [ ] Store query history in BigQuery for analytics on usage patterns

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `mcp>=1.0.0` | Model Context Protocol client + server SDK |
| `google-cloud-aiplatform` | Vertex AI SDK (Gemini model access) |
| `google-cloud-bigquery` | BigQuery client |
| `python-dotenv` | `.env` file loading |

---

## Why MCP?

Model Context Protocol (MCP) is an open standard (by Anthropic) that
decouples **reasoning** (LLM) from **execution** (tools).

Benefits demonstrated here:
- The MCP server can be swapped for a remote server without touching agent code
- Tools are discoverable at runtime via `list_tools()` — new tools appear automatically
- The same MCP server can be reused by multiple agent applications
- Execution is isolated from the LLM: a misbehaving tool can't corrupt agent state
