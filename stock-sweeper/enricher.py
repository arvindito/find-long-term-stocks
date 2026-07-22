import sqlite3
import time
import argparse
import pandas as pd
from datetime import datetime
from config import DB_NAME
from screener import run_screener
from edgar import set_identity, Company

# SEC EDGAR User-Agent header (Required by SEC)
set_identity("Arvind Advani arvind.advani@gmail.com")

def has_sufficient_sec_data(conn, ticker: str, min_year: int) -> bool:
    """Checks if SQLite already holds multi-year SEC historical data for this ticker."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM financial_records 
        WHERE ticker = ? AND period_type = 'Historical' AND year >= ?
    """, (ticker, min_year))
    count = cursor.fetchone()[0]
    # If we already have 5+ historical years cached, consider it up-to-date
    return count >= 5

def enrich_shortlist_history(max_years: int = 10, force_refresh: bool = False):
    """
    Fetches up to 10 years of audited SEC financial statements for shortlisted stocks.
    Skips tickers that already have SEC historical data unless force_refresh=True.
    """
    print("Running SQL Screener to get shortlist...")
    shortlist_df = run_screener()
    
    if shortlist_df.empty:
        print("No stocks passed screening criteria. Skipping SEC enrichment.")
        return

    tickers = shortlist_df['ticker'].tolist()
    current_year = datetime.now().year
    min_year = current_year - max_years

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print(f"\nEvaluating SEC data for {len(tickers)} shortlisted stocks (Force Refresh: {force_refresh})...")
    
    for ticker in tickers:
        # Check cache unless force_refresh is True
        if not force_refresh and has_sufficient_sec_data(conn, ticker, min_year):
            print(f" ⚡ Skipping {ticker}: SEC historical records already cached in database.")
            continue

        print(f" -> Fetching SEC EDGAR filings for {ticker}...")
        try:
            company = Company(ticker)
            
            # 1. Try 10-K (Domestic US Companies)
            filings = company.get_filings(form="10-K")
            form_type = "10-K"
            
            # 2. Fallback to 20-F (Foreign Private Issuers like ABBNY)
            if not filings:
                filings = company.get_filings(form="20-F")
                form_type = "20-F"

            if not filings:
                print(f"    No 10-K or 20-F filings found for {ticker}.")
                time.sleep(1)
                continue

            records_to_upsert = []
            
            for filing in filings[:max_years + 2]:
                try:
                    obj = filing.obj()
                    if obj is None or not hasattr(obj, 'financials'):
                        continue
                    
                    fin = obj.financials
                    if fin is None:
                        continue

                    fy = None
                    if hasattr(obj, 'period_of_report') and obj.period_of_report:
                        fy = pd.to_datetime(obj.period_of_report).year
                    elif hasattr(filing, 'filing_date'):
                        fy = pd.to_datetime(filing.filing_date).year

                    if not fy or fy < min_year or fy >= current_year:
                        continue

                    def extract_metric(getter_func):
                        try:
                            val = getter_func()
                            return float(val) if val is not None and pd.notnull(val) else None
                        except Exception:
                            return None

                    rev = extract_metric(fin.get_revenue) if hasattr(fin, 'get_revenue') else None
                    net_inc = extract_metric(fin.get_net_income) if hasattr(fin, 'get_net_income') else None
                    eps = extract_metric(fin.get_eps) if hasattr(fin, 'get_eps') else None
                    shares = extract_metric(fin.get_shares_outstanding) if hasattr(fin, 'get_shares_outstanding') else None

                    net_margin = (net_inc / rev) if (net_inc and rev and rev != 0) else None

                    records_to_upsert.append((
                        ticker, int(fy), 'Historical',
                        rev, net_inc, net_margin, eps, shares,
                        None, None, None, None, None
                    ))

                except Exception:
                    continue

            if records_to_upsert:
                cursor.executemany("""
                INSERT INTO financial_records 
                (ticker, year, period_type, revenue, net_income, net_income_margin, eps_diluted, shares_outstanding, total_assets, total_liabilities, current_assets, current_liabilities, pe_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, year, period_type) DO UPDATE SET
                    revenue = COALESCE(excluded.revenue, revenue),
                    net_income = COALESCE(excluded.net_income, net_income),
                    net_income_margin = COALESCE(excluded.net_income_margin, net_income_margin),
                    eps_diluted = COALESCE(excluded.eps_diluted, eps_diluted),
                    shares_outstanding = COALESCE(excluded.shares_outstanding, shares_outstanding);
                """, records_to_upsert)
                conn.commit()
                print(f"    Successfully updated {len(records_to_upsert)} annual records ({form_type}) for {ticker}.")
            else:
                print(f"    No processable records found for {ticker}.")

        except Exception as e:
            print(f"    Could not fetch SEC EDGAR data for {ticker}: {e}")

        time.sleep(1)

    conn.close()
    print("\nSEC EDGAR historical enrichment complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEC EDGAR Financial Enricher")
    parser.add_argument("--force", action="store_true", help="Force re-downloading SEC filings even if cached.")
    args = parser.parse_args()

    enrich_shortlist_history(max_years=10, force_refresh=args.force)
