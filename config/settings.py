"""
Central configuration for the Banking Data Copilot.
All values are read from environment variables with safe local defaults.
Copy .env.example → .env and fill in your GCP values before using real BigQuery.
"""
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # ── GCP ───────────────────────────────────────────────────────────────────
    project_id: str = field(
        default_factory=lambda: os.getenv("GCP_PROJECT_ID", "your-gcp-project")
    )
    location: str = field(
        default_factory=lambda: os.getenv("GCP_LOCATION", "us-central1")
    )

    # ── BigQuery ──────────────────────────────────────────────────────────────
    dataset_id: str = field(
        default_factory=lambda: os.getenv("BQ_DATASET_ID", "banking_demo")
    )
    table_id: str = field(
        default_factory=lambda: os.getenv("BQ_TABLE_ID", "sales_data")
    )
    max_rows: int = field(
        default_factory=lambda: int(os.getenv("BQ_MAX_ROWS", "100"))
    )

    # ── Vertex AI / Gemini ────────────────────────────────────────────────────
    model_name: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash-001")
    )

    # ── Documents ─────────────────────────────────────────────────────────────
    # Relative to the project root; resolved to absolute at runtime
    documents_path: str = field(
        default_factory=lambda: os.getenv("DOCS_PATH", "data/documents")
    )

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_ttl: int = field(
        default_factory=lambda: int(os.getenv("CACHE_TTL", "300"))
    )

    # ── Local testing ─────────────────────────────────────────────────────────
    # When True, all LLM and BQ calls return deterministic mock data so the
    # full pipeline can be exercised without any GCP credentials.
    use_mock_data: bool = field(
        default_factory=lambda: os.getenv("USE_MOCK_DATA", "false").lower() == "true"
    )


# Singleton — import this everywhere
settings = Settings()
