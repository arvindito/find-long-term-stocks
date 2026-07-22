import sqlite3
import time
import yfinance as yf
import pandas as pd
from datetime import datetime
from config import DB_NAME, BATCH_SIZE, BATCH_PAUSE_SECONDS
from sec_tickers import fetch_sec_tickers

def extract_ticker_data(ticker_symbol: str) -> tuple[dict, list[dict]]:
    """
    Extracts summary metrics, all available historical annual financials,
    and complete analyst estimates (0y and +1y) via yfinance.
    """
    try:
        yt = yf.Ticker(ticker_symbol)
        info = yt.info
        
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        market_cap = info.get('marketCap')
        
        # Require a valid price and market cap to process
        if not current_price or not market_cap:
            return None, []
            
        raw_dte = info.get('debtToEquity')
        dte_ratio = (float(raw_dte) / 100.0) if raw_dte is not None else None
            
        # 1. Company Overview Record
        overview_data = {
            'ticker': ticker_symbol,
            'company_name': info.get('longName') or info.get('shortName') or ticker_symbol,
            'sector': info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'market_cap': float(market_cap),
            'current_price': float(current_price),
            'beta': info.get('beta'),
            'current_ratio': info.get('currentRatio'),
            'debt_to_equity': dte_ratio,
            'operating_margins': info.get('operatingMargins'),
            'earnings_growth': info.get('earningsGrowth'),
            'revenue_growth': info.get('revenueGrowth'),
            'forward_pe': info.get('forwardPE'),
            'is_active': 1,
            'last_scraped': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        financial_records = []
        inc_stmt = yt.financials
        bal_sheet = yt.balance_sheet
        
        latest_shares_count = None
        
        # 2. Extract All Available Historical Years
        if isinstance(inc_stmt, pd.DataFrame) and not inc_stmt.empty:
            for date_col in inc_stmt.columns:
                try:
                    year = pd.to_datetime(date_col).year
                except Exception:
                    continue
                    
                rev = inc_stmt.loc['Total Revenue', date_col] if 'Total Revenue' in inc_stmt.index else None
                net_inc = inc_stmt.loc['Net Income', date_col] if 'Net Income' in inc_stmt.index else None
                eps = inc_stmt.loc['Diluted EPS', date_col] if 'Diluted EPS' in inc_stmt.index else None
                shares = inc_stmt.loc['Diluted Average Shares', date_col] if 'Diluted Average Shares' in inc_stmt.index else None
                
                if shares and pd.notnull(shares) and latest_shares_count is None:
                    latest_shares_count = float(shares)

                tot_assets = bal_sheet.loc['Total Assets', date_col] if isinstance(bal_sheet, pd.DataFrame) and 'Total Assets' in bal_sheet.index else None
                tot_liab = bal_sheet.loc['Total Liabilities Net Minority Interest', date_col] if isinstance(bal_sheet, pd.DataFrame) and 'Total Liabilities Net Minority Interest' in bal_sheet.index else None
                curr_assets = bal_sheet.loc['Current Assets', date_col] if isinstance(bal_sheet, pd.DataFrame) and 'Current Assets' in bal_sheet.index else None
                curr_liab = bal_sheet.loc['Current Liabilities', date_col] if isinstance(bal_sheet, pd.DataFrame) and 'Current Liabilities' in bal_sheet.index else None
                
                net_margin = (float(net_inc) / float(rev)) if (net_inc and rev and float(rev) != 0) else None
                pe = (current_price / float(eps)) if (eps and float(eps) > 0) else None
                
                financial_records.append({
                    'ticker': ticker_symbol,
                    'year': year,
                    'period_type': 'Historical',
                    'revenue': float(rev) if pd.notnull(rev) else None,
                    'net_income': float(net_inc) if pd.notnull(net_inc) else None,
                    'net_income_margin': net_margin,
                    'eps_diluted': float(eps) if pd.notnull(eps) else None,
                    'shares_outstanding': float(shares) if pd.notnull(shares) else None,
                    'total_assets': float(tot_assets) if pd.notnull(tot_assets) else None,
                    'total_liabilities': float(tot_liab) if pd.notnull(tot_liab) else None,
                    'current_assets': float(curr_assets) if pd.notnull(curr_assets) else None,
                    'current_liabilities': float(curr_liab) if pd.notnull(curr_liab) else None,
                    'pe_ratio': pe
                })
                
        # 3. Extract Projected Estimates (0y and +1y)
        try:
            earnings_est = yt.earnings_estimate
            revenue_est = yt.revenue_estimate
            
            if isinstance(earnings_est, pd.DataFrame) and not earnings_est.empty:
                for idx, row in earnings_est.iterrows():
                    if idx in ['0y', '+1y']:
                        proj_year = datetime.now().year if idx == '0y' else datetime.now().year + 1
                        proj_eps = float(row.get('avg')) if row.get('avg') is not None else None
                        
                        proj_rev = None
                        if isinstance(revenue_est, pd.DataFrame) and idx in revenue_est.index:
                            val = revenue_est.loc[idx, 'avg']
                            proj_rev = float(val) if pd.notnull(val) else None
                            
                        # Derive Projected Net Income & Net Margin
                        proj_net_inc = None
                        proj_net_margin = None
                        if proj_eps is not None and latest_shares_count:
                            proj_net_inc = proj_eps * latest_shares_count
                            if proj_rev and proj_rev != 0:
                                proj_net_margin = proj_net_inc / proj_rev

                        proj_pe = (current_price / proj_eps) if (proj_eps and proj_eps > 0) else None
                        
                        financial_records.append({
                            'ticker': ticker_symbol,
                            'year': proj_year,
                            'period_type': 'Projected',
                            'revenue': proj_rev,
                            'net_income': proj_net_inc,
                            'net_income_margin': proj_net_margin,
                            'eps_diluted': proj_eps,
                            'shares_outstanding': latest_shares_count,
                            'total_assets': None,
                            'total_liabilities': None,
                            'current_assets': None,
                            'current_liabilities': None,
                            'pe_ratio': proj_pe
                        })
        except Exception:
            pass
            
        return overview_data, financial_records

    except Exception as e:
        return None, []


def save_to_database(conn, overview_batch, financial_batch):
    """Saves batch records to SQLite."""
    cursor = conn.cursor()
    
    cursor.executemany("""
    INSERT OR REPLACE INTO company_overview 
    (ticker, company_name, sector, industry, market_cap, current_price, beta, 
     current_ratio, debt_to_equity, operating_margins, earnings_growth, 
     revenue_growth, forward_pe, is_active, last_scraped)
    VALUES (:ticker, :company_name, :sector, :industry, :market_cap, :current_price, :beta,
            :current_ratio, :debt_to_equity, :operating_margins, :earnings_growth,
            :revenue_growth, :forward_pe, :is_active, :last_scraped)
    """, overview_batch)
    
    cursor.executemany("""
    INSERT OR REPLACE INTO financial_records
    (ticker, year, period_type, revenue, net_income, net_income_margin, eps_diluted, 
     shares_outstanding, total_assets, total_liabilities, current_assets, current_liabilities, pe_ratio)
    VALUES (:ticker, :year, :period_type, :revenue, :net_income, :net_income_margin, :eps_diluted,
            :shares_outstanding, :total_assets, :total_liabilities, :current_assets, :current_liabilities, :pe_ratio)
    """, financial_batch)
    
    conn.commit()


def run_sweeper(limit: int = None):
    """Main market-wide rate-limited sweeper engine."""
    conn = sqlite3.connect(DB_NAME)
    
    sec_tickers = fetch_sec_tickers()
    if not sec_tickers:
        print("Aborting sweep: Could not fetch SEC tickers.")
        conn.close()
        return

    if limit:
        sec_tickers = sec_tickers[:limit]

    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor = conn.cursor()
    cursor.execute("SELECT ticker FROM company_overview WHERE DATE(last_scraped) = ?", (today_str,))
    scraped_today = {row[0] for row in cursor.fetchall()}
    
    pending_tickers = [t for t in sec_tickers if t not in scraped_today]
    print(f"Total Tickers: {len(sec_tickers)} | Scraped Today: {len(scraped_today)} | Pending: {len(pending_tickers)}")

    if not pending_tickers:
        print("Market data is up to date!")
        conn.close()
        return

    overview_batch = []
    financial_batch = []
    
    for i, ticker in enumerate(pending_tickers, 1):
        overview, records = extract_ticker_data(ticker)
        
        if overview:
            overview_batch.append(overview)
            financial_batch.extend(records)
            
        if len(overview_batch) >= BATCH_SIZE or i == len(pending_tickers):
            save_to_database(conn, overview_batch, financial_batch)
            print(f"[{i}/{len(pending_tickers)}] Saved batch of {len(overview_batch)} tickers to database.")
            overview_batch.clear()
            financial_batch.clear()
            time.sleep(BATCH_PAUSE_SECONDS)

    conn.close()
    print("Market sweep completed successfully.")

if __name__ == "__main__":
    # Remove limit argument to run across all SEC tickers
    run_sweeper()
