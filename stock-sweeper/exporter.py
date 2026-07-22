import os
import sqlite3
import subprocess
import pandas as pd
from datetime import datetime
from config import DB_NAME
from screener import run_screener

EXPORT_DIR = "exports"

def export_full_historical_shortlist(max_history_years: int = 10):
    """
    1. Runs screener to get shortlisted tickers.
    2. Queries financial records (capped at max_history_years of historical data).
    3. Merges overview metrics with yearly financials.
    4. Formats numbers so every cell contains a single raw float/int.
    5. Exports to CSV and opens in Numbers.app.
    """
    print("Running SQL Screener...")
    shortlist_df = run_screener()
    
    if shortlist_df.empty:
        print("No stocks passed screening criteria. Skipping export.")
        return

    filtered_tickers = shortlist_df['ticker'].tolist()
    placeholders = ",".join(["?"] * len(filtered_tickers))
    
    current_year = datetime.now().year
    min_historical_year = current_year - max_history_years

    conn = sqlite3.connect(DB_NAME)
    
    # Query up to 10 historical years + all projected years
    query = f"""
    SELECT 
        o.ticker AS Ticker,
        o.company_name AS "Company Name",
        o.sector AS Sector,
        o.industry AS Industry,
        f.year AS Year,
        f.period_type AS "Period Type",
        o.market_cap / 1e9 AS "Market Cap ($B)",
        o.current_price AS "Current Price ($)",
        o.forward_pe AS "Summary Forward P/E",
        o.earnings_growth * 100 AS "Quarterly EPS Growth (%)",
        o.revenue_growth * 100 AS "Quarterly Rev Growth (%)",
        o.operating_margins * 100 AS "Operating Margin (%)",
        o.current_ratio AS "Current Ratio",
        o.debt_to_equity AS "Debt to Equity",
        o.beta AS Beta,
        f.revenue / 1e6 AS "Annual Revenue ($M)",
        f.net_income / 1e6 AS "Annual Net Income ($M)",
        f.net_income_margin * 100 AS "Annual Net Margin (%)",
        f.eps_diluted AS "Diluted EPS ($)",
        f.shares_outstanding / 1e6 AS "Shares Outstanding (M)",
        f.total_assets / 1e6 AS "Total Assets ($M)",
        f.total_liabilities / 1e6 AS "Total Liabilities ($M)",
        f.current_assets / 1e6 AS "Current Assets ($M)",
        f.current_liabilities / 1e6 AS "Current Liabilities ($M)",
        f.pe_ratio AS "Yearly P/E Ratio"
    FROM company_overview o
    JOIN financial_records f ON o.ticker = f.ticker
    WHERE o.ticker IN ({placeholders})
      AND (f.period_type = 'Projected' OR f.year >= ?)
    ORDER BY o.ticker ASC, f.year DESC, f.period_type ASC;
    """
    
    params = filtered_tickers + [min_historical_year]
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    # Clean numeric columns to 2 decimal places
    float_cols = df.select_dtypes(include=['float64', 'float32']).columns
    df[float_cols] = df[float_cols].round(2)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(EXPORT_DIR, f"screener_10yr_history_{timestamp}.csv")
    latest_filepath = os.path.join(EXPORT_DIR, "screener_10yr_history_latest.csv")

    df.to_csv(filepath, index=False)
    df.to_csv(latest_filepath, index=False)
    
    print(f"\nSuccessfully exported shortlist dataset ({len(df)} total rows) to:")
    print(f"  └─ {filepath}")
    print(f"  └─ {latest_filepath}")

    try:
        subprocess.run(["open", "-a", "Numbers", latest_filepath])
        print("\nOpening 10-year report in Numbers.app...")
    except Exception as e:
        print(f"Note: Could not auto-open Numbers.app ({e})")

if __name__ == "__main__":
    export_full_historical_shortlist(max_history_years=10)
