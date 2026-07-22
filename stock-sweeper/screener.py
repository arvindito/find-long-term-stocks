import sqlite3
import pandas as pd
from config import DB_NAME

def run_screener(
    min_market_cap: float = 1_000_000_000,
    min_current_ratio: float = 0.5,
    max_debt_to_equity: float = 2.0,
    min_beta: float = 0.7,
    min_operating_margin: float = 0.10,
    min_earnings_growth: float = 0.05,
    min_revenue_growth: float = 0.05,
    min_forward_pe: float = 5.0
) -> pd.DataFrame:
    """
    Queries local SQLite database applying the core 8 quality & growth filters.
    """
    conn = sqlite3.connect(DB_NAME)
    
    query = """
    SELECT 
        ticker,
        company_name,
        sector,
        industry,
        market_cap,
        current_price,
        forward_pe,
        earnings_growth,
        revenue_growth,
        operating_margins,
        current_ratio,
        debt_to_equity,
        beta
    FROM company_overview
    WHERE is_active = 1
      AND market_cap >= ?
      AND current_ratio >= ?
      AND debt_to_equity <= ?
      AND beta >= ?
      AND operating_margins >= ?
      AND earnings_growth >= ?
      AND revenue_growth >= ?
      AND forward_pe >= ?
    ORDER BY forward_pe ASC;
    """
    
    df = pd.read_sql_query(
        query, 
        conn, 
        params=(
            min_market_cap,
            min_current_ratio,
            max_debt_to_equity,
            min_beta,
            min_operating_margin,
            min_earnings_growth,
            min_revenue_growth,
            min_forward_pe
        )
    )
    conn.close()
    
    print(f"Screener complete: Found {len(df)} matching stocks.")
    return df

if __name__ == "__main__":
    print("Running screener with customized parameters...")
    shortlist = run_screener()
    if not shortlist.empty:
        print("\n--- Shortlisted Candidates ---")
        print(shortlist.to_string(index=False))
    else:
        print("\nNo stocks matched all strict criteria in the current 30-ticker sample batch.")
        print("To see top candidates in our current sample, let's inspect the active non-SPAC companies:")
        
        conn = sqlite3.connect(DB_NAME)
        sample_df = pd.read_sql_query(
            "SELECT ticker, company_name, market_cap, forward_pe, operating_margins FROM company_overview WHERE is_active=1 LIMIT 10", 
            conn
        )
        conn.close()
        print(sample_df.to_string(index=False))
