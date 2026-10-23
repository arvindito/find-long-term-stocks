import pandas as pd
from config import DB_NAME
from database import get_db_connection
from utils import classify_market_cap_tier


def run_screener(
    min_market_cap: float = 500_000_000,
    min_current_ratio: float = 0.5,
    max_debt_to_equity: float = 2.0,
    min_beta: float = 0.7,
    min_operating_margin: float = 0.10,
    min_earnings_growth: float = 0.05,
    min_revenue_growth: float = 0.05,
    min_forward_pe: float = 5.0,
    min_roic: float = 0.10,
) -> pd.DataFrame:
    """
    Applies fundamental quality filters including Free Cash Flow and ROIC hurdles
    across all active companies >= $500M (Small-Cap, Mid-Cap, Large-Cap, and Mega-Cap).
    """
    conn = get_db_connection(DB_NAME)

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
        beta,
        free_cash_flow,
        roic
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
      AND free_cash_flow > 0
      AND roic >= ?
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
            min_forward_pe,
            min_roic,
        ),
    )
    conn.close()

    if not df.empty:
        df["market_cap_tier"] = df["market_cap"].apply(classify_market_cap_tier)

    print(f"Screener complete: Found {len(df)} matching stocks.")
    return df


if __name__ == "__main__":
    shortlist = run_screener()
    if not shortlist.empty:
        print("\n--- Shortlisted Candidates ---")
        print(
            shortlist[
                ["ticker", "company_name", "market_cap_tier", "current_price", "forward_pe", "operating_margins", "roic"]
            ].to_string(index=False)
        )
