"""
MCP Tool: search_documents

Searches local .txt files in the documents directory for content
matching a query string.

Algorithm: sliding-window term-frequency scoring.
- Split query into individual terms (stop words removed implicitly by length filter).
- For each document, count how many times each term appears.
- Find the 300-character window with the most term hits (the excerpt).
- Score = total hits / (word_count / 100)  — a density metric.

This is intentionally simple. Replace with a vector store (e.g. Vertex AI
Matching Engine, pgvector) for production semantic search.
"""
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("tools.search_docs")

EXCERPT_WINDOW = 300   # characters to include in each result excerpt
STEP_SIZE      = 50    # how far to advance the sliding window each iteration


def search_documents(query: str, max_results: int = 5) -> dict[str, Any]:
    """
    Search local banking documents for content matching a query.

    Args:
        query:       Free-text search string.
        max_results: Cap on how many documents to return.

    Returns:
        {
            "results": [
                {
                    "filename":        str,
                    "excerpt":         str,   # best matching 300-char window
                    "relevance_score": float,
                    "total_chars":     int
                },
                ...
            ],
            "query":                    str,
            "total_documents_searched": int,
            "error":                    str | None
        }
    """
    # Resolve documents path relative to project root (the CWD when main.py runs)
    docs_path = os.path.abspath(settings.documents_path)

    if not os.path.isdir(docs_path):
        logger.warning(f"Documents directory not found: {docs_path}")
        return {
            "results": [],
            "query": query,
            "total_documents_searched": 0,
            "error": f"Directory not found: {docs_path}",
        }

    # Tokenise query — ignore very short tokens (articles, prepositions)
    query_terms = [t.lower() for t in re.findall(r"\b\w+\b", query) if len(t) > 2]

    if not query_terms:
        return {
            "results": [],
            "query": query,
            "total_documents_searched": 0,
            "error": "No usable search terms after filtering",
        }

    results = []
    total_searched = 0

    for filename in sorted(os.listdir(docs_path)):
        if not filename.endswith(".txt"):
            continue
        total_searched += 1
        filepath = os.path.join(docs_path, filename)

        try:
            with open(filepath, encoding="utf-8") as fh:
                content = fh.read()
        except OSError as exc:
            logger.warning(f"Cannot read {filepath}: {exc}")
            continue

        score, excerpt = _score_and_excerpt(content, query_terms)

        if score > 0:
            results.append({
                "filename":        filename,
                "excerpt":         excerpt,
                "relevance_score": round(score, 4),
                "total_chars":     len(content),
            })

    results.sort(key=lambda r: r["relevance_score"], reverse=True)
    top = results[:max_results]
    logger.info(
        f"Document search '{query[:60]}': {len(top)}/{total_searched} docs matched"
    )

    return {
        "results": top,
        "query": query,
        "total_documents_searched": total_searched,
    }


def _score_and_excerpt(content: str, terms: list[str]) -> tuple[float, str]:
    """
    Return (relevance_score, best_excerpt) for a document.

    Score is term-hit density: total hits per 100 words.
    Excerpt is the EXCERPT_WINDOW-char slice with the most term hits.
    """
    content_lower = content.lower()
    word_count = len(re.findall(r"\b\w+\b", content_lower))

    total_hits = sum(content_lower.count(t) for t in terms)
    if total_hits == 0 or word_count == 0:
        return 0.0, ""

    # Sliding-window excerpt search
    best_pos, best_hits = 0, 0
    doc_len = len(content)
    for i in range(0, max(1, doc_len - EXCERPT_WINDOW), STEP_SIZE):
        chunk = content_lower[i : i + EXCERPT_WINDOW]
        hits = sum(chunk.count(t) for t in terms)
        if hits > best_hits:
            best_hits, best_pos = hits, i

    excerpt = content[best_pos : best_pos + EXCERPT_WINDOW].strip()
    score = total_hits / (word_count / 100)
    return score, excerpt
