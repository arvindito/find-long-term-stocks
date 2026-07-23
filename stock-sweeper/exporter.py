import os
import sqlite3
import subprocess
import pandas as pd
import yfinance as yf
from datetime import datetime
from config import DB_NAME
from screener import run_screener

EXPORT_DIR = "exports"

def export_clean_dataset(max_history_years: int = 10):
    print("Running SQL Screener...")
    shortlist_df = run_screener()
    
    if shortlist_df.empty:
        print("No stocks passed screening. Skipping export.")
        return

    filtered_tickers = shortlist_df['ticker'].tolist()
    placeholders = ",".join(["?"] * len(filtered_tickers))
    
    current_year = datetime.now().year
    min_historical_year = current_year - max_history_years

    conn = sqlite3.connect(DB_NAME)
    
    price_cache = {}
    growth_cache = {}
    target_price_cache = {}

    for t in filtered_tickers:
        try:
            data = yf.download(t, start=f"{min_historical_year}-01-01", end=f"{current_year}-01-15", progress=False)
            if not data.empty:
                close_data = data['Close'][t] if isinstance(data.columns, pd.MultiIndex) else data['Close']
                close_data = close_data.dropna()
                price_cache[t] = {}
                for yr in range(min_historical_year, current_year):
                    yr_data = close_data[close_data.index.year == yr]
                    if not yr_data.empty:
                        price_cache[t][yr] = float(yr_data.iloc[-1])

            yt = yf.Ticker(t)
            info = yt.info or {}
            target_price_cache[t] = info.get('targetMeanPrice')

            rev_est = yt.revenue_estimate
            eps_est = yt.earnings_estimate
            
            growth_cache[t] = {}
            if rev_est is not None and eps_est is not None:
                if '0y' in rev_est.index and '0y' in eps_est.index:
                    growth_cache[t][current_year] = {
                        'rev_growth': float(rev_est.loc['0y', 'growth']) if ('growth' in rev_est.columns and pd.notnull(rev_est.loc['0y', 'growth'])) else None,
                        'eps_growth': float(eps_est.loc['0y', 'growth']) if ('growth' in eps_est.columns and pd.notnull(eps_est.loc['0y', 'growth'])) else None
                    }
                if '+1y' in rev_est.index and '+1y' in eps_est.index:
                    growth_cache[t][current_year + 1] = {
                        'rev_growth': float(rev_est.loc['+1y', 'growth']) if ('growth' in rev_est.columns and pd.notnull(rev_est.loc['+1y', 'growth'])) else None,
                        'eps_growth': float(eps_est.loc['+1y', 'growth']) if ('growth' in eps_est.columns and pd.notnull(eps_est.loc['+1y', 'growth'])) else None
                    }
        except Exception:
            pass

    query = f"""
    SELECT 
        f.ticker AS Ticker,
        o.company_name AS "Company Name",
        o.sector AS Sector,
        o.industry AS Industry,
        f.year AS Year,
        f.period_type AS "Period Type",
        f.source_provider AS "Data Source Provider",
        f.updated_at AS "Last Updated At",
        
        o.market_cap AS overview_market_cap,
        o.current_price AS overview_current_price,
        o.beta AS overview_beta,
        
        CASE 
            WHEN f.period_type = 'Projected' AND f.eps_diluted > 0 THEN ROUND(o.current_price / f.eps_diluted, 2)
            ELSE NULL 
        END AS "Forward P/E",
        
        -- Custom Analysis Ratio: Total Assets / Total Liabilities
        CASE 
            WHEN f.total_liabilities > 0 THEN ROUND(CAST(f.total_assets AS FLOAT) / f.total_liabilities, 2)
            ELSE NULL 
        END AS "Total Assets / Total Liabilities",

        -- Liquidity & Solvency Ratios
        CASE 
            WHEN f.current_liabilities > 0 THEN ROUND(CAST(f.current_assets AS FLOAT) / f.current_liabilities, 2)
            WHEN f.period_type = 'Projected' THEN ROUND(o.current_ratio, 2)
            ELSE NULL 
        END AS "Current Ratio",
        
        CASE 
            WHEN (f.total_assets - f.total_liabilities) > 0 THEN ROUND(CAST(f.total_liabilities AS FLOAT) / (f.total_assets - f.total_liabilities), 2)
            WHEN f.period_type = 'Projected' THEN ROUND(o.debt_to_equity, 2)
            ELSE NULL 
        END AS "Debt to Equity",

        ROUND(f.pe_ratio, 2) AS "P/E Ratio",
        
        f.shares_outstanding,
        ROUND(f.revenue / 1e6, 2) AS "Revenue ($M)",
        ROUND(f.net_income / 1e6, 2) AS "Net Income ($M)",
        ROUND(f.net_income_margin * 100, 2) AS "Net Profit Margin (%)",
        ROUND(f.eps_diluted, 2) AS "Diluted EPS ($)",
        ROUND(f.shares_outstanding / 1e6, 2) AS "Shares Outstanding (M)",
        ROUND(f.total_assets / 1e6, 2) AS "Total Assets ($M)",
        ROUND(f.total_liabilities / 1e6, 2) AS "Total Liabilities ($M)",
        ROUND(f.current_assets / 1e6, 2) AS "Current Assets ($M)",
        ROUND(f.current_liabilities / 1e6, 2) AS "Current Liabilities ($M)"

    FROM financial_records f
    JOIN company_overview o ON f.ticker = o.ticker
    WHERE f.ticker IN ({placeholders})
      AND f.year >= ?
    ORDER BY f.ticker ASC, f.year DESC, f.period_type DESC;
    """
    
    params = filtered_tickers + [min_historical_year]
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    prices = []
    market_caps = []
    eps_growths = []
    rev_growths = []
    betas = []

    for idx, row in df.iterrows():
        t = row['Ticker']
        yr = row['Year']
        p_type = row['Period Type']
        sh = row['shares_outstanding']

        if yr > current_year and p_type == 'Projected':
            tgt_p = target_price_cache.get(t)
            if tgt_p and pd.notnull(tgt_p):
                prices.append(round(float(tgt_p), 2))
                if sh and sh > 0:
                    market_caps.append(round((float(tgt_p) * sh) / 1e9, 2))
                else:
                    market_caps.append(None)
            else:
                prices.append(None)
                market_caps.append(None)

            yr_growth = growth_cache.get(t, {}).get(yr, {})
            eg = yr_growth.get('eps_growth')
            rg = yr_growth.get('rev_growth')
            eps_growths.append(round(eg * 100, 2) if (eg is not None and pd.notnull(eg)) else None)
            rev_growths.append(round(rg * 100, 2) if (rg is not None and pd.notnull(rg)) else None)
            betas.append(round(row['overview_beta'], 2) if pd.notnull(row['overview_beta']) else None)

        elif yr == current_year and (p_type == 'Projected' or p_type == 'Historical'):
            curr_p = row['overview_current_price']
            prices.append(round(curr_p, 2) if pd.notnull(curr_p) else None)
            
            if curr_p and sh and sh > 0:
                market_caps.append(round((curr_p * sh) / 1e9, 2))
            else:
                market_caps.append(round(row['overview_market_cap'] / 1e9, 2) if pd.notnull(row['overview_market_cap']) else None)

            if p_type == 'Projected':
                yr_growth = growth_cache.get(t, {}).get(yr, {})
                eg = yr_growth.get('eps_growth')
                rg = yr_growth.get('rev_growth')
                eps_growths.append(round(eg * 100, 2) if (eg is not None and pd.notnull(eg)) else None)
                rev_growths.append(round(rg * 100, 2) if (rg is not None and pd.notnull(rg)) else None)
                betas.append(round(row['overview_beta'], 2) if pd.notnull(row['overview_beta']) else None)
            else:
                eps_growths.append(None)
                rev_growths.append(None)
                betas.append(None)

        else:
            hist_p = price_cache.get(t, {}).get(yr)
            if hist_p:
                prices.append(round(hist_p, 2))
                if sh and sh > 0:
                    market_caps.append(round((hist_p * sh) / 1e9, 2))
                else:
                    market_caps.append(None)
            else:
                prices.append(None)
                market_caps.append(None)

            eps_growths.append(None)
            rev_growths.append(None)
            betas.append(None)

    fwd_pe_loc = df.columns.get_loc('Forward P/E')
    df.insert(fwd_pe_loc, 'Consensus Revenue Growth (%)', rev_growths)
    df.insert(fwd_pe_loc, 'Consensus Earnings Growth (%)', eps_growths)
    df.insert(fwd_pe_loc, 'Beta', betas)
    df.insert(fwd_pe_loc, 'Market Cap ($B)', market_caps)
    df.insert(fwd_pe_loc, 'Price ($)', prices)

    df.drop(columns=['overview_market_cap', 'overview_current_price', 'overview_beta', 'shares_outstanding'], inplace=True, errors='ignore')

    os.makedirs(EXPORT_DIR, exist_ok=True)
    latest_filepath = os.path.join(EXPORT_DIR, "screener_shortlist_complete.csv")

    df.to_csv(latest_filepath, index=False)
    
    print(f"\nSuccessfully exported clean dataset ({len(df)} rows, {len(df.columns)} columns) to:")
    print(f"  └─ {latest_filepath}")

    try:
        subprocess.run(["open", "-a", "Numbers", latest_filepath])
        print("\nOpening dataset in Numbers.app...")
    except Exception as e:
        print(f"Note: Could not auto-open Numbers.app ({e})")

if __name__ == "__main__":
    export_clean_dataset(max_history_years=10)
