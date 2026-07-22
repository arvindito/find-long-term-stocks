import yfinance as yf
import pandas as pd
from datetime import datetime

def extract_ticker_data(ticker_symbol: str) -> tuple[dict, list[dict]]:
    """
    Extracts metadata, historical financial statements (4-5 years),
    and forward analyst estimates for a single ticker via yfinance.
    
    Returns:
        overview_data (dict): Single record for company_overview table.
        financial_records (list[dict]): Multi-year rows for financial_records table.
    """
    try:
        yt = yf.Ticker(ticker_symbol)
        info = yt.info
        
        # Guard clause: Ensure yfinance actually returned valid data for this ticker
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not current_price:
            return None, []
            
        # 1. Company Overview Record
        overview_data = {
            'ticker': ticker_symbol,
            'company_name': info.get('longName') or info.get('shortName') or ticker_symbol,
            'sector': info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'beta': info.get('beta'),
            'current_price': current_price,
            'is_active': 1,
            'last_scraped': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        financial_records = []
        
        # 2. Extract Historical Statements (Income Statement & Balance Sheet)
        inc_stmt = yt.financials  # Yearly income statement (Columns = Dates)
        bal_sheet = yt.balance_sheet  # Yearly balance sheet
        
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
                
                # Balance Sheet items
                tot_assets = bal_sheet.loc['Total Assets', date_col] if isinstance(bal_sheet, pd.DataFrame) and 'Total Assets' in bal_sheet.index else None
                tot_liab = bal_sheet.loc['Total Liabilities Net Minority Interest', date_col] if isinstance(bal_sheet, pd.DataFrame) and 'Total Liabilities Net Minority Interest' in bal_sheet.index else None
                curr_assets = bal_sheet.loc['Current Assets', date_col] if isinstance(bal_sheet, pd.DataFrame) and 'Current Assets' in bal_sheet.index else None
                curr_liab = bal_sheet.loc['Current Liabilities', date_col] if isinstance(bal_sheet, pd.DataFrame) and 'Current Liabilities' in bal_sheet.index else None
                
                # Derived Math
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
                
        # 3. Extract Forward Projections (1 to 2 Years)
        try:
            earnings_est = yt.earnings_estimate
            revenue_est = yt.revenue_estimate
            
            if isinstance(earnings_est, pd.DataFrame) and not earnings_est.empty:
                for idx, row in earnings_est.iterrows():
                    # idx values in yfinance earnings_estimate: '0y' (Current Year), '+1y' (Next Year)
                    if idx in ['0y', '+1y']:
                        proj_year = datetime.now().year if idx == '0y' else datetime.now().year + 1
                        proj_eps = row.get('avg')
                        
                        proj_rev = None
                        if isinstance(revenue_est, pd.DataFrame) and idx in revenue_est.index:
                            proj_rev = revenue_est.loc[idx, 'avg']
                            
                        proj_pe = (current_price / float(proj_eps)) if (proj_eps and float(proj_eps) > 0) else None
                        
                        financial_records.append({
                            'ticker': ticker_symbol,
                            'year': proj_year,
                            'period_type': 'Projected',
                            'revenue': float(proj_rev) if pd.notnull(proj_rev) else None,
                            'net_income': None,
                            'net_income_margin': None,
                            'eps_diluted': float(proj_eps) if pd.notnull(proj_eps) else None,
                            'shares_outstanding': None,
                            'total_assets': None,
                            'total_liabilities': None,
                            'current_assets': None,
                            'current_liabilities': None,
                            'pe_ratio': proj_pe
                        })
        except Exception:
            pass  # Some smaller stocks do not have analyst projection tables
            
        return overview_data, financial_records

    except Exception as e:
        print(f"Error extracting data for {ticker_symbol}: {e}")
        return None, []

if __name__ == "__main__":
    # Test extraction on Apple (AAPL)
    test_ticker = "AAPL"
    print(f"Testing extraction for {test_ticker}...")
    overview, records = extract_ticker_data(test_ticker)
    
    if overview:
        print("\n--- Overview Record ---")
        print(overview)
        print(f"\n--- Financial Records ({len(records)} years total) ---")
        for r in records:
            print(f"Year: {r['year']} ({r['period_type']}) | Rev: {r['revenue']} | EPS: {r['eps_diluted']} | P/E: {r['pe_ratio']}")
