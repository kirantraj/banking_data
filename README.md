# 🏦 Banking Data Copilot

> A production-grade multi-agent AI system that lets business users query complex banking datasets using plain English — no SQL required.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vertex AI](https://img.shields.io/badge/Google-Vertex%20AI-4285F4.svg)](https://cloud.google.com/vertex-ai)
[![MCP](https://img.shields.io/badge/Protocol-MCP-green.svg)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📌 Overview

The Banking Data Copilot bridges the gap between business users and financial data. Instead of writing SQL or waiting for a data team, users simply ask questions in plain English:

> *"Which customers had more than 5 transactions over $10,000 in the last 90 days?"*

The system handles the rest — decomposing the question, generating and validating SQL, executing it safely, and returning a human-readable explanation.

Built as a capstone project for the [5-Day AI Agents Intensive Vibe Coding Course with Google](https://www.kaggle.com/competitions/5-day-ai-agents-intensive-vibecoding-course-with-google) on Kaggle.

---

## 🏗️ Architecture

The system is composed of four specialized agents connected through an MCP (Model Context Protocol) server:

```
User Natural Language Question
        │
        ▼
┌─────────────────┐
│  Planner Agent  │  ← Decomposes the question into a structured query plan
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SQL Generator  │  ← Translates plan to SQL using schema context
│  Agent          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Validator      │  ← Reviews SQL for correctness and safety
│  Agent          │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────┐
│         MCP Server           │
│  • execute_query(sql)        │
│  • get_schema()              │
│  • validate_sql(sql)         │
└────────┬─────────────────────┘
         │
         ▼
┌─────────────────┐
│  Explainer      │  ← Translates results into business narrative
│  Agent          │
└────────┬────────┘
         │
         ▼
  Human-Readable Answer
```

### Agent Responsibilities

| Agent | Role |
|---|---|
| **Planner** | Decomposes natural language into a structured query plan (JSON output) |
| **SQL Generator** | Converts the plan into syntactically correct SQL using live schema context |
| **Validator** | Checks SQL for safety (blocks DROP/DELETE/UPDATE) and schema alignment |
| **Explainer** | Returns results as a plain-English business narrative with domain context |

### MCP Server Tools

| Tool | Description |
|---|---|
| `execute_query(sql)` | Runs validated SQL against the banking dataset |
| `get_schema()` | Returns live database schema to ground the SQL Generator |
| `validate_sql(sql)` | Rule-based safety check before execution |

---

## 🔒 Security Design

Security is a first-class concern throughout the system:

- **No direct database access** — all data operations go through the MCP server's tool interface
- **Read-only enforcement** — the Validator agent and `validate_sql` tool block all destructive SQL (DROP, DELETE, UPDATE, INSERT)
- **Credential safety** — all API keys and credentials managed via environment variables, never hardcoded
- **`.env` excluded** — credentials are never committed to version control (see `.gitignore`)
- **Application Default Credentials (ADC)** — used for Google Cloud authentication, following GCP security best practices

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| LLM / Agent backbone | Google Vertex AI (Gemini) |
| Agent protocol | Model Context Protocol (MCP) |
| MCP server | FastAPI (Python) |
| Orchestration | Python |
| Database | SQLite (local) / BigQuery (cloud) |
| Deployment target | Google Cloud Run |

---

## 📋 Prerequisites

- Python 3.10+
- Google Cloud account with Vertex AI API enabled
- Gemini API access (via Vertex AI or AI Studio)
- `gcloud` CLI installed and authenticated

---

## ⚙️ Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/kirantraj/banking_data.git
cd banking_data
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```env
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_REGION=us-central1
VERTEX_AI_MODEL=gemini-1.5-pro
DATABASE_PATH=data/banking.db
MCP_SERVER_PORT=8000
```

> ⚠️ **Never commit your `.env` file.** It is excluded via `.gitignore`.

### 5. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

### 6. Start the MCP server

```bash
python mcp_server.py
```

The server will start on `http://localhost:8000`. You should see:

```
MCP Server running on port 8000
Tools registered: execute_query, get_schema, validate_sql
```

### 7. Run the agent

```bash
python main.py
```

---

## 💬 Example Interaction

**User input:**
```
Which customers had more than 5 transactions over $10,000 in the last 90 days?
```

**Planner Agent:**
```json
{
  "intent": "aggregate_filter",
  "table": "transactions",
  "filters": ["amount > 10000", "transaction_date >= DATE('now', '-90 days')"],
  "group_by": "customer_id",
  "having": "COUNT(*) > 5",
  "output": ["customer_id", "transaction_count"]
}
```

**SQL Generator:**
```sql
SELECT customer_id, COUNT(*) as txn_count
FROM transactions
WHERE amount > 10000
  AND transaction_date >= DATE('now', '-90 days')
GROUP BY customer_id
HAVING COUNT(*) > 5
ORDER BY txn_count DESC;
```

**Validator:**
```
✅ No destructive operations detected.
✅ Schema fields verified: transactions.customer_id, transactions.amount, transactions.transaction_date
✅ Approved for execution.
```

**Explainer Agent:**
```
3 customers exceeded the high-value transaction threshold in the last 90 days.
Customer C-4471 had the highest activity with 12 transactions averaging $47,300 each.
This pattern may warrant closer review from a compliance or fraud detection standpoint.
```

---

## 📁 Project Structure

```
banking_data/
│
├── main.py                  # Entry point — orchestrates the agent pipeline
├── mcp_server.py            # FastAPI MCP server exposing data tools
├── requirements.txt
├── .env.example             # Template for environment variables
├── .gitignore               # Excludes .env and credentials
│
├── agents/
│   ├── planner.py           # Planner Agent — decomposes user questions
│   ├── sql_generator.py     # SQL Generator Agent — produces SQL queries
│   ├── validator.py         # Validator Agent — safety and schema checks
│   └── explainer.py         # Explainer Agent — human-readable results
│
├── tools/
│   ├── execute_query.py     # MCP tool: runs SQL against database
│   ├── get_schema.py        # MCP tool: returns database schema
│   └── validate_sql.py      # MCP tool: rule-based SQL safety check
│
├── data/
│   └── banking.db           # SQLite banking dataset (synthetic)
│
└── docs/
    └── architecture.png     # Architecture diagram
```

---

## 🚀 Deployment (Google Cloud Run)

The MCP server is containerized for deployment on Cloud Run:

```bash
# Build container
docker build -t banking-data-copilot .

# Push to Artifact Registry
docker tag banking-data-copilot gcr.io/YOUR_PROJECT/banking-data-copilot
docker push gcr.io/YOUR_PROJECT/banking-data-copilot

# Deploy to Cloud Run
gcloud run deploy banking-data-copilot \
  --image gcr.io/YOUR_PROJECT/banking-data-copilot \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

---

## 🧠 Key Design Decisions

**Why four agents instead of one?**
A single LLM prompt could attempt all steps but fails in predictable ways — hallucinated SQL, no validation, no recovery. Separating into specialized agents lets each one fail gracefully and allows the pipeline to catch errors at each stage.

**Why MCP for the tool layer?**
MCP creates a clean, enforced boundary between agent reasoning and data execution. Agents cannot access the database directly — they must use the tools exposed by the MCP server. This makes the system auditable and safe by design.

**Why inject schema on every call?**
Early testing showed the SQL Generator frequently produced wrong field names without live schema context. Calling `get_schema()` on every request grounds the agent in the actual database structure and eliminates this class of errors.

---

## 📚 Course Concepts Applied

This project applies the following concepts from the 5-Day AI Agents Intensive:

| Concept | Where |
|---|---|
| Multi-agent system | `agents/` — four specialized agents with clear boundaries |
| MCP Server | `mcp_server.py` + `tools/` |
| Security features | Validator agent, `validate_sql` tool, ADC authentication |
| Deployability | Cloud Run deployment via Docker |
| Agent skills | Explainer agent (domain-aware financial narrative generation) |

---

## 🗺️ Roadmap

- [ ] Streamlit / Gradio front-end for interactive web UI
- [ ] Multi-table JOIN support for complex analytical queries
- [ ] Conversation memory for follow-up question context
- [ ] Live Cloud Run deployment with public demo endpoint
- [ ] BigQuery backend for production-scale datasets

---

## 👤 Author

**Kiran Thyagaraj**  
Senior Data Engineer | AI/ML Practitioner  
[GitHub](https://github.com/kirantraj) · [LinkedIn](https://linkedin.com/in/kiran-thyagaraj)

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

*Built with Google Vertex AI, Gemini, Model Context Protocol (MCP), Python, and FastAPI.*  
*Submitted as a capstone project for the Kaggle 5-Day AI Agents Intensive Vibe Coding Course with Google.*
