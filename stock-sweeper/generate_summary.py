import os
import sqlite3
import subprocess
import pandas as pd
from datetime import datetime

EXPORT_DIR = "exports"
INPUT_CSV = os.path.join(EXPORT_DIR, "screener_shortlist_complete.csv")
OUTPUT_SUMMARY_CSV = os.path.join(EXPORT_DIR, "screener_summary_leaderboard.csv")

def generate_leaderboard():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Could not find base dataset at {INPUT_CSV}. Run exporter.py first.")
        return

    df = pd.read_csv(INPUT_CSV)
    
    current_year = datetime.now().year  # 2026
    year_3y = current_year + 3         # 2029
    year_5y = current_year + 5         # 2031

    summary_rows = []
    
    tickers = df['Ticker'].unique()

    for ticker in tickers:
        sub_df = df[df['Ticker'] == ticker].copy()
        
        first_row = sub_df.iloc[0]
        company_name = first_row['Company Name']
        sector = first_row['Sector']
        industry = first_row['Industry']
        last_updated = first_row['Last Updated At']

        # 1. Current Price & Ratios (Year 0 / 2026 Historical or Projected)
        row_curr = sub_df[(sub_df['Year'] == current_year) & (sub_df['Period Type'] == 'Historical')]
        if row_curr.empty:
            row_curr = sub_df[(sub_df['Year'] == current_year) & (sub_df['Period Type'] == 'Projected')]
        
        curr_price = row_curr['Price ($)'].values[0] if not row_curr.empty and pd.notnull(row_curr['Price ($)'].values[0]) else None
        beta_val = sub_df['Beta'].dropna().iloc[0] if not sub_df['Beta'].dropna().empty else None

        # Financial Health Ratios (Most recent available non-null values)
        curr_ratio_val = sub_df['Current Ratio'].dropna().iloc[0] if not sub_df['Current Ratio'].dropna().empty else None
        assets_to_liab_val = sub_df['Total Assets / Total Liabilities'].dropna().iloc[0] if not sub_df['Total Assets / Total Liabilities'].dropna().empty else None

        # 2. 3Y Target Price (2029)
        row_3y = sub_df[(sub_df['Year'] == year_3y) & (sub_df['Period Type'] == 'Projected')]
        price_3y = row_3y['Price ($)'].values[0] if not row_3y.empty and pd.notnull(row_3y['Price ($)'].values[0]) else None

        # 3. 5Y Target Price (2031)
        row_5y = sub_df[(sub_df['Year'] == year_5y) & (sub_df['Period Type'] == 'Projected')]
        price_5y = row_5y['Price ($)'].values[0] if not row_5y.empty and pd.notnull(row_5y['Price ($)'].values[0]) else None

        # Model Valuation Inputs
        target_pe = row_5y['Target P/E Multiple'].values[0] if not row_5y.empty and pd.notnull(row_5y['Target P/E Multiple'].values[0]) else None
        blended_growth_5y = row_5y['Blended Growth (%)'].values[0] if not row_5y.empty and pd.notnull(row_5y['Blended Growth (%)'].values[0]) else None

        # Profit & CAGR Calculations
        return_3y = None
        profit_5y = None
        cagr_5y = None

        if curr_price and curr_price > 0:
            if price_3y:
                return_3y = round(((price_3y - curr_price) / curr_price) * 100.0, 2)
            if price_5y:
                profit_5y = round(((price_5y - curr_price) / curr_price) * 100.0, 2)
                cagr_5y = round((((price_5y / curr_price) ** (1.0 / 5.0)) - 1.0) * 100.0, 2)

        summary_rows.append({
            'Ticker': ticker,
            'Company Name': company_name,
            'Sector': sector,
            'Industry': industry,
            'Last Updated At': last_updated,
            'Current Price ($)': curr_price,
            '3Y Price ($)': price_3y,
            '5Y Price ($)': price_5y,
            '3Y Return (%)': return_3y,
            '5Y Total Profit (%)': profit_5y,
            '5Y CAGR (%)': cagr_5y,
            'Beta': beta_val,
            'Current Ratio': curr_ratio_val,
            'Total Assets / Total Liabilities': assets_to_liab_val,
            'Model Target P/E': target_pe,
            '5Y Blended Growth (%)': blended_growth_5y
        })

    summary_df = pd.DataFrame(summary_rows)
    
    # Sort by 5Y Total Profit (%) descending
    summary_df.sort_values(by='5Y Total Profit (%)', ascending=False, inplace=True)

    summary_df.to_csv(OUTPUT_SUMMARY_CSV, index=False)
    
    print(f"\nSuccessfully generated Summary Leaderboard ({len(summary_df)} companies) at:")
    print(f"  └─ {OUTPUT_SUMMARY_CSV}\n")
    print(summary_df[['Ticker', 'Company Name', 'Current Price ($)', '5Y Price ($)', '5Y Total Profit (%)', 'Beta', 'Current Ratio', 'Total Assets / Total Liabilities']].to_string(index=False))

    try:
        subprocess.run(["open", "-a", "Numbers", OUTPUT_SUMMARY_CSV])
        print("\nOpening Summary Leaderboard in Numbers.app...")
    except Exception as e:
        print(f"Note: Could not auto-open Numbers.app ({e})")

if __name__ == "__main__":
    generate_leaderboard()
