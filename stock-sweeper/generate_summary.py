import os
from datetime import datetime
import pandas as pd

from config import EXPORT_DIR, TIMELINE_CSV, FUNDAMENTAL_LEADERBOARD_CSV
from utils import classify_market_cap_tier, open_file

LEGACY_INPUT_CSV = os.path.join(EXPORT_DIR, "15y_export.csv")
FALLBACK_INPUT_CSV = os.path.join(EXPORT_DIR, "screener_shortlist_complete.csv")


def _extract_hist_price_for_year(hist_df: pd.DataFrame, target_year: int):
    yr_rows = hist_df[hist_df["Year"] == target_year]
    if yr_rows.empty:
        return None
    valid_p = pd.to_numeric(yr_rows["Price ($)"], errors="coerce").dropna()
    return round(float(valid_p.iloc[0]), 2) if not valid_p.empty else None


def generate_leaderboard():
    if os.path.exists(TIMELINE_CSV):
        input_path = TIMELINE_CSV
    elif os.path.exists(LEGACY_INPUT_CSV):
        input_path = LEGACY_INPUT_CSV
    else:
        input_path = FALLBACK_INPUT_CSV

    if not os.path.exists(input_path):
        print(f"Error: Could not find base dataset at {TIMELINE_CSV}. Run exporter.py first.")
        return None

    df = pd.read_csv(input_path)
    if df.empty:
        print(f"Warning: {input_path} is empty.")
        return None

    current_year = datetime.now().year  # 2026
    year_3y = current_year + 3          # 2029
    year_5y = current_year + 5          # 2031

    summary_rows = []
    tickers = df["Ticker"].unique()

    for ticker in tickers:
        sub_df = df[df["Ticker"] == ticker].copy()

        first_row = sub_df.iloc[0]
        company_name = first_row["Company Name"]
        sector = first_row["Sector"]
        industry = first_row["Industry"]
        last_updated = first_row["Last Updated At"]

        # Historical rows for price checkpoints
        hist_df = sub_df[sub_df["Period Type"] == "Historical"].copy()
        hist_10y_6y = hist_df[(hist_df["Year"] >= current_year - 10) & (hist_df["Year"] <= current_year - 6)]
        valid_10y_6y_prices = pd.to_numeric(hist_10y_6y["Price ($)"], errors="coerce").dropna()

        hist_10y_6y_max = round(float(valid_10y_6y_prices.max()), 2) if not valid_10y_6y_prices.empty else None
        hist_10y_6y_min = round(float(valid_10y_6y_prices.min()), 2) if not valid_10y_6y_prices.empty else None

        price_5y_ago = _extract_hist_price_for_year(hist_df, current_year - 5)
        price_4y_ago = _extract_hist_price_for_year(hist_df, current_year - 4)
        price_3y_ago = _extract_hist_price_for_year(hist_df, current_year - 3)
        price_1y_ago = _extract_hist_price_for_year(hist_df, current_year - 1)

        # 1. Current Price, Market Cap & Ratios (Year 0 / 2026 Historical or Projected)
        row_curr = sub_df[(sub_df["Year"] == current_year) & (sub_df["Period Type"] == "Historical")]
        if row_curr.empty or row_curr["Price ($)"].dropna().empty:
            row_curr = sub_df[(sub_df["Year"] == current_year) & (sub_df["Period Type"] == "Projected")]
        if row_curr.empty or row_curr["Price ($)"].dropna().empty:
            hist_prices = sub_df[sub_df["Period Type"] == "Historical"]["Price ($)"].dropna()
            curr_price = float(hist_prices.iloc[0]) if not hist_prices.empty else None
        else:
            curr_price = float(row_curr["Price ($)"].dropna().iloc[0])

        market_cap_b = None
        if not row_curr.empty and "Market Cap ($B)" in row_curr.columns and not row_curr["Market Cap ($B)"].dropna().empty:
            market_cap_b = round(float(row_curr["Market Cap ($B)"].dropna().iloc[0]), 2)
        elif "Market Cap ($B)" in sub_df.columns and not sub_df["Market Cap ($B)"].dropna().empty:
            market_cap_b = round(float(sub_df["Market Cap ($B)"].dropna().iloc[0]), 2)

        market_cap_tier = classify_market_cap_tier(market_cap_b * 1e9 if market_cap_b is not None else None)

        share_dilution_cagr = None
        if "3Y Share Dilution CAGR (%)" in sub_df.columns and not sub_df["3Y Share Dilution CAGR (%)"].dropna().empty:
            share_dilution_cagr = round(float(sub_df["3Y Share Dilution CAGR (%)"].dropna().iloc[0]), 2)

        beta_val = float(sub_df["Beta"].dropna().iloc[0]) if not sub_df["Beta"].dropna().empty else None

        # Financial Health Ratios (Most recent available non-null values)
        curr_ratio_val = float(sub_df["Current Ratio"].dropna().iloc[0]) if not sub_df["Current Ratio"].dropna().empty else None
        solvency_col = (
            "Solvency Ratio (Assets/Liabilities)"
            if "Solvency Ratio (Assets/Liabilities)" in sub_df.columns
            else "Total Assets / Total Liabilities"
        )
        assets_to_liab_val = (
            float(sub_df[solvency_col].dropna().iloc[0])
            if (solvency_col in sub_df.columns and not sub_df[solvency_col].dropna().empty)
            else None
        )

        # 2. 3Y Target Price (2029)
        row_3y = sub_df[(sub_df["Year"] == year_3y) & (sub_df["Period Type"] == "Projected")]
        price_3y = float(row_3y["Price ($)"].dropna().iloc[0]) if (not row_3y.empty and not row_3y["Price ($)"].dropna().empty) else None

        # 3. 5Y Target Price (2031)
        row_5y = sub_df[(sub_df["Year"] == year_5y) & (sub_df["Period Type"] == "Projected")]
        price_5y = float(row_5y["Price ($)"].dropna().iloc[0]) if (not row_5y.empty and not row_5y["Price ($)"].dropna().empty) else None

        # Model Valuation Inputs
        target_pe = (
            float(row_5y["Target P/E Multiple"].dropna().iloc[0])
            if (not row_5y.empty and not row_5y["Target P/E Multiple"].dropna().empty)
            else None
        )
        blended_growth_5y = (
            float(row_5y["Blended Growth (%)"].dropna().iloc[0])
            if (not row_5y.empty and not row_5y["Blended Growth (%)"].dropna().empty)
            else None
        )

        # Profit & CAGR Calculations
        return_3y = None
        profit_5y = None
        cagr_5y = None

        if curr_price and curr_price > 0:
            if price_3y and price_3y > 0:
                return_3y = round(((price_3y - curr_price) / curr_price) * 100.0, 2)
            if price_5y and price_5y > 0:
                profit_5y = round(((price_5y - curr_price) / curr_price) * 100.0, 2)
                cagr_5y = round((((price_5y / curr_price) ** (1.0 / 5.0)) - 1.0) * 100.0, 2)

        summary_rows.append({
            "Ticker": ticker,
            "Company Name": company_name,
            "Sector": sector,
            "Industry": industry,
            "Market Cap ($B)": market_cap_b,
            "Market Cap Tier": market_cap_tier,
            "Last Updated At": last_updated,
            "10Y-6Y Historical Max Price ($)": hist_10y_6y_max,
            "10Y-6Y Historical Min Price ($)": hist_10y_6y_min,
            "5Y Ago Price ($)": price_5y_ago,
            "4Y Ago Price ($)": price_4y_ago,
            "3Y Ago Price ($)": price_3y_ago,
            "1Y Ago Price ($)": price_1y_ago,
            "Current Price ($)": curr_price,
            "3Y Target Price ($)": price_3y,
            "5Y Target Price ($)": price_5y,
            "3Y Projected Return (%)": return_3y,
            "5Y Projected Total Return (%)": profit_5y,
            "5Y Projected CAGR (%)": cagr_5y,
            "3Y Share Dilution CAGR (%)": share_dilution_cagr,
            "Beta": beta_val,
            "Current Ratio": curr_ratio_val,
            "Solvency Ratio (Assets/Liabilities)": assets_to_liab_val,
            "Terminal Target P/E Multiple": target_pe,
            "5Y Blended Growth Rate (%)": blended_growth_5y,
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.sort_values(by="5Y Projected Total Return (%)", ascending=False, inplace=True)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    summary_df.to_csv(FUNDAMENTAL_LEADERBOARD_CSV, index=False)

    print(f"\nSuccessfully generated Fundamental Screener Leaderboard ({len(summary_df)} companies) at:")
    print(f"  └─ {FUNDAMENTAL_LEADERBOARD_CSV}\n")
    print(
        summary_df[
            [
                "Ticker",
                "Company Name",
                "Market Cap Tier",
                "Current Price ($)",
                "5Y Target Price ($)",
                "5Y Projected Total Return (%)",
                "5Y Projected CAGR (%)",
                "3Y Share Dilution CAGR (%)",
                "Solvency Ratio (Assets/Liabilities)",
            ]
        ].to_string(index=False)
    )

    open_file(FUNDAMENTAL_LEADERBOARD_CSV)
    return summary_df


if __name__ == "__main__":
    generate_leaderboard()
