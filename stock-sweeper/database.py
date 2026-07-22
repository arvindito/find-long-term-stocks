import sqlite3
from config import DB_NAME

def init_db():
    """Initializes the SQLite database tables if they do not exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Company Metadata Table (with active status tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS company_overview (
        ticker TEXT PRIMARY KEY,
        company_name TEXT,
        sector TEXT,
        industry TEXT,
        beta REAL,
        current_price REAL,
        is_active INTEGER DEFAULT 1, -- 1 = Active trading, 0 = Delisted/Shutdown
        last_scraped TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Financial Metrics Table (Historical + Projected)
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
        PRIMARY KEY (ticker, year, period_type)
    )
    """)
    
    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' initialized successfully with active status tracking.")

if __name__ == "__main__":
    init_db()
