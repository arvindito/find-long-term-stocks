import sqlite3
from config import DB_NAME

def create_tables():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Company Overview Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS company_overview (
        ticker TEXT PRIMARY KEY,
        company_name TEXT,
        sector TEXT,
        industry TEXT,
        market_cap REAL,
        current_price REAL,
        forward_pe REAL,
        earnings_growth REAL,
        revenue_growth REAL,
        operating_margins REAL,
        current_ratio REAL,
        debt_to_equity REAL,
        beta REAL,
        source_provider TEXT DEFAULT 'YahooFinance',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Financial Records Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS financial_records (
        ticker TEXT,
        year INTEGER,
        period_type TEXT, -- 'Historical' or 'Projected'
        revenue REAL,
        net_income REAL,
        net_income_margin REAL,
        eps_diluted REAL,
        shares_outstanding REAL,
        total_assets REAL,
        total_liabilities REAL,
        current_assets REAL,
        current_liabilities REAL,
        pe_ratio REAL,
        source_provider TEXT DEFAULT 'YahooFinance',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (ticker, year, period_type)
    );
    """)

    conn.commit()
    conn.close()
    print("Database tables initialized successfully with source attribution and timestamps!")

if __name__ == "__main__":
    create_tables()
