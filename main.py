"""
Banking Data Copilot — Entry Point

Usage:
  python main.py                              # Interactive REPL
  python main.py "Top 10 customers..."        # Single query
  python main.py --demo                       # Run all demo queries
"""
import asyncio
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── Load .env (optional — works fine without it) ──────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from orchestrator.copilot import BankingCopilot
from utils.logger import get_logger

logger = get_logger("main")

DEMO_QUERIES = [
    "Show me the top 10 customers by total transaction amount",
    "What is the total revenue broken down by product?",
    "Which region has the highest transaction volume?",
    "Show me all credit transactions above $20,000",
    "Show documents related to fraud cases in the last 30 days",
]

DIVIDER = "═" * 64


def display_response(resp: dict) -> None:
    """Pretty-print a copilot response to the terminal."""
    print(f"\n{DIVIDER}")
    print(f"  QUERY    : {resp['query']}")
    print(f"  PIPELINE : {resp['pipeline']}  |  ROWS: {resp['row_count']}  |  TIME: {resp['elapsed_seconds']}s", end="")
    if resp.get("from_cache"):
        print("  [CACHED]", end="")
    print()
    print(DIVIDER)

    print(f"\n📊 SUMMARY\n{resp['summary']}")

    if resp.get("insights"):
        print("\n💡 KEY INSIGHTS")
        for i, insight in enumerate(resp["insights"], 1):
            print(f"   {i}. {insight}")

    if resp.get("formatted_table"):
        print(f"\n📋 TOP RESULTS\n{resp['formatted_table']}")

    if resp.get("recommendations"):
        print(f"\n✅ RECOMMENDATION\n{resp['recommendations']}")

    if resp.get("doc_results"):
        print(f"\n📄 DOCUMENTS FOUND ({len(resp['doc_results'])})")
        for doc in resp["doc_results"][:3]:
            score = doc.get("relevance_score", 0)
            print(f"   [{score:.3f}] {doc['filename']}")
            excerpt = doc.get("excerpt", "")[:160].replace("\n", " ")
            print(f"           {excerpt}…")

    if resp.get("sql_executed"):
        print(f"\n🔍 SQL EXECUTED\n   {resp['sql_executed']}")

    print(f"\n{DIVIDER}\n")


async def run_single(query: str) -> None:
    copilot = BankingCopilot()
    resp = await copilot.answer(query)
    display_response(resp)


async def run_demo() -> None:
    print(f"\n{'─'*64}")
    print("  Banking Data Copilot — Demo Mode")
    print(f"{'─'*64}")
    copilot = BankingCopilot()
    for query in DEMO_QUERIES:
        resp = await copilot.answer(query)
        display_response(resp)
        await asyncio.sleep(0.3)


async def run_interactive() -> None:
    print(f"\n{'─'*64}")
    print("  Banking Data Copilot — Interactive Mode")
    print("  Type your question and press Enter.  'exit' to quit.")
    print(f"{'─'*64}\n")
    copilot = BankingCopilot()
    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit", "q", ":q"}:
            print("Goodbye!")
            break
        resp = await copilot.answer(query)
        display_response(resp)


async def main() -> None:
    args = sys.argv[1:]
    if not args:
        await run_interactive()
    elif args[0] == "--demo":
        await run_demo()
    else:
        await run_single(" ".join(args))


if __name__ == "__main__":
    asyncio.run(main())
