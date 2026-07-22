import sqlite3
from config import DB_NAME

def init_db():
    """Initializes the SQLite database tables with our target screening parameters."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Company Overview Table (Stores direct summary metrics for screening)
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
        is_active INTEGER DEFAULT 1,
        last_scraped TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Financial Records Table (Stores multi-year statement data)
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
        pe_ratio REAL,
        PRIMARY KEY (ticker, year, period_type)
    )
    """)
    
    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' initialized with updated summary fields.")

if __name__ == "__main__":
    init_db()
