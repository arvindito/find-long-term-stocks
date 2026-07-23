import os
import sqlite3
import subprocess
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from config import DB_NAME
from screener import run_screener
from enricher import fetch_finviz_eps_next_5y

EXPORT_DIR = "exports"

def calculate_trend_weighted_metric(values, years, current_year, alpha=0.20, winsor_pct=0.10):
    """
    Steps 1-4: Recency Weighting + Winsorization + Weighted Trend Slope (No StDev Clamping).
    """
    clean_data = [(v, y) for v, y in zip(values, years) if pd.notnull(v) and not np.isnan(v) and v > 0]
    if not clean_data:
        return None
    
    vals = np.array([d[0] for d in clean_data])
    yrs = np.array([d[1] for d in clean_data])
    
    if len(vals) == 1:
        return round(float(vals[0]), 4)

    # 1. Assign Exponential Recency Weights (2027 gets k=0)
    max_yr = current_year + 1  # 2027
    years_back = max_yr - yrs
    weights = (1.0 - alpha) ** years_back
    weights /= np.sum(weights)

    # 2. Winsorize extreme values (Step 2)
    lower_q = np.percentile(vals, winsor_pct * 100)
    upper_q = np.percentile(vals, (1.0 - winsor_pct) * 100)
    winsorized_vals = np.clip(vals, lower_q, upper_q)

    # 3. Recency Weighted Mean (Step 3)
    weighted_mean = np.sum(weights * winsorized_vals)

    # 4. Weighted Linear Regression Slope (Step 4)
    if len(vals) > 1:
        x_mean = np.sum(weights * yrs)
        cov = np.sum(weights * (yrs - x_mean) * (winsorized_vals - weighted_mean))
        var_x = np.sum(weights * ((yrs - x_mean) ** 2))
        slope = (cov / var_x) if var_x != 0 else 0.0
    else:
        slope = 0.0

    # Project trend metric starting from 2027 baseline with dampened slope
    target_metric = weighted_mean + (slope * 0.5)
    
    # Floor protection to prevent negative/zero multiples or margins
    target_metric = max(target_metric, lower_q * 0.8)
    return round(float(target_metric), 4)

def calculate_robust_metric_unweighted(series, winsor_pct=0.10, num_stdev=1.0):
    """
    Fancy Averaging (Median -> Winsorize -> Clip within 1-StDev Band) for Method Growth Convergences.
    """
    clean = pd.Series([x for x in series if pd.notnull(x) and not np.isnan(x)])
    if clean.empty:
        return None
    
    if len(clean) == 1:
        return round(float(clean.iloc[0]), 4)

    lower_q = clean.quantile(winsor_pct)
    upper_q = clean.quantile(1.0 - winsor_pct)
    winsorized = clean.clip(lower=lower_q, upper=upper_q)
    
    median_val = winsorized.median()
    std_val = winsorized.std(ddof=0) if len(winsorized) > 1 else 0.0
    
    lower_band = median_val - (num_stdev * std_val)
    upper_band = median_val + (num_stdev * std_val)
    
    final_val = float(np.clip(median_val, lower_band, upper_band))
    return round(final_val, 4)

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
    finviz_growth_cache = {}
    yahoo_lt_growth_cache = {}

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
            info = {}
            try:
                info = yt.info or {}
            except Exception:
                pass

            target_price_cache[t] = info.get('targetMeanPrice')
            finviz_growth_cache[t] = fetch_finviz_eps_next_5y(t)
            yahoo_lt_growth_cache[t] = info.get('longTermPotentialGrowth') or (float(info.get('earningsGrowth')) if info.get('earningsGrowth') else None)

            rev_est = None
            eps_est = None
            try:
                rev_est = yt.revenue_estimate
            except Exception:
                pass

            try:
                eps_est = yt.earnings_estimate
            except Exception:
                pass
            
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
        o.forward_pe AS overview_forward_pe,
        
        CASE 
            WHEN f.period_type = 'Projected' AND f.eps_diluted > 0 THEN ROUND(o.current_price / f.eps_diluted, 2)
            ELSE NULL 
        END AS "Forward P/E",
        
        CASE 
            WHEN f.total_liabilities > 0 THEN ROUND(CAST(f.total_assets AS FLOAT) / f.total_liabilities, 2)
            ELSE NULL 
        END AS "Total Assets / Total Liabilities",

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

    expanded_rows = []
    
    for ticker in filtered_tickers:
        sub_df = df[df['Ticker'] == ticker].copy()
        
        row_2027 = sub_df[(sub_df['Year'] == current_year + 1) & (sub_df['Period Type'] == 'Projected')]
        hist_rows = sub_df[sub_df['Period Type'] == 'Historical']
        
        # Build timeline including historical + 2026/2027 consensus rows
        all_net_margins = []
        all_pe_ratios = []
        all_years = []

        for _, r in sub_df.iterrows():
            y = r['Year']
            p_m = r['Net Profit Margin (%)']
            p_pe = r['P/E Ratio'] if r['P/E Ratio'] and r['P/E Ratio'] > 0 else (r['Forward P/E'] if r['Forward P/E'] else None)
            
            if p_m is not None and pd.notnull(p_m):
                all_net_margins.append(p_m / 100.0)
            else:
                all_net_margins.append(None)
                
            all_pe_ratios.append(p_pe)
            all_years.append(y)

        # Steps 1-4 Trend-Weighted Metrics
        robust_net_margin = calculate_trend_weighted_metric(all_net_margins, all_years, current_year, alpha=0.20, winsor_pct=0.10) or 0.15
        
        fwd_pe = sub_df['overview_forward_pe'].iloc[0] if not sub_df.empty and pd.notnull(sub_df['overview_forward_pe'].iloc[0]) else 18.0
        robust_pe = calculate_trend_weighted_metric(all_pe_ratios, all_years, current_year, alpha=0.20, winsor_pct=0.10) or round(fwd_pe, 2)

        eps_cagr = 0.08
        if len(hist_rows) >= 5:
            oldest_eps = hist_rows.iloc[-1]['Diluted EPS ($)']
            latest_eps = hist_rows.iloc[0]['Diluted EPS ($)']
            if oldest_eps and latest_eps and oldest_eps > 0 and latest_eps > 0:
                eps_cagr = (latest_eps / oldest_eps) ** (1 / 5) - 1

        base_eps = row_2027['Diluted EPS ($)'].values[0] if not row_2027.empty and pd.notnull(row_2027['Diluted EPS ($)'].values[0]) else 5.0
        base_rev = row_2027['Revenue ($M)'].values[0] if not row_2027.empty and pd.notnull(row_2027['Revenue ($M)'].values[0]) else 5000.0
        shares_m = sub_df['Shares Outstanding (M)'].iloc[0] if not sub_df.empty and pd.notnull(sub_df['Shares Outstanding (M)'].iloc[0]) else 290.0

        finviz_g = finviz_growth_cache.get(ticker) or eps_cagr
        yahoo_g = yahoo_lt_growth_cache.get(ticker) or eps_cagr

        # Pre-compute prices for 2027 through 2031
        prices_by_year = {}
        target_2027_price = target_price_cache.get(ticker) or round(base_eps * robust_pe, 2)

        for step, f_year in enumerate(range(current_year + 1, current_year + 6)): # 2027 to 2031
            k = step
            if f_year == current_year + 1:
                prices_by_year[f_year] = [target_2027_price, target_2027_price, target_2027_price, target_2027_price]
            else:
                proj_rev = round(base_rev * ((1 + eps_cagr) ** k), 2)
                eps_m1 = base_eps * ((1 + eps_cagr) ** k)
                p_m1 = eps_m1 * robust_pe
                
                net_inc_m2 = proj_rev * robust_net_margin
                eps_m2 = net_inc_m2 / shares_m if shares_m > 0 else 0
                p_m2 = eps_m2 * robust_pe
                
                eps_m3 = base_eps * ((1 + yahoo_g) ** k)
                p_m3 = eps_m3 * robust_pe
                
                eps_m4 = base_eps * ((1 + finviz_g) ** k)
                p_m4 = eps_m4 * robust_pe

                prices_by_year[f_year] = [p_m1, p_m2, p_m3, p_m4]

        blended_target_prices = {current_year + 1: target_2027_price}
        blended_growths = {current_year + 1: None}

        # Year +2 (2028): Fancy Averaging across 4 Method Prices
        p_2028_list = prices_by_year[current_year + 2]
        blended_target_prices[current_year + 2] = calculate_robust_metric_unweighted(p_2028_list, winsor_pct=0.10, num_stdev=1.0)
        blended_growths[current_year + 2] = None

        # Years +3 to +5 (2029 to 2031): Convergence using Fancy Averaged Growth %
        for f_year in range(current_year + 3, current_year + 6):
            prev_prices = prices_by_year[f_year - 1]
            curr_prices = prices_by_year[f_year]
            
            growths = []
            for p_prev, p_curr in zip(prev_prices, curr_prices):
                if p_prev and p_prev > 0:
                    g = (p_curr - p_prev) / p_prev
                    growths.append(g)

            fancy_growth = calculate_robust_metric_unweighted(growths, winsor_pct=0.10, num_stdev=1.0) or 0.08
            blended_growths[f_year] = round(fancy_growth * 100, 2)
            prev_blended_price = blended_target_prices[f_year - 1]
            blended_target_prices[f_year] = round(prev_blended_price * (1 + fancy_growth), 2)

        # Append existing historical/consensus rows
        for _, r in sub_df.iterrows():
            r_dict = r.to_dict()
            yr_r = r_dict['Year']
            p_type_r = r_dict['Period Type']

            if yr_r == current_year + 1 and p_type_r == 'Projected':
                r_dict['Target Price ($)'] = target_2027_price
                r_dict['Target P/E Multiple'] = round(robust_pe, 2)
            else:
                r_dict['Target Price ($)'] = None
                r_dict['Target P/E Multiple'] = None

            r_dict['Blended Growth (%)'] = None
            r_dict['Hist EPS CAGR (%)'] = None
            r_dict['M1: Projected EPS ($)'] = None
            r_dict['M1: Projected Price ($)'] = None
            r_dict['M2: Projected Revenue ($M)'] = None
            r_dict['Hist Net Margin (%)'] = None
            r_dict['M2: Projected Net Income ($M)'] = None
            r_dict['M2: Projected EPS ($)'] = None
            r_dict['M2: Projected Price ($)'] = None
            r_dict['Yahoo LT Growth Rate (%)'] = None
            r_dict['M3: Projected EPS ($)'] = None
            r_dict['M3: Projected Price ($)'] = None
            r_dict['Finviz EPS 5Y Rate (%)'] = None
            r_dict['M4: Projected EPS ($)'] = None
            r_dict['M4: Projected Price ($)'] = None

            expanded_rows.append(r_dict)

        # Append Forecast Rows (2028-2031)
        first_r = sub_df.iloc[0].to_dict()
        for step, f_year in enumerate(range(current_year + 2, current_year + 6), start=1):
            k = step
            proj_rev = round(base_rev * ((1 + eps_cagr) ** k), 2)

            eps_m1 = round(base_eps * ((1 + eps_cagr) ** k), 2)
            price_m1 = round(eps_m1 * robust_pe, 2)

            net_inc_m2 = round(proj_rev * robust_net_margin, 2)
            eps_m2 = round(net_inc_m2 / shares_m, 2) if shares_m > 0 else 0
            price_m2 = round(eps_m2 * robust_pe, 2)

            eps_m3 = round(base_eps * ((1 + yahoo_g) ** k), 2)
            price_m3 = round(eps_m3 * robust_pe, 2)

            eps_m4 = round(base_eps * ((1 + finviz_g) ** k), 2)
            price_m4 = round(eps_m4 * robust_pe, 2)

            f_row = {
                'Ticker': ticker,
                'Company Name': first_r['Company Name'],
                'Sector': first_r['Sector'],
                'Industry': first_r['Industry'],
                'Year': f_year,
                'Period Type': 'Projected',
                'Data Source Provider': 'Model_Forecast',
                'Last Updated At': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'overview_market_cap': None, 'overview_current_price': None, 'overview_beta': None, 'overview_forward_pe': None,
                'Forward P/E': None, 'Total Assets / Total Liabilities': None,
                'Current Ratio': None, 'Debt to Equity': None, 'P/E Ratio': None,
                'shares_outstanding': first_r.get('shares_outstanding'),
                'Revenue ($M)': None, 'Net Income ($M)': None, 'Net Profit Margin (%)': None,
                'Diluted EPS ($)': None, 'Shares Outstanding (M)': shares_m,
                'Total Assets ($M)': None, 'Total Liabilities ($M)': None,
                'Current Assets ($M)': None, 'Current Liabilities ($M)': None,
                
                'Target P/E Multiple': round(robust_pe, 2),
                'Blended Growth (%)': blended_growths.get(f_year),
                'Target Price ($)': blended_target_prices.get(f_year),
                
                'Hist EPS CAGR (%)': round(eps_cagr * 100, 2),
                'M1: Projected EPS ($)': eps_m1,
                'M1: Projected Price ($)': price_m1,
                
                'M2: Projected Revenue ($M)': proj_rev,
                'Hist Net Margin (%)': round(robust_net_margin * 100, 2),
                'M2: Projected Net Income ($M)': net_inc_m2,
                'M2: Projected EPS ($)': eps_m2,
                'M2: Projected Price ($)': price_m2,
                
                'Yahoo LT Growth Rate (%)': round(yahoo_g * 100, 2) if yahoo_g else None,
                'M3: Projected EPS ($)': eps_m3,
                'M3: Projected Price ($)': price_m3,
                
                'Finviz EPS 5Y Rate (%)': round(finviz_g * 100, 2) if finviz_g else None,
                'M4: Projected EPS ($)': eps_m4,
                'M4: Projected Price ($)': price_m4
            }
            expanded_rows.append(f_row)

    df_out = pd.DataFrame(expanded_rows)
    df_out.sort_values(by=['Ticker', 'Year', 'Period Type'], ascending=[True, False, False], inplace=True)

    prices = []
    market_caps = []
    eps_growths = []
    rev_growths = []
    betas = []

    for idx, row in df_out.iterrows():
        t = row['Ticker']
        yr = row['Year']
        p_type = row['Period Type']
        sh = row.get('shares_outstanding')

        if yr > current_year and p_type == 'Projected':
            tgt_p = row.get('Target Price ($)') or target_price_cache.get(t)
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

    fwd_pe_loc = df_out.columns.get_loc('Forward P/E')
    df_out.insert(fwd_pe_loc, 'Consensus Revenue Growth (%)', rev_growths)
    df_out.insert(fwd_pe_loc, 'Consensus Earnings Growth (%)', eps_growths)
    df_out.insert(fwd_pe_loc, 'Beta', betas)
    df_out.insert(fwd_pe_loc, 'Market Cap ($B)', market_caps)
    df_out.insert(fwd_pe_loc, 'Price ($)', prices)

    df_out.drop(columns=['overview_market_cap', 'overview_current_price', 'overview_beta', 'overview_forward_pe', 'shares_outstanding'], inplace=True, errors='ignore')

    os.makedirs(EXPORT_DIR, exist_ok=True)
    latest_filepath = os.path.join(EXPORT_DIR, "screener_shortlist_complete.csv")

    df_out.to_csv(latest_filepath, index=False)
    
    print(f"\nSuccessfully exported dataset ({len(df_out)} rows, {len(df_out.columns)} columns) to:")
    print(f"  └─ {latest_filepath}")

    try:
        subprocess.run(["open", "-a", "Numbers", latest_filepath])
        print("\nOpening dataset in Numbers.app...")
    except Exception as e:
        print(f"Note: Could not auto-open Numbers.app ({e})")

if __name__ == "__main__":
    export_clean_dataset(max_history_years=10)

# Auto-trigger Summary Leaderboard generation
try:
    from generate_summary import generate_leaderboard
    generate_leaderboard()
except Exception as e:
    print(f"Note: Could not auto-run summary leaderboard ({e})")
