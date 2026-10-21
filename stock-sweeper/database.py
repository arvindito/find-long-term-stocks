import argparse
import sqlite3
from config import DB_NAME


def init_db(reset: bool = False):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if reset:
        cursor.execute("DROP TABLE IF EXISTS company_overview;")
        cursor.execute("DROP TABLE IF EXISTS financial_records;")

    # Check if existing tables are missing newly required columns (FCF, ROIC, OCF, CapEx)
    cursor.execute("PRAGMA table_info(company_overview);")
    overview_cols = {row[1] for row in cursor.fetchall()}
    if overview_cols and ("free_cash_flow" not in overview_cols or "roic" not in overview_cols or "last_scraped" not in overview_cols):
        cursor.execute("DROP TABLE IF EXISTS company_overview;")

    cursor.execute("PRAGMA table_info(financial_records);")
    fin_cols = {row[1] for row in cursor.fetchall()}
    if fin_cols and ("free_cash_flow" not in fin_cols or "operating_cash_flow" not in fin_cols or "capital_expenditures" not in fin_cols):
        cursor.execute("DROP TABLE IF EXISTS financial_records;")

    # Company Overview Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS company_overview (
        ticker TEXT PRIMARY KEY,
        company_name TEXT,
        sector TEXT,
        industry TEXT,
        market_cap REAL,
        current_price REAL,
        beta REAL,
        current_ratio REAL,
        debt_to_equity REAL,
        operating_margins REAL,
        earnings_growth REAL,
        revenue_growth REAL,
        forward_pe REAL,
        free_cash_flow REAL,
        roic REAL,
        target_mean_price REAL,
        finviz_eps_5y REAL,
        yahoo_lt_growth REAL,
        last_enriched TIMESTAMP,
        is_active INTEGER DEFAULT 1,
        source_provider TEXT DEFAULT 'YahooFinance',
        last_scraped TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Non-destructive column migrations for company_overview
    cursor.execute("PRAGMA table_info(company_overview);")
    existing_overview_cols = {row[1] for row in cursor.fetchall()}
    for col_name, col_type in [
        ("target_mean_price", "REAL"),
        ("finviz_eps_5y", "REAL"),
        ("yahoo_lt_growth", "REAL"),
        ("last_enriched", "TIMESTAMP"),
    ]:
        if col_name not in existing_overview_cols:
            cursor.execute(f"ALTER TABLE company_overview ADD COLUMN {col_name} {col_type};")

    # Financial Records Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS financial_records (
        ticker TEXT,
        year INTEGER,
        period_type TEXT,
        revenue REAL,
        net_income REAL,
        net_income_margin REAL,
        eps_diluted REAL,
        shares_outstanding REAL,
        total_assets REAL,
        total_liabilities REAL,
        current_assets REAL,
        current_liabilities REAL,
        operating_cash_flow REAL,
        capital_expenditures REAL,
        free_cash_flow REAL,
        pe_ratio REAL,
        year_end_price REAL,
        consensus_eps_growth REAL,
        consensus_rev_growth REAL,
        source_provider TEXT DEFAULT 'YahooFinance',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (ticker, year, period_type)
    );
    """)

    # Non-destructive column migrations for financial_records
    cursor.execute("PRAGMA table_info(financial_records);")
    existing_fin_cols = {row[1] for row in cursor.fetchall()}
    for col_name, col_type in [
        ("year_end_price", "REAL"),
        ("consensus_eps_growth", "REAL"),
        ("consensus_rev_growth", "REAL"),
    ]:
        if col_name not in existing_fin_cols:
            cursor.execute(f"ALTER TABLE financial_records ADD COLUMN {col_name} {col_type};")

    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' initialized successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize or reset the SQLite database.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables.")
    args = parser.parse_args()
    init_db(reset=args.reset)
