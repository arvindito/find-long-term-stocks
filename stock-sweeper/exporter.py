import os
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf

from config import DB_NAME, EXPORT_DIR, TIMELINE_CSV
from database import init_db, get_db_connection
from screener import run_screener
from enricher import fetch_finviz_eps_next_5y, fetch_batch_historical_year_end_prices
from utils import is_valid_num, clean_float, open_file


def calculate_trend_weighted_metric(values, years, current_year, alpha=0.20, winsor_pct=0.10):
    clean_data = [
        (float(v), int(y))
        for v, y in zip(values, years)
        if is_valid_num(v) and is_valid_num(y) and float(v) > 0
    ]
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
    if not is_valid_num(target_metric) or target_metric <= 0:
        return round(float(np.median(vals)), 4)
    return round(float(target_metric), 4)


def calculate_robust_metric_unweighted(series, winsor_pct=0.10, num_stdev=1.0):
    clean = pd.Series([float(x) for x in series if is_valid_num(x)], dtype=float)
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
    return round(final_val, 4) if is_valid_num(final_val) else None


def _compounded_growth_factor(annual_rate: float, steps: int) -> float:
    """
    Applies a realistic multi-year compounding factor with gentle mean-reversion
    for hyper-growth rates (>18%/yr) across forecast steps k=1..4.
    """
    if steps <= 0:
        return 1.0
    factor = 1.0
    for s in range(1, steps + 1):
        if annual_rate > 0.18:
            # Decay excess growth above 18% by 12% per year toward sustainable levels
            step_r = 0.18 + (annual_rate - 0.18) * (0.88 ** (s - 1))
        else:
            step_r = annual_rate
        factor *= (1.0 + step_r)
    return factor


def export_clean_dataset(max_history_years: int = 10):
    init_db(reset=False)

    print("Running SQL Screener...")
    shortlist_df = run_screener()
    if shortlist_df.empty:
        print("No stocks passed screening. Skipping export.")
        return

    filtered_tickers = shortlist_df["ticker"].tolist()
    placeholders = ",".join(["?"] * len(filtered_tickers))

    current_year = datetime.now().year
    min_historical_year = current_year - max_history_years

    conn = get_db_connection(DB_NAME)

    price_cache = {}
    growth_cache = {}
    target_price_cache = {}
    finviz_growth_cache = {}
    yahoo_lt_growth_cache = {}

    # Load sector median forward P/E from company_overview
    sector_pe_df = pd.read_sql_query(
        "SELECT sector, forward_pe FROM company_overview WHERE is_active = 1 AND market_cap >= 1000000000 AND forward_pe >= 5.0 AND forward_pe <= 80.0",
        conn,
    )
    sector_median_pe = {}
    if not sector_pe_df.empty:
        for sec_name, grp in sector_pe_df.groupby("sector"):
            clean_pes = [float(x) for x in grp["forward_pe"] if is_valid_num(x) and float(x) > 0]
            if clean_pes:
                sector_median_pe[sec_name] = float(np.median(clean_pes))

    # Do NOT fall back yahoo_lt_growth to single-quarter earnings_growth
    ov_meta_df = pd.read_sql_query(
        f"SELECT ticker, target_mean_price, finviz_eps_5y, yahoo_lt_growth FROM company_overview WHERE ticker IN ({placeholders})",
        conn,
        params=filtered_tickers,
    )
    for _, r in ov_meta_df.iterrows():
        t = r["ticker"]
        target_price_cache[t] = clean_float(r.get("target_mean_price"))
        finviz_growth_cache[t] = clean_float(r.get("finviz_eps_5y"))
        yahoo_lt_growth_cache[t] = clean_float(r.get("yahoo_lt_growth"))

    fin_meta_df = pd.read_sql_query(
        f"SELECT ticker, year, period_type, year_end_price, consensus_eps_growth, consensus_rev_growth FROM financial_records WHERE ticker IN ({placeholders}) AND year >= ?",
        conn,
        params=filtered_tickers + [min_historical_year],
    )
    for _, r in fin_meta_df.iterrows():
        t = r["ticker"]
        yr = int(r["year"])
        pt = r["period_type"]
        yep = clean_float(r.get("year_end_price"))
        if pt == "Historical" and yep is not None:
            price_cache.setdefault(t, {})[yr] = yep
        if pt == "Projected":
            eg = clean_float(r.get("consensus_eps_growth"))
            rg = clean_float(r.get("consensus_rev_growth"))
            if eg is not None or rg is not None:
                growth_cache.setdefault(t, {})[yr] = {"eps_growth": eg, "rev_growth": rg}
            # If yahoo_lt_growth is missing or looks like a single-quarter spike (>35%), use +1y consensus EPS growth
            if yr == current_year + 1 and eg is not None:
                curr_ylt = yahoo_lt_growth_cache.get(t)
                if curr_ylt is None or abs(curr_ylt) > 0.35:
                    yahoo_lt_growth_cache[t] = eg

    tickers_missing_prices = [t for t in filtered_tickers if not price_cache.get(t)]
    if tickers_missing_prices:
        batch_prices = fetch_batch_historical_year_end_prices(tickers_missing_prices, min_historical_year, current_year - 1)
        for t, p_map in batch_prices.items():
            if p_map:
                price_cache[t] = p_map

    for t in filtered_tickers:
        try:
            if finviz_growth_cache.get(t) is None:
                finviz_growth_cache[t] = clean_float(fetch_finviz_eps_next_5y(t))
            if target_price_cache.get(t) is None or not growth_cache.get(t):
                yt = yf.Ticker(t)
                info = yt.info or {}
                if target_price_cache.get(t) is None:
                    target_price_cache[t] = clean_float(info.get("targetMeanPrice"))
                if yahoo_lt_growth_cache.get(t) is None:
                    yahoo_lt_growth_cache[t] = clean_float(info.get("longTermPotentialGrowth"))

                if not growth_cache.get(t):
                    rev_est = yt.revenue_estimate
                    eps_est = yt.earnings_estimate
                    growth_cache[t] = {}
                    if isinstance(rev_est, pd.DataFrame) and isinstance(eps_est, pd.DataFrame):
                        if "0y" in rev_est.index and "0y" in eps_est.index:
                            growth_cache[t][current_year] = {
                                "rev_growth": clean_float(rev_est.loc["0y", "growth"]) if "growth" in rev_est.columns else None,
                                "eps_growth": clean_float(eps_est.loc["0y", "growth"]) if "growth" in eps_est.columns else None,
                            }
                        if "+1y" in rev_est.index and "+1y" in eps_est.index:
                            eg_1y = clean_float(eps_est.loc["+1y", "growth"]) if "growth" in eps_est.columns else None
                            growth_cache[t][current_year + 1] = {
                                "rev_growth": clean_float(rev_est.loc["+1y", "growth"]) if "growth" in rev_est.columns else None,
                                "eps_growth": eg_1y,
                            }
                            if yahoo_lt_growth_cache.get(t) is None and eg_1y is not None:
                                yahoo_lt_growth_cache[t] = eg_1y
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
        sub_df = df[df["Ticker"] == ticker].copy()
        if sub_df.empty:
            continue

        curr_p_ov = clean_float(sub_df["overview_current_price"].iloc[0], default=50.0)
        fwd_pe = clean_float(sub_df["overview_forward_pe"].iloc[0], default=18.0)
        if fwd_pe <= 0:
            fwd_pe = 18.0

        # Fix 1: Normalize foreign-currency Projected rows (e.g., KARO in ZAR, TSM in TWD, SONY in JPY)
        proj_mask = sub_df["Period Type"] == "Projected"
        if proj_mask.any() and curr_p_ov > 0 and fwd_pe > 0:
            proj_eps_vals = [clean_float(x) for x in sub_df.loc[proj_mask, "Diluted EPS ($)"] if is_valid_num(x) and float(x) > 0]
            if proj_eps_vals:
                max_proj_eps = max(proj_eps_vals)
                implied_usd_eps = curr_p_ov / fwd_pe
                # If consensus EPS is in local currency (>2.2x or <0.35x implied USD forward EPS), normalize to USD
                if (max_proj_eps / implied_usd_eps) > 2.2 or (max_proj_eps / implied_usd_eps) < 0.35:
                    fx_factor = implied_usd_eps / max_proj_eps
                    for idx_p in sub_df[proj_mask].index:
                        old_e = clean_float(sub_df.loc[idx_p, "Diluted EPS ($)"])
                        old_r = clean_float(sub_df.loc[idx_p, "Revenue ($M)"])
                        old_ni = clean_float(sub_df.loc[idx_p, "Net Income ($M)"])
                        if old_e is not None and old_e > 0:
                            new_e = round(old_e * fx_factor, 2)
                            sub_df.loc[idx_p, "Diluted EPS ($)"] = new_e
                            sub_df.loc[idx_p, "Forward P/E"] = round(curr_p_ov / new_e, 2) if new_e > 0 else round(fwd_pe, 2)
                            sub_df.loc[idx_p, "P/E Ratio"] = round(curr_p_ov / new_e, 2) if new_e > 0 else round(fwd_pe, 2)
                        if old_r is not None:
                            sub_df.loc[idx_p, "Revenue ($M)"] = round(old_r * fx_factor, 2)
                        if old_ni is not None:
                            sub_df.loc[idx_p, "Net Income ($M)"] = round(old_ni * fx_factor, 2)

        # Normalize historical stock splits, ADR ratio shifts, and dual-class share count jumps (>1.75x or <0.55x YoY)
        hist_mask = sub_df["Period Type"] == "Historical"
        hist_asc_idx = sub_df[hist_mask].sort_values(by="Year", ascending=True).index.tolist()
        if len(hist_asc_idx) >= 2:
            for pos in range(len(hist_asc_idx) - 1, 0, -1):
                curr_idx = hist_asc_idx[pos]
                prev_idx = hist_asc_idx[pos - 1]
                s_curr = clean_float(sub_df.loc[curr_idx, "Shares Outstanding (M)"])
                s_prev = clean_float(sub_df.loc[prev_idx, "Shares Outstanding (M)"])
                if s_curr and s_prev and s_curr > 0 and s_prev > 0:
                    sh_ratio = s_curr / s_prev
                    if sh_ratio > 1.75 or sh_ratio < 0.55:
                        for k_pos in range(pos):
                            k_idx = hist_asc_idx[k_pos]
                            old_s = clean_float(sub_df.loc[k_idx, "Shares Outstanding (M)"])
                            old_e = clean_float(sub_df.loc[k_idx, "Diluted EPS ($)"])
                            k_yr = int(sub_df.loc[k_idx, "Year"])
                            p_hist = clean_float(price_cache.get(ticker, {}).get(k_yr))
                            if old_s is not None and old_s > 0:
                                sub_df.loc[k_idx, "Shares Outstanding (M)"] = round(old_s * sh_ratio, 2)
                            if old_e is not None and old_e > 0 and sh_ratio > 1.75:
                                # Only split-adjust historical EPS if p_hist / old_e indicates pre-split EPS vs split-adjusted price
                                if p_hist is None or (p_hist / old_e) < 4.5:
                                    new_e_hist = round(old_e / sh_ratio, 2)
                                    if new_e_hist > 0:
                                        sub_df.loc[k_idx, "Diluted EPS ($)"] = new_e_hist
                                        if p_hist and p_hist > 0:
                                            sub_df.loc[k_idx, "P/E Ratio"] = round(p_hist / new_e_hist, 2)

        row_2027 = sub_df[(sub_df["Year"] == current_year + 1) & (sub_df["Period Type"] == "Projected")]
        row_2026_proj = sub_df[(sub_df["Year"] == current_year) & (sub_df["Period Type"] == "Projected")]
        hist_rows = sub_df[sub_df["Period Type"] == "Historical"].sort_values(by="Year", ascending=True)

        all_net_margins = []
        all_pe_ratios = []
        hist_pe_ratios = []
        all_years = []

        for _, r in sub_df.iterrows():
            y = int(r["Year"])
            p_m = clean_float(r["Net Profit Margin (%)"])
            r_pe = clean_float(r["P/E Ratio"])
            r_fpe = clean_float(r["Forward P/E"])
            p_pe = r_pe if (r_pe is not None and 2.0 <= r_pe <= 120.0) else (r_fpe if (r_fpe is not None and 2.0 <= r_fpe <= 120.0) else None)

            all_net_margins.append((p_m / 100.0) if (p_m is not None and p_m > 0) else None)
            all_pe_ratios.append(p_pe)
            if r["Period Type"] == "Historical" and r_pe is not None and 2.0 <= r_pe <= 120.0:
                hist_pe_ratios.append(r_pe)
            all_years.append(y)

        robust_net_margin = calculate_trend_weighted_metric(all_net_margins, all_years, current_year, alpha=0.20, winsor_pct=0.10) or 0.15
        raw_robust_pe = calculate_trend_weighted_metric(all_pe_ratios, all_years, current_year, alpha=0.20, winsor_pct=0.10) or round(fwd_pe, 2)

        # Fix 3: Realistic 5Y Growth Bounds [-25%, +30%]
        eps_cagr = 0.08
        valid_eps_hist = hist_rows[hist_rows["Diluted EPS ($)"].apply(lambda x: is_valid_num(x) and float(x) > 0)]
        if len(valid_eps_hist) >= 2:
            old_eps = float(valid_eps_hist.iloc[0]["Diluted EPS ($)"])
            new_eps = float(valid_eps_hist.iloc[-1]["Diluted EPS ($)"])
            n_eps_yrs = int(valid_eps_hist.iloc[-1]["Year"]) - int(valid_eps_hist.iloc[0]["Year"])
            if old_eps > 0 and new_eps > 0 and n_eps_yrs > 0:
                raw_eps_cagr = (new_eps / old_eps) ** (1.0 / n_eps_yrs) - 1.0
                if is_valid_num(raw_eps_cagr):
                    eps_cagr = float(np.clip(raw_eps_cagr, -0.25, 0.30))

        rev_cagr = eps_cagr
        valid_rev_hist = hist_rows[hist_rows["Revenue ($M)"].apply(lambda x: is_valid_num(x) and float(x) > 0)]
        if len(valid_rev_hist) >= 2:
            old_rev = float(valid_rev_hist.iloc[0]["Revenue ($M)"])
            new_rev = float(valid_rev_hist.iloc[-1]["Revenue ($M)"])
            n_rev_yrs = int(valid_rev_hist.iloc[-1]["Year"]) - int(valid_rev_hist.iloc[0]["Year"])
            if old_rev > 0 and new_rev > 0 and n_rev_yrs > 0:
                raw_rev_cagr = (new_rev / old_rev) ** (1.0 / n_rev_yrs) - 1.0
                if is_valid_num(raw_rev_cagr):
                    rev_cagr = float(np.clip(raw_rev_cagr, -0.25, 0.30))

        raw_finviz_g = clean_float(finviz_growth_cache.get(ticker))
        finviz_g = float(np.clip(raw_finviz_g, -0.25, 0.30)) if raw_finviz_g is not None else eps_cagr

        # Use multi-year consensus / Finviz / historical median rather than single-quarter YoY earningsGrowth
        raw_yahoo_g = clean_float(yahoo_lt_growth_cache.get(ticker))
        if raw_yahoo_g is not None and abs(raw_yahoo_g) <= 0.45:
            yahoo_g = float(np.clip(raw_yahoo_g, -0.25, 0.30))
        else:
            yahoo_g = float(np.median([eps_cagr, rev_cagr, finviz_g]))

        # Baseline EPS, Revenue, Shares for Projections
        base_eps = None
        if not row_2027.empty:
            base_eps = clean_float(row_2027["Diluted EPS ($)"].values[0])
        if (base_eps is None or base_eps <= 0) and not row_2026_proj.empty:
            base_eps = clean_float(row_2026_proj["Diluted EPS ($)"].values[0])
        if (base_eps is None or base_eps <= 0) and not valid_eps_hist.empty:
            base_eps = float(valid_eps_hist.iloc[-1]["Diluted EPS ($)"])
        if base_eps is None or base_eps <= 0:
            base_eps = round(curr_p_ov / fwd_pe, 2) if fwd_pe > 0 else 5.0

        base_rev = None
        if not row_2027.empty:
            base_rev = clean_float(row_2027["Revenue ($M)"].values[0])
        if (base_rev is None or base_rev <= 0) and not row_2026_proj.empty:
            base_rev = clean_float(row_2026_proj["Revenue ($M)"].values[0])
        if (base_rev is None or base_rev <= 0) and not valid_rev_hist.empty:
            base_rev = float(valid_rev_hist.iloc[-1]["Revenue ($M)"])
        if base_rev is None or base_rev <= 0:
            base_rev = 5000.0

        valid_shares = sub_df["Shares Outstanding (M)"].dropna()
        valid_shares = [float(s) for s in valid_shares if is_valid_num(s) and float(s) > 0]
        if valid_shares:
            shares_m = valid_shares[0]
        else:
            mc = clean_float(sub_df["overview_market_cap"].iloc[0])
            shares_m = round((mc / curr_p_ov) / 1e6, 2) if (mc and curr_p_ov > 0) else 290.0

        # Historical 3-year net share count CAGR (dilution/buyback drift),
        # normalized for stock splits, ADR ratio shifts, and dual-class share reporting jumps
        share_cagr = 0.0
        valid_shares_hist = hist_rows[hist_rows["Shares Outstanding (M)"].apply(lambda x: is_valid_num(x) and float(x) > 0)]
        if len(valid_shares_hist) >= 2:
            sh_vals = [float(x) for x in valid_shares_hist["Shares Outstanding (M)"].tolist()]
            sh_yrs = [int(y) for y in valid_shares_hist["Year"].tolist()]
            # Walk backward from most recent year and remove split/class discontinuities (>1.75x or <0.55x YoY)
            adj_sh = list(sh_vals)
            for idx_s in range(len(adj_sh) - 1, 0, -1):
                ratio = adj_sh[idx_s] / adj_sh[idx_s - 1] if adj_sh[idx_s - 1] > 0 else 1.0
                if ratio > 1.75 or ratio < 0.55:
                    for k_s in range(idx_s):
                        adj_sh[k_s] *= ratio
            latest_sh_yr = sh_yrs[-1]
            window_pairs = [(y, s) for y, s in zip(sh_yrs, adj_sh) if y >= latest_sh_yr - 3]
            if len(window_pairs) < 2:
                window_pairs = list(zip(sh_yrs, adj_sh))[-4:]
            old_yr, old_sh = window_pairs[0]
            new_yr, new_sh = window_pairs[-1]
            n_sh_yrs = new_yr - old_yr
            if old_sh > 0 and new_sh > 0 and n_sh_yrs > 0:
                raw_share_cagr = (new_sh / old_sh) ** (1.0 / n_sh_yrs) - 1.0
                if is_valid_num(raw_share_cagr):
                    share_cagr = float(np.clip(raw_share_cagr, -0.10, 0.15))

        # Fix 2: Smooth Year 1 -> Year 5 P/E Transition (Anchored to Current Forward P/E Regime)
        sec_name = str(sub_df["Sector"].iloc[0]) if not sub_df.empty else "Unknown"
        sec_pe = sector_median_pe.get(sec_name, 18.0)
        sector_pe_floor = max(10.0, sec_pe * 0.65)
        expected_g = max(0.0, float(np.median([eps_cagr, rev_cagr, yahoo_g, finviz_g])))
        peg_terminal_ceiling = min(45.0, max(sec_pe * 1.15, sec_pe + (expected_g * 100.0 * 0.85)))

        raw_tgt_2027 = clean_float(target_price_cache.get(ticker))
        # Guard against foreign-currency analyst target prices (>2.5x or <0.35x current USD price)
        if raw_tgt_2027 is not None and (raw_tgt_2027 > curr_p_ov * 2.5 or raw_tgt_2027 < curr_p_ov * 0.35):
            raw_tgt_2027 = None

        implied_curr_pe = (curr_p_ov / base_eps) if base_eps > 0 else fwd_pe
        anchor_pe = min(45.0, max(sector_pe_floor, implied_curr_pe if 4.0 <= implied_curr_pe <= 60.0 else fwd_pe))
        starting_pe_ceiling = min(45.0, max(anchor_pe * 1.25, sec_pe * 1.15))
        robust_pe = round(max(sector_pe_floor, min(raw_robust_pe, starting_pe_ceiling)), 2)

        target_2027_price = (
            round(raw_tgt_2027, 2)
            if (raw_tgt_2027 is not None and raw_tgt_2027 > 0)
            else round(base_eps * robust_pe, 2)
        )
        # Align Year 1 starting multiple with Year 1 target price so Year 2 never jumps off a different multiple base
        implied_2027_pe = (target_2027_price / base_eps) if base_eps > 0 else robust_pe
        if 4.0 <= implied_2027_pe <= 55.0:
            robust_pe = round(0.65 * implied_2027_pe + 0.35 * robust_pe, 2)

        valid_hist_pes = hist_pe_ratios if hist_pe_ratios else [p for p in all_pe_ratios if is_valid_num(p) and p > 0]
        raw_hist_median_pe = float(np.median(valid_hist_pes)) if valid_hist_pes else sec_pe
        terminal_pe_target = round(max(sector_pe_floor, min(raw_hist_median_pe, robust_pe, peg_terminal_ceiling)), 2)

        prices_by_year = {}
        for step, f_year in enumerate(range(current_year + 1, current_year + 6)):  # 2027 to 2031
            k = step
            if f_year == current_year + 1:
                prices_by_year[f_year] = [target_2027_price, target_2027_price, target_2027_price, target_2027_price]
            else:
                pe_k = robust_pe - ((k / 4.0) * (robust_pe - terminal_pe_target))
                pe_k = max(pe_k, terminal_pe_target)
                proj_shares = shares_m * ((1.0 + share_cagr) ** k)

                # M1: EPS CAGR
                eps_m1 = base_eps * _compounded_growth_factor(eps_cagr, k)
                p_m1 = max(0.01, eps_m1 * pe_k)

                # M2: Independent Revenue CAGR + Net Margin + Share Drift
                proj_rev = round(base_rev * _compounded_growth_factor(rev_cagr, k), 2)
                net_inc_m2 = proj_rev * robust_net_margin
                eps_m2 = (net_inc_m2 / proj_shares) if proj_shares > 0 else base_eps
                p_m2 = max(0.01, eps_m2 * pe_k)

                # M3: Yahoo Consensus Trajectory
                eps_m3 = base_eps * _compounded_growth_factor(yahoo_g, k)
                p_m3 = max(0.01, eps_m3 * pe_k)

                # M4: Finviz 5Y EPS Consensus
                eps_m4 = base_eps * _compounded_growth_factor(finviz_g, k)
                p_m4 = max(0.01, eps_m4 * pe_k)

                prices_by_year[f_year] = [p_m1, p_m2, p_m3, p_m4]

        blended_target_prices = {current_year + 1: target_2027_price}
        blended_growths = {current_year + 1: None}

        # Year +2 Blended Convergence
        p_2028_list = prices_by_year[current_year + 2]
        p_2028_blended = calculate_robust_metric_unweighted(p_2028_list, winsor_pct=0.10, num_stdev=1.0)
        if p_2028_blended is None or p_2028_blended <= 0:
            p_2028_blended = round(target_2027_price * (1.0 + eps_cagr), 2)
        blended_target_prices[current_year + 2] = round(p_2028_blended, 2)
        blended_growths[current_year + 2] = (
            round(((p_2028_blended - target_2027_price) / target_2027_price) * 100.0, 2)
            if target_2027_price > 0
            else None
        )

        # Years +3 to +5 Blended Convergence
        for f_year in range(current_year + 3, current_year + 6):
            prev_prices = prices_by_year[f_year - 1]
            curr_prices = prices_by_year[f_year]
            growths = [
                ((p_c - p_p) / p_p)
                for p_p, p_c in zip(prev_prices, curr_prices)
                if is_valid_num(p_p) and is_valid_num(p_c) and p_p > 0 and p_c > 0
            ]
            fancy_growth = calculate_robust_metric_unweighted(growths, winsor_pct=0.10, num_stdev=1.0)
            if fancy_growth is None:
                fancy_growth = 0.08
            blended_growths[f_year] = round(fancy_growth * 100.0, 2)
            prev_blended_price = blended_target_prices[f_year - 1]
            blended_target_prices[f_year] = round(prev_blended_price * (1.0 + fancy_growth), 2)

        for _, r in sub_df.iterrows():
            r_dict = r.to_dict()
            yr_r = r_dict["Year"]
            p_type_r = r_dict["Period Type"]

            if not is_valid_num(r_dict.get("Shares Outstanding (M)")):
                r_dict["Shares Outstanding (M)"] = round(shares_m, 2)
                r_dict["shares_outstanding"] = shares_m * 1e6

            r_dict["3Y Share Dilution CAGR (%)"] = round(share_cagr * 100.0, 2)

            if yr_r == current_year + 1 and p_type_r == "Projected":
                r_dict["Target Price ($)"] = target_2027_price
                r_dict["Target P/E Multiple"] = round(robust_pe, 2)
                if not is_valid_num(r_dict.get("P/E Ratio")):
                    r_dict["P/E Ratio"] = round(robust_pe, 2)
                r_dict["Hist EPS CAGR (%)"] = round(eps_cagr * 100.0, 2)
                r_dict["Hist Net Margin (%)"] = round(robust_net_margin * 100.0, 2)
                r_dict["Yahoo LT Growth Rate (%)"] = round(yahoo_g * 100.0, 2) if is_valid_num(yahoo_g) else None
                r_dict["Finviz EPS 5Y Rate (%)"] = round(finviz_g * 100.0, 2) if is_valid_num(finviz_g) else None
                r_dict["M1: Projected EPS ($)"] = clean_float(r_dict.get("Diluted EPS ($)")) or round(base_eps, 2)
                r_dict["M1: Projected Price ($)"] = target_2027_price
                r_dict["M2: Projected Revenue ($M)"] = clean_float(r_dict.get("Revenue ($M)")) or round(base_rev, 2)
                r_dict["M2: Projected Net Income ($M)"] = clean_float(r_dict.get("Net Income ($M)")) or round(base_rev * robust_net_margin, 2)
                r_dict["M2: Projected EPS ($)"] = clean_float(r_dict.get("Diluted EPS ($)")) or round(base_eps, 2)
                r_dict["M2: Projected Price ($)"] = target_2027_price
                r_dict["M3: Projected EPS ($)"] = clean_float(r_dict.get("Diluted EPS ($)")) or round(base_eps, 2)
                r_dict["M3: Projected Price ($)"] = target_2027_price
                r_dict["M4: Projected EPS ($)"] = clean_float(r_dict.get("Diluted EPS ($)")) or round(base_eps, 2)
                r_dict["M4: Projected Price ($)"] = target_2027_price
                r_dict["Blended Growth (%)"] = (
                    round(((target_2027_price - curr_p_ov) / curr_p_ov) * 100.0, 2)
                    if (curr_p_ov and curr_p_ov > 0)
                    else None
                )
            else:
                r_dict["Target Price ($)"] = None
                r_dict["Target P/E Multiple"] = None
                r_dict["Blended Growth (%)"] = None
                r_dict["Hist EPS CAGR (%)"] = round(eps_cagr * 100.0, 2)
                r_dict["M1: Projected EPS ($)"] = None
                r_dict["M1: Projected Price ($)"] = None
                r_dict["M2: Projected Revenue ($M)"] = None
                r_dict["Hist Net Margin (%)"] = round(robust_net_margin * 100.0, 2)
                r_dict["M2: Projected Net Income ($M)"] = None
                r_dict["M2: Projected EPS ($)"] = None
                r_dict["M2: Projected Price ($)"] = None
                r_dict["Yahoo LT Growth Rate (%)"] = round(yahoo_g * 100.0, 2) if is_valid_num(yahoo_g) else None
                r_dict["M3: Projected EPS ($)"] = None
                r_dict["M3: Projected Price ($)"] = None
                r_dict["Finviz EPS 5Y Rate (%)"] = round(finviz_g * 100.0, 2) if is_valid_num(finviz_g) else None
                r_dict["M4: Projected EPS ($)"] = None
                r_dict["M4: Projected Price ($)"] = None
            expanded_rows.append(r_dict)

        first_r = sub_df.iloc[0].to_dict()
        ov_cr = clean_float(first_r.get("Current Ratio"))
        ov_dte = clean_float(first_r.get("Debt to Equity"))
        ov_atl_vals = [clean_float(x) for x in sub_df["Total Assets / Total Liabilities"] if is_valid_num(x)]
        ov_atl = ov_atl_vals[0] if ov_atl_vals else None

        for step, f_year in enumerate(range(current_year + 2, current_year + 6), start=1):
            k = step
            pe_k = robust_pe - ((k / 4.0) * (robust_pe - terminal_pe_target))
            pe_k = max(pe_k, terminal_pe_target)
            proj_shares = shares_m * ((1.0 + share_cagr) ** k)

            proj_rev = round(base_rev * _compounded_growth_factor(rev_cagr, k), 2)
            eps_m1 = round(base_eps * _compounded_growth_factor(eps_cagr, k), 2)
            price_m1 = round(eps_m1 * pe_k, 2)

            net_inc_m2 = round(proj_rev * robust_net_margin, 2)
            eps_m2 = round(net_inc_m2 / proj_shares, 2) if proj_shares > 0 else 0.0
            price_m2 = round(eps_m2 * pe_k, 2)

            eps_m3 = round(base_eps * _compounded_growth_factor(yahoo_g, k), 2)
            price_m3 = round(eps_m3 * pe_k, 2)

            eps_m4 = round(base_eps * _compounded_growth_factor(finviz_g, k), 2)
            price_m4 = round(eps_m4 * pe_k, 2)

            tgt_p_yr = blended_target_prices.get(f_year)
            blended_eps = round(tgt_p_yr / pe_k, 2) if (tgt_p_yr and pe_k > 0) else eps_m1
            blended_net_inc = round(blended_eps * proj_shares, 2) if (blended_eps is not None and proj_shares > 0) else net_inc_m2
            fwd_pe_yr = round(curr_p_ov / blended_eps, 2) if (curr_p_ov and blended_eps and blended_eps > 0) else round(pe_k, 2)

            f_row = {
                "Ticker": ticker,
                "Company Name": first_r["Company Name"],
                "Sector": first_r["Sector"],
                "Industry": first_r["Industry"],
                "Year": f_year,
                "Period Type": "Projected",
                "Data Source Provider": "Model_Forecast",
                "Last Updated At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "overview_market_cap": first_r.get("overview_market_cap"),
                "overview_current_price": first_r.get("overview_current_price"),
                "overview_beta": first_r.get("overview_beta"),
                "overview_forward_pe": first_r.get("overview_forward_pe"),
                "Forward P/E": fwd_pe_yr,
                "Total Assets / Total Liabilities": ov_atl,
                "Current Ratio": ov_cr,
                "Debt to Equity": ov_dte,
                "P/E Ratio": round(pe_k, 2),
                "shares_outstanding": proj_shares * 1e6,
                "Revenue ($M)": proj_rev,
                "Net Income ($M)": blended_net_inc,
                "Net Profit Margin (%)": round(robust_net_margin * 100.0, 2),
                "Diluted EPS ($)": blended_eps,
                "Shares Outstanding (M)": round(proj_shares, 2),
                "3Y Share Dilution CAGR (%)": round(share_cagr * 100.0, 2),
                "Total Assets ($M)": None,
                "Total Liabilities ($M)": None,
                "Current Assets ($M)": None,
                "Current Liabilities ($M)": None,
                "Target P/E Multiple": round(pe_k, 2),
                "Blended Growth (%)": blended_growths.get(f_year),
                "Target Price ($)": blended_target_prices.get(f_year),
                "Hist EPS CAGR (%)": round(eps_cagr * 100.0, 2),
                "M1: Projected EPS ($)": eps_m1,
                "M1: Projected Price ($)": price_m1,
                "M2: Projected Revenue ($M)": proj_rev,
                "Hist Net Margin (%)": round(robust_net_margin * 100.0, 2),
                "M2: Projected Net Income ($M)": net_inc_m2,
                "M2: Projected EPS ($)": eps_m2,
                "M2: Projected Price ($)": price_m2,
                "Yahoo LT Growth Rate (%)": round(yahoo_g * 100.0, 2) if is_valid_num(yahoo_g) else None,
                "M3: Projected EPS ($)": eps_m3,
                "M3: Projected Price ($)": price_m3,
                "Finviz EPS 5Y Rate (%)": round(finviz_g * 100.0, 2) if is_valid_num(finviz_g) else None,
                "M4: Projected EPS ($)": eps_m4,
                "M4: Projected Price ($)": price_m4,
            }
            expanded_rows.append(f_row)

    conn.close()

    if not expanded_rows:
        print("No valid expanded rows produced.")
        return

    df_out = pd.DataFrame(expanded_rows)
    df_out.sort_values(by=["Ticker", "Year", "Period Type"], ascending=[True, False, False], inplace=True)

    prices, market_caps, eps_growths, rev_growths, betas = [], [], [], [], []

    for _, row in df_out.iterrows():
        t = row["Ticker"]
        yr = int(row["Year"])
        p_type = row["Period Type"]
        sh = clean_float(row.get("shares_outstanding"))

        if yr > current_year and p_type == "Projected":
            tgt_p = clean_float(row.get("Target Price ($)")) or clean_float(target_price_cache.get(t))
            prices.append(round(tgt_p, 2) if tgt_p is not None else None)
            market_caps.append(round((tgt_p * sh) / 1e9, 2) if (tgt_p is not None and sh is not None and sh > 0) else None)

            yr_growth = growth_cache.get(t, {}).get(yr, {})
            eg = clean_float(yr_growth.get("eps_growth"))
            rg = clean_float(yr_growth.get("rev_growth"))
            if eg is None and is_valid_num(row.get("Blended Growth (%)")):
                eg = float(row.get("Blended Growth (%)")) / 100.0
            if rg is None and is_valid_num(row.get("Hist EPS CAGR (%)")):
                rg = float(row.get("Hist EPS CAGR (%)")) / 100.0
            eps_growths.append(round(eg * 100.0, 2) if eg is not None else None)
            rev_growths.append(round(rg * 100.0, 2) if rg is not None else None)
            ov_beta = clean_float(row.get("overview_beta"))
            betas.append(round(ov_beta, 2) if ov_beta is not None else None)

        elif yr == current_year and p_type in ("Projected", "Historical"):
            curr_p = clean_float(row.get("overview_current_price"))
            ov_mc = clean_float(row.get("overview_market_cap"))
            prices.append(round(curr_p, 2) if curr_p is not None else None)
            if curr_p is not None and sh is not None and sh > 0:
                market_caps.append(round((curr_p * sh) / 1e9, 2))
            elif ov_mc is not None:
                market_caps.append(round(ov_mc / 1e9, 2))
            else:
                market_caps.append(None)

            ov_beta = clean_float(row.get("overview_beta"))
            betas.append(round(ov_beta, 2) if ov_beta is not None else None)

            if p_type == "Projected":
                yr_growth = growth_cache.get(t, {}).get(yr, {})
                eg = clean_float(yr_growth.get("eps_growth"))
                rg = clean_float(yr_growth.get("rev_growth"))
                eps_growths.append(round(eg * 100.0, 2) if eg is not None else None)
                rev_growths.append(round(rg * 100.0, 2) if rg is not None else None)
            else:
                eps_growths.append(None)
                rev_growths.append(None)
        else:
            hist_p = clean_float(price_cache.get(t, {}).get(yr))
            prices.append(round(hist_p, 2) if hist_p is not None else None)
            market_caps.append(round((hist_p * sh) / 1e9, 2) if (hist_p is not None and sh is not None and sh > 0) else None)
            eps_growths.append(None)
            rev_growths.append(None)
            ov_beta = clean_float(row.get("overview_beta"))
            betas.append(round(ov_beta, 2) if ov_beta is not None else None)

    fwd_pe_loc = df_out.columns.get_loc("Forward P/E")
    df_out.insert(fwd_pe_loc, "Consensus Revenue Growth (%)", rev_growths)
    df_out.insert(fwd_pe_loc, "Consensus Earnings Growth (%)", eps_growths)
    df_out.insert(fwd_pe_loc, "Beta", betas)
    df_out.insert(fwd_pe_loc, "Market Cap ($B)", market_caps)
    df_out.insert(fwd_pe_loc, "Price ($)", prices)

    df_out.drop(
        columns=["overview_market_cap", "overview_current_price", "overview_beta", "overview_forward_pe", "shares_outstanding"],
        inplace=True,
        errors="ignore",
    )

    os.makedirs(EXPORT_DIR, exist_ok=True)
    df_out.to_csv(TIMELINE_CSV, index=False)

    print(f"\nSuccessfully exported dataset ({len(df_out)} rows, {len(df_out.columns)} columns) to:")
    print(f"  └─ {TIMELINE_CSV}")

    open_file(TIMELINE_CSV)


if __name__ == "__main__":
    export_clean_dataset(max_history_years=10)
