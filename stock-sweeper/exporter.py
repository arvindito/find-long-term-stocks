import os
import math
import sqlite3
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from config import DB_NAME
from screener import run_screener
from enricher import fetch_finviz_eps_next_5y
from utils import open_file

EXPORT_DIR = "exports"


def _is_valid_num(val) -> bool:
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
        f = float(val)
        return not (math.isnan(f) or math.isinf(f))
    except (ValueError, TypeError):
        return False


def _clean_num(val, default=None):
    return float(val) if _is_valid_num(val) else default


def calculate_trend_weighted_metric(values, years, current_year, alpha=0.20, winsor_pct=0.10):
    clean_data = [(float(v), int(y)) for v, y in zip(values, years) if _is_valid_num(v) and _is_valid_num(y) and float(v) > 0]
    if not clean_data:
        return None

    vals = np.array([d[0] for d in clean_data], dtype=float)
    yrs = np.array([d[1] for d in clean_data], dtype=float)

    if len(vals) == 1:
        return round(float(vals[0]), 4)

    max_yr = current_year + 1
    years_back = np.maximum(0.0, max_yr - yrs)
    weights = (1.0 - alpha) ** years_back
    w_sum = np.sum(weights)
    if w_sum <= 0:
        return round(float(np.median(vals)), 4)
    weights /= w_sum

    lower_q = np.percentile(vals, winsor_pct * 100)
    upper_q = np.percentile(vals, (1.0 - winsor_pct) * 100)
    winsorized_vals = np.clip(vals, lower_q, upper_q)

    weighted_mean = float(np.sum(weights * winsorized_vals))

    if len(vals) > 1:
        x_mean = float(np.sum(weights * yrs))
        cov = float(np.sum(weights * (yrs - x_mean) * (winsorized_vals - weighted_mean)))
        var_x = float(np.sum(weights * ((yrs - x_mean) ** 2)))
        slope = (cov / var_x) if var_x > 1e-9 else 0.0
    else:
        slope = 0.0

    target_metric = weighted_mean + (slope * 0.5)
    target_metric = max(target_metric, float(lower_q) * 0.8)
    if not _is_valid_num(target_metric) or target_metric <= 0:
        return round(float(np.median(vals)), 4)
    return round(float(target_metric), 4)


def calculate_robust_metric_unweighted(series, winsor_pct=0.10, num_stdev=1.0):
    clean = pd.Series([float(x) for x in series if _is_valid_num(x)], dtype=float)
    if clean.empty:
        return None

    if len(clean) == 1:
        return round(float(clean.iloc[0]), 4)

    lower_q = clean.quantile(winsor_pct)
    upper_q = clean.quantile(1.0 - winsor_pct)
    winsorized = clean.clip(lower=lower_q, upper=upper_q)

    median_val = float(winsorized.median())
    std_val = float(winsorized.std(ddof=0)) if len(winsorized) > 1 else 0.0

    lower_band = median_val - (num_stdev * std_val)
    upper_band = median_val + (num_stdev * std_val)

    final_val = float(np.clip(median_val, lower_band, upper_band))
    return round(final_val, 4) if _is_valid_num(final_val) else None


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
                        price_cache[t][yr] = _clean_num(yr_data.iloc[-1])

            yt = yf.Ticker(t)
            info = yt.info or {}
            target_price_cache[t] = _clean_num(info.get('targetMeanPrice'))
            finviz_growth_cache[t] = _clean_num(fetch_finviz_eps_next_5y(t))
            raw_y_lt = _clean_num(info.get('longTermPotentialGrowth'))
            if raw_y_lt is None:
                raw_y_lt = _clean_num(info.get('earningsGrowth'))
            yahoo_lt_growth_cache[t] = raw_y_lt

            rev_est = yt.revenue_estimate
            eps_est = yt.earnings_estimate

            growth_cache[t] = {}
            if isinstance(rev_est, pd.DataFrame) and isinstance(eps_est, pd.DataFrame):
                if '0y' in rev_est.index and '0y' in eps_est.index:
                    growth_cache[t][current_year] = {
                        'rev_growth': _clean_num(rev_est.loc['0y', 'growth']) if 'growth' in rev_est.columns else None,
                        'eps_growth': _clean_num(eps_est.loc['0y', 'growth']) if 'growth' in eps_est.columns else None,
                    }
                if '+1y' in rev_est.index and '+1y' in eps_est.index:
                    growth_cache[t][current_year + 1] = {
                        'rev_growth': _clean_num(rev_est.loc['+1y', 'growth']) if 'growth' in rev_est.columns else None,
                        'eps_growth': _clean_num(eps_est.loc['+1y', 'growth']) if 'growth' in eps_est.columns else None,
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

    expanded_rows = []

    for ticker in filtered_tickers:
        sub_df = df[df['Ticker'] == ticker].copy()
        if sub_df.empty:
            continue

        row_2027 = sub_df[(sub_df['Year'] == current_year + 1) & (sub_df['Period Type'] == 'Projected')]
        row_2026_proj = sub_df[(sub_df['Year'] == current_year) & (sub_df['Period Type'] == 'Projected')]
        hist_rows = sub_df[sub_df['Period Type'] == 'Historical'].sort_values(by='Year', ascending=True)

        all_net_margins = []
        all_pe_ratios = []
        hist_pe_ratios = []
        all_years = []

        for _, r in sub_df.iterrows():
            y = int(r['Year'])
            p_m = _clean_num(r['Net Profit Margin (%)'])
            r_pe = _clean_num(r['P/E Ratio'])
            r_fpe = _clean_num(r['Forward P/E'])
            p_pe = r_pe if (r_pe is not None and r_pe > 0) else (r_fpe if (r_fpe is not None and r_fpe > 0) else None)

            all_net_margins.append((p_m / 100.0) if (p_m is not None and p_m > 0) else None)
            all_pe_ratios.append(p_pe)
            if r['Period Type'] == 'Historical' and r_pe is not None and r_pe > 0:
                hist_pe_ratios.append(r_pe)
            all_years.append(y)

        robust_net_margin = calculate_trend_weighted_metric(all_net_margins, all_years, current_year, alpha=0.20, winsor_pct=0.10) or 0.15
        fwd_pe = _clean_num(sub_df['overview_forward_pe'].iloc[0], default=18.0)
        if fwd_pe <= 0:
            fwd_pe = 18.0
        robust_pe = calculate_trend_weighted_metric(all_pe_ratios, all_years, current_year, alpha=0.20, winsor_pct=0.10) or round(fwd_pe, 2)

        # OPTION A: Multiple Compression Target (Company Historical Median P/E)
        valid_hist_pes = hist_pe_ratios if hist_pe_ratios else [p for p in all_pe_ratios if _is_valid_num(p) and p > 0]
        terminal_pe_target = float(np.median(valid_hist_pes)) if valid_hist_pes else 15.0
        terminal_pe_target = max(10.0, min(terminal_pe_target, robust_pe))

        # Dynamic Historical EPS CAGR (Method 1)
        eps_cagr = 0.08
        valid_eps_hist = hist_rows[hist_rows['Diluted EPS ($)'].apply(lambda x: _is_valid_num(x) and float(x) > 0)]
        if len(valid_eps_hist) >= 2:
            old_eps = float(valid_eps_hist.iloc[0]['Diluted EPS ($)'])
            new_eps = float(valid_eps_hist.iloc[-1]['Diluted EPS ($)'])
            n_eps_yrs = int(valid_eps_hist.iloc[-1]['Year']) - int(valid_eps_hist.iloc[0]['Year'])
            if old_eps > 0 and new_eps > 0 and n_eps_yrs > 0:
                raw_eps_cagr = (new_eps / old_eps) ** (1.0 / n_eps_yrs) - 1.0
                if _is_valid_num(raw_eps_cagr):
                    eps_cagr = float(np.clip(raw_eps_cagr, -0.35, 0.45))

        # Dedicated Historical Revenue CAGR (Method 2)
        rev_cagr = eps_cagr
        valid_rev_hist = hist_rows[hist_rows['Revenue ($M)'].apply(lambda x: _is_valid_num(x) and float(x) > 0)]
        if len(valid_rev_hist) >= 2:
            old_rev = float(valid_rev_hist.iloc[0]['Revenue ($M)'])
            new_rev = float(valid_rev_hist.iloc[-1]['Revenue ($M)'])
            n_rev_yrs = int(valid_rev_hist.iloc[-1]['Year']) - int(valid_rev_hist.iloc[0]['Year'])
            if old_rev > 0 and new_rev > 0 and n_rev_yrs > 0:
                raw_rev_cagr = (new_rev / old_rev) ** (1.0 / n_rev_yrs) - 1.0
                if _is_valid_num(raw_rev_cagr):
                    rev_cagr = float(np.clip(raw_rev_cagr, -0.35, 0.45))

        # Baseline EPS, Revenue, Shares for Projections
        base_eps = None
        if not row_2027.empty:
            base_eps = _clean_num(row_2027['Diluted EPS ($)'].values[0])
        if (base_eps is None or base_eps <= 0) and not row_2026_proj.empty:
            base_eps = _clean_num(row_2026_proj['Diluted EPS ($)'].values[0])
        if (base_eps is None or base_eps <= 0) and not valid_eps_hist.empty:
            base_eps = float(valid_eps_hist.iloc[-1]['Diluted EPS ($)'])
        if base_eps is None or base_eps <= 0:
            curr_p_fallback = _clean_num(sub_df['overview_current_price'].iloc[0], default=50.0)
            base_eps = round(curr_p_fallback / fwd_pe, 2) if fwd_pe > 0 else 5.0

        base_rev = None
        if not row_2027.empty:
            base_rev = _clean_num(row_2027['Revenue ($M)'].values[0])
        if (base_rev is None or base_rev <= 0) and not row_2026_proj.empty:
            base_rev = _clean_num(row_2026_proj['Revenue ($M)'].values[0])
        if (base_rev is None or base_rev <= 0) and not valid_rev_hist.empty:
            base_rev = float(valid_rev_hist.iloc[-1]['Revenue ($M)'])
        if base_rev is None or base_rev <= 0:
            base_rev = 5000.0

        valid_shares = sub_df['Shares Outstanding (M)'].dropna()
        valid_shares = [float(s) for s in valid_shares if _is_valid_num(s) and float(s) > 0]
        if valid_shares:
            shares_m = valid_shares[0]
        else:
            mc = _clean_num(sub_df['overview_market_cap'].iloc[0])
            cp = _clean_num(sub_df['overview_current_price'].iloc[0])
            shares_m = round((mc / cp) / 1e6, 2) if (mc and cp and cp > 0) else 290.0

        raw_finviz_g = _clean_num(finviz_growth_cache.get(ticker))
        finviz_g = float(np.clip(raw_finviz_g, -0.35, 0.45)) if raw_finviz_g is not None else eps_cagr

        raw_yahoo_g = _clean_num(yahoo_lt_growth_cache.get(ticker))
        yahoo_g = float(np.clip(raw_yahoo_g, -0.35, 0.45)) if raw_yahoo_g is not None else eps_cagr

        prices_by_year = {}
        raw_tgt_2027 = _clean_num(target_price_cache.get(ticker))
        target_2027_price = round(raw_tgt_2027, 2) if (raw_tgt_2027 is not None and raw_tgt_2027 > 0) else round(base_eps * robust_pe, 2)

        for step, f_year in enumerate(range(current_year + 1, current_year + 6)):  # 2027 to 2031
            k = step
            if f_year == current_year + 1:
                prices_by_year[f_year] = [target_2027_price, target_2027_price, target_2027_price, target_2027_price]
            else:
                # Linear P/E Decay (Option A) across Years 2-5
                pe_k = robust_pe - ((k / 5.0) * (robust_pe - terminal_pe_target))
                pe_k = max(pe_k, terminal_pe_target)

                # M1: EPS CAGR
                eps_m1 = base_eps * ((1.0 + eps_cagr) ** k)
                p_m1 = max(0.01, eps_m1 * pe_k)

                # M2: Independent Revenue CAGR + Net Margin
                proj_rev = round(base_rev * ((1.0 + rev_cagr) ** k), 2)
                net_inc_m2 = proj_rev * robust_net_margin
                eps_m2 = (net_inc_m2 / shares_m) if shares_m > 0 else base_eps
                p_m2 = max(0.01, eps_m2 * pe_k)

                # M3: Yahoo
                eps_m3 = base_eps * ((1.0 + yahoo_g) ** k)
                p_m3 = max(0.01, eps_m3 * pe_k)

                # M4: Finviz
                eps_m4 = base_eps * ((1.0 + finviz_g) ** k)
                p_m4 = max(0.01, eps_m4 * pe_k)

                prices_by_year[f_year] = [p_m1, p_m2, p_m3, p_m4]

        blended_target_prices = {current_year + 1: target_2027_price}
        blended_growths = {current_year + 1: None}

        # Year +2 Fancy Averaging
        p_2028_list = prices_by_year[current_year + 2]
        p_2028_blended = calculate_robust_metric_unweighted(p_2028_list, winsor_pct=0.10, num_stdev=1.0)
        if p_2028_blended is None or p_2028_blended <= 0:
            p_2028_blended = round(target_2027_price * (1.0 + eps_cagr), 2)
        blended_target_prices[current_year + 2] = round(p_2028_blended, 2)
        blended_growths[current_year + 2] = round(((p_2028_blended - target_2027_price) / target_2027_price) * 100.0, 2) if target_2027_price > 0 else None

        # Years +3 to +5 Blended Convergence
        for f_year in range(current_year + 3, current_year + 6):
            prev_prices = prices_by_year[f_year - 1]
            curr_prices = prices_by_year[f_year]
            growths = [
                ((p_c - p_p) / p_p)
                for p_p, p_c in zip(prev_prices, curr_prices)
                if _is_valid_num(p_p) and _is_valid_num(p_c) and p_p > 0 and p_c > 0
            ]
            fancy_growth = calculate_robust_metric_unweighted(growths, winsor_pct=0.10, num_stdev=1.0)
            if fancy_growth is None:
                fancy_growth = 0.08
            blended_growths[f_year] = round(fancy_growth * 100.0, 2)
            prev_blended_price = blended_target_prices[f_year - 1]
            blended_target_prices[f_year] = round(prev_blended_price * (1.0 + fancy_growth), 2)

        # Append Sub-DF rows
        for _, r in sub_df.iterrows():
            r_dict = r.to_dict()
            yr_r = r_dict['Year']
            p_type_r = r_dict['Period Type']

            if not _is_valid_num(r_dict.get('Shares Outstanding (M)')):
                r_dict['Shares Outstanding (M)'] = round(shares_m, 2)
                r_dict['shares_outstanding'] = shares_m * 1e6

            if yr_r == current_year + 1 and p_type_r == 'Projected':
                r_dict['Target Price ($)'] = target_2027_price
                r_dict['Target P/E Multiple'] = round(robust_pe, 2)
                if not _is_valid_num(r_dict.get('P/E Ratio')):
                    r_dict['P/E Ratio'] = round(robust_pe, 2)
                r_dict['Hist EPS CAGR (%)'] = round(eps_cagr * 100.0, 2)
                r_dict['Hist Net Margin (%)'] = round(robust_net_margin * 100.0, 2)
                r_dict['Yahoo LT Growth Rate (%)'] = round(yahoo_g * 100.0, 2) if _is_valid_num(yahoo_g) else None
                r_dict['Finviz EPS 5Y Rate (%)'] = round(finviz_g * 100.0, 2) if _is_valid_num(finviz_g) else None
                r_dict['M1: Projected EPS ($)'] = _clean_num(r_dict.get('Diluted EPS ($)')) or round(base_eps, 2)
                r_dict['M1: Projected Price ($)'] = target_2027_price
                r_dict['M2: Projected Revenue ($M)'] = _clean_num(r_dict.get('Revenue ($M)')) or round(base_rev, 2)
                r_dict['M2: Projected Net Income ($M)'] = _clean_num(r_dict.get('Net Income ($M)')) or round(base_rev * robust_net_margin, 2)
                r_dict['M2: Projected EPS ($)'] = _clean_num(r_dict.get('Diluted EPS ($)')) or round(base_eps, 2)
                r_dict['M2: Projected Price ($)'] = target_2027_price
                r_dict['M3: Projected EPS ($)'] = _clean_num(r_dict.get('Diluted EPS ($)')) or round(base_eps, 2)
                r_dict['M3: Projected Price ($)'] = target_2027_price
                r_dict['M4: Projected EPS ($)'] = _clean_num(r_dict.get('Diluted EPS ($)')) or round(base_eps, 2)
                r_dict['M4: Projected Price ($)'] = target_2027_price
                curr_p_ov = _clean_num(r_dict.get('overview_current_price'))
                r_dict['Blended Growth (%)'] = round(((target_2027_price - curr_p_ov) / curr_p_ov) * 100.0, 2) if (curr_p_ov and curr_p_ov > 0) else None
            else:
                r_dict['Target Price ($)'] = None
                r_dict['Target P/E Multiple'] = None
                r_dict['Blended Growth (%)'] = None
                r_dict['Hist EPS CAGR (%)'] = round(eps_cagr * 100.0, 2)
                r_dict['M1: Projected EPS ($)'] = None
                r_dict['M1: Projected Price ($)'] = None
                r_dict['M2: Projected Revenue ($M)'] = None
                r_dict['Hist Net Margin (%)'] = round(robust_net_margin * 100.0, 2)
                r_dict['M2: Projected Net Income ($M)'] = None
                r_dict['M2: Projected EPS ($)'] = None
                r_dict['M2: Projected Price ($)'] = None
                r_dict['Yahoo LT Growth Rate (%)'] = round(yahoo_g * 100.0, 2) if _is_valid_num(yahoo_g) else None
                r_dict['M3: Projected EPS ($)'] = None
                r_dict['M3: Projected Price ($)'] = None
                r_dict['Finviz EPS 5Y Rate (%)'] = round(finviz_g * 100.0, 2) if _is_valid_num(finviz_g) else None
                r_dict['M4: Projected EPS ($)'] = None
                r_dict['M4: Projected Price ($)'] = None
            expanded_rows.append(r_dict)

        # Append Forecast Rows (2028-2031)
        first_r = sub_df.iloc[0].to_dict()
        ov_cr = _clean_num(first_r.get('Current Ratio'))
        ov_dte = _clean_num(first_r.get('Debt to Equity'))
        ov_atl_vals = [_clean_num(x) for x in sub_df['Total Assets / Total Liabilities'] if _is_valid_num(x)]
        ov_atl = ov_atl_vals[0] if ov_atl_vals else None

        for step, f_year in enumerate(range(current_year + 2, current_year + 6), start=1):
            k = step
            pe_k = robust_pe - ((k / 5.0) * (robust_pe - terminal_pe_target))
            pe_k = max(pe_k, terminal_pe_target)

            proj_rev = round(base_rev * ((1.0 + rev_cagr) ** k), 2)
            eps_m1 = round(base_eps * ((1.0 + eps_cagr) ** k), 2)
            price_m1 = round(eps_m1 * pe_k, 2)

            net_inc_m2 = round(proj_rev * robust_net_margin, 2)
            eps_m2 = round(net_inc_m2 / shares_m, 2) if shares_m > 0 else 0.0
            price_m2 = round(eps_m2 * pe_k, 2)

            eps_m3 = round(base_eps * ((1.0 + yahoo_g) ** k), 2)
            price_m3 = round(eps_m3 * pe_k, 2)

            eps_m4 = round(base_eps * ((1.0 + finviz_g) ** k), 2)
            price_m4 = round(eps_m4 * pe_k, 2)

            tgt_p_yr = blended_target_prices.get(f_year)
            blended_eps = round(tgt_p_yr / pe_k, 2) if (tgt_p_yr and pe_k > 0) else eps_m1
            blended_net_inc = round(blended_eps * shares_m, 2) if (blended_eps is not None and shares_m > 0) else net_inc_m2
            curr_p_ov = _clean_num(first_r.get('overview_current_price'))
            fwd_pe_yr = round(curr_p_ov / blended_eps, 2) if (curr_p_ov and blended_eps and blended_eps > 0) else round(pe_k, 2)

            f_row = {
                'Ticker': ticker,
                'Company Name': first_r['Company Name'],
                'Sector': first_r['Sector'],
                'Industry': first_r['Industry'],
                'Year': f_year,
                'Period Type': 'Projected',
                'Data Source Provider': 'Model_Forecast',
                'Last Updated At': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'overview_market_cap': first_r.get('overview_market_cap'),
                'overview_current_price': first_r.get('overview_current_price'),
                'overview_beta': first_r.get('overview_beta'),
                'overview_forward_pe': first_r.get('overview_forward_pe'),
                'Forward P/E': fwd_pe_yr,
                'Total Assets / Total Liabilities': ov_atl,
                'Current Ratio': ov_cr,
                'Debt to Equity': ov_dte,
                'P/E Ratio': round(pe_k, 2),
                'shares_outstanding': first_r.get('shares_outstanding') or (shares_m * 1e6),
                'Revenue ($M)': proj_rev,
                'Net Income ($M)': blended_net_inc,
                'Net Profit Margin (%)': round(robust_net_margin * 100.0, 2),
                'Diluted EPS ($)': blended_eps,
                'Shares Outstanding (M)': round(shares_m, 2),
                'Total Assets ($M)': None,
                'Total Liabilities ($M)': None,
                'Current Assets ($M)': None,
                'Current Liabilities ($M)': None,

                'Target P/E Multiple': round(pe_k, 2),
                'Blended Growth (%)': blended_growths.get(f_year),
                'Target Price ($)': blended_target_prices.get(f_year),

                'Hist EPS CAGR (%)': round(eps_cagr * 100.0, 2),
                'M1: Projected EPS ($)': eps_m1,
                'M1: Projected Price ($)': price_m1,

                'M2: Projected Revenue ($M)': proj_rev,
                'Hist Net Margin (%)': round(robust_net_margin * 100.0, 2),
                'M2: Projected Net Income ($M)': net_inc_m2,
                'M2: Projected EPS ($)': eps_m2,
                'M2: Projected Price ($)': price_m2,

                'Yahoo LT Growth Rate (%)': round(yahoo_g * 100.0, 2) if _is_valid_num(yahoo_g) else None,
                'M3: Projected EPS ($)': eps_m3,
                'M3: Projected Price ($)': price_m3,

                'Finviz EPS 5Y Rate (%)': round(finviz_g * 100.0, 2) if _is_valid_num(finviz_g) else None,
                'M4: Projected EPS ($)': eps_m4,
                'M4: Projected Price ($)': price_m4,
            }
            expanded_rows.append(f_row)

    conn.close()

    if not expanded_rows:
        print("No valid expanded rows produced.")
        return

    df_out = pd.DataFrame(expanded_rows)
    df_out.sort_values(by=['Ticker', 'Year', 'Period Type'], ascending=[True, False, False], inplace=True)

    prices, market_caps, eps_growths, rev_growths, betas = [], [], [], [], []

    for _, row in df_out.iterrows():
        t = row['Ticker']
        yr = int(row['Year'])
        p_type = row['Period Type']
        sh = _clean_num(row.get('shares_outstanding'))

        if yr > current_year and p_type == 'Projected':
            tgt_p = _clean_num(row.get('Target Price ($)')) or _clean_num(target_price_cache.get(t))
            prices.append(round(tgt_p, 2) if tgt_p is not None else None)
            market_caps.append(round((tgt_p * sh) / 1e9, 2) if (tgt_p is not None and sh is not None and sh > 0) else None)

            yr_growth = growth_cache.get(t, {}).get(yr, {})
            eg = _clean_num(yr_growth.get('eps_growth'))
            rg = _clean_num(yr_growth.get('rev_growth'))
            if eg is None and _is_valid_num(row.get('Blended Growth (%)')):
                eg = float(row.get('Blended Growth (%)')) / 100.0
            if rg is None and _is_valid_num(row.get('Hist EPS CAGR (%)')):
                rg = float(row.get('Hist EPS CAGR (%)')) / 100.0
            eps_growths.append(round(eg * 100.0, 2) if eg is not None else None)
            rev_growths.append(round(rg * 100.0, 2) if rg is not None else None)
            ov_beta = _clean_num(row.get('overview_beta'))
            betas.append(round(ov_beta, 2) if ov_beta is not None else None)

        elif yr == current_year and p_type in ('Projected', 'Historical'):
            curr_p = _clean_num(row.get('overview_current_price'))
            ov_mc = _clean_num(row.get('overview_market_cap'))
            prices.append(round(curr_p, 2) if curr_p is not None else None)
            if curr_p is not None and sh is not None and sh > 0:
                market_caps.append(round((curr_p * sh) / 1e9, 2))
            elif ov_mc is not None:
                market_caps.append(round(ov_mc / 1e9, 2))
            else:
                market_caps.append(None)

            ov_beta = _clean_num(row.get('overview_beta'))
            betas.append(round(ov_beta, 2) if ov_beta is not None else None)

            if p_type == 'Projected':
                yr_growth = growth_cache.get(t, {}).get(yr, {})
                eg = _clean_num(yr_growth.get('eps_growth'))
                rg = _clean_num(yr_growth.get('rev_growth'))
                eps_growths.append(round(eg * 100.0, 2) if eg is not None else None)
                rev_growths.append(round(rg * 100.0, 2) if rg is not None else None)
            else:
                eps_growths.append(None)
                rev_growths.append(None)
        else:
            hist_p = _clean_num(price_cache.get(t, {}).get(yr))
            prices.append(round(hist_p, 2) if hist_p is not None else None)
            market_caps.append(round((hist_p * sh) / 1e9, 2) if (hist_p is not None and sh is not None and sh > 0) else None)
            eps_growths.append(None)
            rev_growths.append(None)
            ov_beta = _clean_num(row.get('overview_beta'))
            betas.append(round(ov_beta, 2) if ov_beta is not None else None)

    fwd_pe_loc = df_out.columns.get_loc('Forward P/E')
    df_out.insert(fwd_pe_loc, 'Consensus Revenue Growth (%)', rev_growths)
    df_out.insert(fwd_pe_loc, 'Consensus Earnings Growth (%)', eps_growths)
    df_out.insert(fwd_pe_loc, 'Beta', betas)
    df_out.insert(fwd_pe_loc, 'Market Cap ($B)', market_caps)
    df_out.insert(fwd_pe_loc, 'Price ($)', prices)

    df_out.drop(
        columns=['overview_market_cap', 'overview_current_price', 'overview_beta', 'overview_forward_pe', 'shares_outstanding'],
        inplace=True,
        errors='ignore',
    )

    os.makedirs(EXPORT_DIR, exist_ok=True)
    latest_filepath = os.path.join(EXPORT_DIR, "15y_export.csv")
    df_out.to_csv(latest_filepath, index=False)

    print(f"\nSuccessfully exported dataset ({len(df_out)} rows, {len(df_out.columns)} columns) to:")
    print(f"  └─ {latest_filepath}")

    open_file(latest_filepath)


if __name__ == "__main__":
    export_clean_dataset(max_history_years=10)
