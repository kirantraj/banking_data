"""
BigQuery Setup Script

Creates the banking_demo dataset and sales_data table, then inserts
20 sample rows so you can run the copilot against real BigQuery.

Run once:
    python setup_bigquery.py

Prerequisites:
    • GCP_PROJECT_ID set in .env (or environment)
    • Application Default Credentials: `gcloud auth application-default login`
    • google-cloud-bigquery installed: `pip install google-cloud-bigquery`
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config.settings import settings

SAMPLE_ROWS = [
    {"date": "2024-01-15", "product": "Savings Account",  "revenue":  15000.00, "customer_id": "C001", "region": "North", "transaction_type": "credit"},
    {"date": "2024-01-16", "product": "Credit Card",       "revenue":   8500.50, "customer_id": "C002", "region": "South", "transaction_type": "debit"},
    {"date": "2024-01-17", "product": "Home Loan",         "revenue":  52000.00, "customer_id": "C003", "region": "East",  "transaction_type": "credit"},
    {"date": "2024-01-18", "product": "Savings Account",  "revenue":   3200.00, "customer_id": "C004", "region": "West",  "transaction_type": "credit"},
    {"date": "2024-01-19", "product": "Credit Card",       "revenue":  12000.75, "customer_id": "C005", "region": "North", "transaction_type": "debit"},
    {"date": "2024-01-20", "product": "Personal Loan",    "revenue":  25000.00, "customer_id": "C006", "region": "South", "transaction_type": "credit"},
    {"date": "2024-01-21", "product": "Home Loan",         "revenue":  78000.00, "customer_id": "C007", "region": "East",  "transaction_type": "credit"},
    {"date": "2024-01-22", "product": "Credit Card",       "revenue":   4500.25, "customer_id": "C008", "region": "West",  "transaction_type": "debit"},
    {"date": "2024-01-23", "product": "Savings Account",  "revenue":   9800.00, "customer_id": "C009", "region": "North", "transaction_type": "credit"},
    {"date": "2024-01-24", "product": "Personal Loan",    "revenue":  35000.00, "customer_id": "C010", "region": "South", "transaction_type": "credit"},
    {"date": "2024-01-25", "product": "Credit Card",       "revenue":   6200.00, "customer_id": "C011", "region": "East",  "transaction_type": "debit"},
    {"date": "2024-01-26", "product": "Home Loan",         "revenue":  95000.00, "customer_id": "C012", "region": "West",  "transaction_type": "credit"},
    {"date": "2024-01-27", "product": "Savings Account",  "revenue":  18500.00, "customer_id": "C013", "region": "North", "transaction_type": "credit"},
    {"date": "2024-01-28", "product": "Credit Card",       "revenue":   3100.50, "customer_id": "C014", "region": "South", "transaction_type": "debit"},
    {"date": "2024-01-29", "product": "Personal Loan",    "revenue":  42000.00, "customer_id": "C015", "region": "East",  "transaction_type": "credit"},
    {"date": "2024-01-30", "product": "Home Loan",         "revenue":  67500.00, "customer_id": "C016", "region": "West",  "transaction_type": "credit"},
    {"date": "2024-02-01", "product": "Savings Account",  "revenue":   7300.00, "customer_id": "C017", "region": "North", "transaction_type": "credit"},
    {"date": "2024-02-02", "product": "Credit Card",       "revenue":  15600.00, "customer_id": "C018", "region": "South", "transaction_type": "debit"},
    {"date": "2024-02-03", "product": "Personal Loan",    "revenue":  28000.00, "customer_id": "C019", "region": "East",  "transaction_type": "credit"},
    {"date": "2024-02-04", "product": "Home Loan",         "revenue": 110000.00, "customer_id": "C020", "region": "West",  "transaction_type": "credit"},
]


def main() -> None:
    try:
        from google.cloud import bigquery
    except ImportError:
        print("ERROR: google-cloud-bigquery not installed. Run: pip install google-cloud-bigquery")
        sys.exit(1)

    project  = settings.project_id
    dataset  = settings.dataset_id
    table_id = settings.table_id
    client   = bigquery.Client(project=project)

    print(f"Setting up BigQuery in project: {project}")

    # ── Dataset ───────────────────────────────────────────────────────────────
    dataset_ref = f"{project}.{dataset}"
    ds = bigquery.Dataset(dataset_ref)
    ds.location = "US"
    try:
        client.create_dataset(ds, exists_ok=True)
        print(f"✓ Dataset ready: {dataset_ref}")
    except Exception as exc:
        print(f"✗ Dataset error: {exc}")
        sys.exit(1)

    # ── Table ─────────────────────────────────────────────────────────────────
    table_ref = f"{dataset_ref}.{table_id}"
    schema = [
        bigquery.SchemaField("date",             "DATE"),
        bigquery.SchemaField("product",          "STRING"),
        bigquery.SchemaField("revenue",          "FLOAT64"),
        bigquery.SchemaField("customer_id",      "STRING"),
        bigquery.SchemaField("region",           "STRING"),
        bigquery.SchemaField("transaction_type", "STRING"),
    ]
    table = bigquery.Table(table_ref, schema=schema)
    try:
        client.create_table(table, exists_ok=True)
        print(f"✓ Table ready:   {table_ref}")
    except Exception as exc:
        print(f"✗ Table error: {exc}")
        sys.exit(1)

    # ── Insert rows ───────────────────────────────────────────────────────────
    errors = client.insert_rows_json(table_ref, SAMPLE_ROWS)
    if errors:
        print(f"✗ Row insert errors: {errors}")
        sys.exit(1)

    print(f"✓ Inserted {len(SAMPLE_ROWS)} sample rows")
    print(f"\nSetup complete!  Now run:\n  USE_MOCK_DATA=false python main.py --demo")


if __name__ == "__main__":
    main()
