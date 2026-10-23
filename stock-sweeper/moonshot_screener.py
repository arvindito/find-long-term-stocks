import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    DB_NAME,
    EXPORT_DIR,
    FUNDAMENTAL_LEADERBOARD_CSV,
    QUALITATIVE_MOAT_CSV,
    MOONSHOT_LEADERBOARD_CSV,
    DUAL_SURVIVOR_LOG_CSV,
)
from database import get_db_connection
from qualitative_scorer import score_pillar_1_insider_alignment
from utils import ensure_file_limits, clean_float, classify_market_cap_tier, open_file

ensure_file_limits()


def run_moonshot_screener(
    min_market_cap: float = 300_000_000,
    max_market_cap: float = 10_000_000_000,
    min_rev_growth: float = 0.25,
    max_rev_growth: float = 3.00,
    min_current_ratio: float = 1.5,
    max_debt_to_equity: float = 1.0,
    min_operating_margin: float = -0.15,
    min_beta: float = 1.15,
    min_accel_threshold: float = 0.30,
) -> pd.DataFrame:
    """
    Screens market_data.db for 1% Portfolio Sleeve Asymmetric Moonshot / Inflection candidates
    ($300M - $10B market cap) designed for 6m - 3y high-upside right-tail outcomes:
      - Fortress liquidity runway: Current Ratio >= 1.5 & Debt/Equity <= 1.0
      - Explosive top-line demand: Revenue Growth 25% - 300% (with RevGrowth >= 30% or EPS Growth >= 30%)
      - Point-of-inflection profitability: Operating Margin >= -15% AND Forward P/E > 0
      - High institutional torque: Beta >= 1.15
      - Excludes non-operating sectors (Real Estate, Financial Services, Utilities)
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
        target_mean_price,
        finviz_eps_5y,
        yahoo_lt_growth,
        gross_margins,
        operating_margins,
        revenue_growth,
        earnings_growth,
        current_ratio,
        debt_to_equity,
        beta,
        free_cash_flow,
        roic,
        last_scraped
    FROM company_overview
    WHERE is_active = 1
      AND market_cap >= ?
      AND market_cap <= ?
      AND revenue_growth >= ?
      AND revenue_growth <= ?
      AND current_ratio >= ?
      AND (debt_to_equity IS NULL OR debt_to_equity <= ?)
      AND operating_margins >= ?
      AND forward_pe > 0
      AND beta >= ?
      AND (revenue_growth >= ? OR earnings_growth >= ?)
      AND sector NOT IN ('Real Estate', 'Financial Services', 'Utilities')
    ORDER BY revenue_growth DESC;
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(
            min_market_cap,
            max_market_cap,
            min_rev_growth,
            max_rev_growth,
            min_current_ratio,
            max_debt_to_equity,
            min_operating_margin,
            min_beta,
            min_accel_threshold,
            min_accel_threshold,
        ),
    )
    conn.close()

    if not df.empty:
        df["market_cap_tier"] = df["market_cap"].apply(classify_market_cap_tier)

    print(f"Moonshot Screener complete: Found {len(df)} high-torque inflection candidates ($300M-$10B).")
    return df


def _fetch_moonshot_yf_bundle(ticker: str):
    """Fetches live/cached Yahoo Finance metadata for insider ownership, gross margins, and analyst targets."""
    try:
        yt = yf.Ticker(ticker)
        info = yt.info or {}
        return ticker, info, yt
    except Exception:
        return ticker, {}, None


def score_and_export_moonshots() -> pd.DataFrame:
    """
    Runs the Asymmetric Moonshot Screener, scores candidates across the 5-Pillar
    Asymmetric Inflection Framework (100 pts), exports asymmetric_moonshot_leaderboard.csv,
    and updates the persistent Dual-Survivor Overlap Log (dual_survivor_overlap_log.csv).
    """
    moon_df = run_moonshot_screener()
    if moon_df.empty:
        print("No moonshot candidates found.")
        return pd.DataFrame()

    tickers = moon_df["ticker"].astype(str).tolist()
    print(f"Scoring {len(tickers)} Moonshot candidates across the 5 Asymmetric Inflection Pillars...")

    yf_info_map = {}
    yf_obj_map = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        for t, info, yt_obj in executor.map(_fetch_moonshot_yf_bundle, tickers):
            yf_info_map[t] = info
            yf_obj_map[t] = yt_obj

    conn = get_db_connection(DB_NAME)
    cursor = conn.cursor()
    for t, info in yf_info_map.items():
        gm = clean_float(info.get("grossMargins"))
        tgt = clean_float(info.get("targetMeanPrice"))
        if gm is not None or tgt is not None:
            cursor.execute(
                """
                UPDATE company_overview
                SET gross_margins = COALESCE(?, gross_margins),
                    target_mean_price = COALESCE(?, target_mean_price)
                WHERE ticker = ?
                """,
                (gm, tgt, t),
            )
    conn.commit()
    conn.close()

    # Load main compounder leaderboards for overlap check
    main_screener_tickers = set()
    moat_map = {}
    if os.path.exists(FUNDAMENTAL_LEADERBOARD_CSV):
        try:
            f_df = pd.read_csv(FUNDAMENTAL_LEADERBOARD_CSV)
            main_screener_tickers = set(f_df["Ticker"].astype(str).unique())
            if "Total Moat Score (100)" in f_df.columns:
                for _, fr_row in f_df.iterrows():
                    moat_map[str(fr_row["Ticker"])] = clean_float(fr_row.get("Total Moat Score (100)"))
        except Exception:
            pass
    if os.path.exists(QUALITATIVE_MOAT_CSV):
        try:
            m_df = pd.read_csv(QUALITATIVE_MOAT_CSV)
            for _, mr in m_df.iterrows():
                moat_map[str(mr["Ticker"])] = clean_float(mr.get("Total Moat Score (100)"))
        except Exception:
            pass

    def _score_moonshot_row(row):
        t = str(row["ticker"])
        c_name = str(row.get("company_name", t))
        info = yf_info_map.get(t, {})
        yt_obj = yf_obj_map.get(t)

        mcap = clean_float(row.get("market_cap"), 1e9)
        mcap_b = round(mcap / 1e9, 2)
        curr_p = clean_float(row.get("current_price")) or clean_float(info.get("currentPrice"), 20.0)
        fwd_pe = clean_float(row.get("forward_pe")) or clean_float(info.get("forwardPE"), 25.0)
        rev_g = clean_float(row.get("revenue_growth"), 0.30)
        eps_g = clean_float(row.get("earnings_growth"))
        op_m = clean_float(row.get("operating_margins"), 0.0)
        gm = clean_float(row.get("gross_margins")) or clean_float(info.get("grossMargins"))
        cr = clean_float(row.get("current_ratio"), 1.5)
        dte = clean_float(row.get("debt_to_equity"), 0.0) or 0.0
        beta = clean_float(row.get("beta"), 1.3)
        fcf = clean_float(row.get("free_cash_flow"))
        roic = clean_float(row.get("roic"))

        # 1. Pillar 1 (20 pts): Fortress Survival Runway (Current Ratio + Low Debt)
        if cr >= 3.0:
            cr_pts = 12.0
        elif cr >= 2.2:
            cr_pts = 10.0
        elif cr >= 1.75:
            cr_pts = 8.5
        else:
            cr_pts = 7.0

        if dte <= 0.15:
            debt_pts = 8.0
        elif dte <= 0.40:
            debt_pts = 6.5
        elif dte <= 0.70:
            debt_pts = 5.0
        else:
            debt_pts = 3.5
        p1_runway = round(cr_pts + debt_pts, 1)

        # 2. Pillar 2 (25 pts): Explosive Top-Line & Earnings Velocity
        if rev_g >= 0.75:
            rev_pts = 18.0
        elif rev_g >= 0.50:
            rev_pts = 15.5
        elif rev_g >= 0.35:
            rev_pts = 13.0
        else:
            rev_pts = 10.0

        if eps_g is not None and eps_g >= 0.75:
            eps_pts = 7.0
        elif eps_g is not None and eps_g >= 0.35:
            eps_pts = 5.5
        elif fcf is not None and fcf > 0:
            eps_pts = 5.0
        else:
            eps_pts = 3.5
        p2_velocity = round(rev_pts + eps_pts, 1)

        # 3. Pillar 3 (20 pts): Operating Leverage & Gross Margin Torque
        gm_eff = gm if gm is not None else max(0.25, op_m + 0.22)
        if gm_eff >= 0.55:
            gm_pts = 12.0
        elif gm_eff >= 0.40:
            gm_pts = 10.0
        elif gm_eff >= 0.28:
            gm_pts = 7.5
        else:
            gm_pts = 5.0

        # Inflection bonus: crossing breakeven (-12% to +15% op margin with positive forward EPS) or high FCF margin
        if -0.12 <= op_m <= 0.18 and fwd_pe > 0:
            inflect_pts = 8.0
        elif op_m > 0.18:
            inflect_pts = 7.0
        else:
            inflect_pts = 5.5
        p3_torque = round(gm_pts + inflect_pts, 1)

        # 4. Pillar 4 (20 pts): 1Y Analyst Target & 3Y Inflection Re-Rating Upside
        raw_tgt_1y = clean_float(row.get("target_mean_price")) or clean_float(info.get("targetMeanPrice"))
        if raw_tgt_1y is not None and (raw_tgt_1y > curr_p * 3.0 or raw_tgt_1y < curr_p * 0.35):
            raw_tgt_1y = None

        # Model 3Y Inflection Target Price:
        # Compounded 3Y fundamental velocity (clamped to [22%, 55%] annual with decay) + institutional re-rating
        eff_g = float(np.clip(rev_g * 0.75 + (min(eps_g, 0.80) * 0.25 if eps_g and eps_g > 0 else rev_g * 0.25), 0.22, 0.55))
        g_yr1 = eff_g
        g_yr2 = 0.20 + (eff_g - 0.20) * 0.82
        g_yr3 = 0.20 + (eff_g - 0.20) * (0.82 ** 2)
        comp_3y = (1.0 + g_yr1) * (1.0 + g_yr2) * (1.0 + g_yr3)

        # Re-rating factor: if forward P/E is reasonable (<25x) for a 35%+ grower, multiple expands moderately; if >45x, multiple compresses toward 30x
        if fwd_pe <= 20.0:
            rerate_factor = 1.25
        elif fwd_pe <= 32.0:
            rerate_factor = 1.10
        elif fwd_pe <= 50.0:
            rerate_factor = 0.92
        else:
            rerate_factor = 0.78

        model_3y_price = round(curr_p * comp_3y * rerate_factor, 2)
        tgt_1y_price = round(raw_tgt_1y, 2) if (raw_tgt_1y and raw_tgt_1y > 0) else round(curr_p * (1.0 + g_yr1), 2)
        # Ensure 3Y inflection target is consistent with 1Y consensus trajectory
        if tgt_1y_price > curr_p:
            model_3y_price = round(0.35 * (tgt_1y_price * (1.0 + g_yr2) * (1.0 + g_yr3)) + 0.65 * model_3y_price, 2)

        upside_1y_pct = round(((tgt_1y_price - curr_p) / curr_p) * 100.0, 2) if curr_p > 0 else 0.0
        upside_3y_pct = round(((model_3y_price - curr_p) / curr_p) * 100.0, 2) if curr_p > 0 else 0.0
        multiple_3y_x = round(model_3y_price / curr_p, 2) if curr_p > 0 else 1.0

        if upside_3y_pct >= 250.0:
            p4_upside = 20.0
        elif upside_3y_pct >= 180.0:
            p4_upside = 17.0
        elif upside_3y_pct >= 120.0:
            p4_upside = 14.0
        elif upside_3y_pct >= 80.0:
            p4_upside = 11.0
        else:
            p4_upside = 8.0

        # 5. Pillar 5 (15 pts): Insider Alignment & Sweet-Spot Size Torque
        ins_p1, _ = score_pillar_1_insider_alignment(t, info, yt_obj)
        held_ins = clean_float(info.get("heldPercentInsiders"), 0.0) or 0.0
        insider_pts = min(9.0, round((ins_p1 / 15.0) * 6.0 + (3.0 if held_ins >= 0.02 else 1.5), 1))

        if mcap <= 3_500_000_000:
            size_pts = 6.0
        elif mcap <= 6_500_000_000:
            size_pts = 4.5
        else:
            size_pts = 3.0
        p5_alignment = round(insider_pts + size_pts, 1)

        total_inflection_score = round(p1_runway + p2_velocity + p3_torque + p4_upside + p5_alignment, 1)
        in_main = t in main_screener_tickers

        return {
            "Ticker": t,
            "Company Name": c_name,
            "Sector": row.get("sector", "Unknown"),
            "Industry": row.get("industry", "Unknown"),
            "Market Cap ($B)": mcap_b,
            "Market Cap Tier": row.get("market_cap_tier", classify_market_cap_tier(mcap)),
            "Survived Both Lists": "YES" if in_main else "No",
            "Current Price ($)": round(curr_p, 2),
            "1Y Analyst Target ($)": tgt_1y_price,
            "1Y Upside (%)": upside_1y_pct,
            "3Y Inflection Target ($)": model_3y_price,
            "3Y Projected Return (%)": upside_3y_pct,
            "3Y Implied Multiple (x)": multiple_3y_x,
            "Revenue Growth (%)": round(rev_g * 100.0, 1),
            "Earnings Growth (%)": round(eps_g * 100.0, 1) if eps_g is not None else None,
            "Gross Margin (%)": round(gm_eff * 100.0, 1) if gm_eff is not None else None,
            "Operating Margin (%)": round(op_m * 100.0, 1),
            "ROIC (%)": round(roic * 100.0, 1) if roic is not None else None,
            "Current Ratio": round(cr, 2),
            "Debt / Equity": round(dte, 2),
            "Beta": round(beta, 2),
            "Forward P/E": round(fwd_pe, 1),
            "Pillar 1: Survival Runway (20)": p1_runway,
            "Pillar 2: Growth Velocity (25)": p2_velocity,
            "Pillar 3: Operating Torque (20)": p3_torque,
            "Pillar 4: 3Y Re-Rating Upside (20)": p4_upside,
            "Pillar 5: Insider & Size Torque (15)": p5_alignment,
            "Moonshot Inflection Score (100)": total_inflection_score,
            "Compounder Moat Score (100)": moat_map.get(t),
            "Last Updated At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        row_dicts = [r.to_dict() for _, r in moon_df.iterrows()]
        scored_rows = list(executor.map(_score_moonshot_row, row_dicts))

    out_df = pd.DataFrame(scored_rows)
    out_df.sort_values(
        by=["Moonshot Inflection Score (100)", "3Y Projected Return (%)"],
        ascending=[False, False],
        inplace=True,
    )

    os.makedirs(EXPORT_DIR, exist_ok=True)
    out_df.to_csv(MOONSHOT_LEADERBOARD_CSV, index=False)

    print(f"\nSuccessfully generated Asymmetric Moonshot Leaderboard ({len(out_df)} candidates) at:")
    print(f"  └─ {MOONSHOT_LEADERBOARD_CSV}\n")

    display_cols = [
        "Ticker",
        "Company Name",
        "Market Cap ($B)",
        "Survived Both Lists",
        "Current Price ($)",
        "3Y Inflection Target ($)",
        "3Y Projected Return (%)",
        "Revenue Growth (%)",
        "Operating Margin (%)",
        "Current Ratio",
        "Moonshot Inflection Score (100)",
    ]
    print(out_df[display_cols].head(25).to_string(index=False))

    update_dual_survivor_log(out_df)
    open_file(MOONSHOT_LEADERBOARD_CSV)
    return out_df


def update_dual_survivor_log(moonshot_df: pd.DataFrame) -> pd.DataFrame:
    """
    Identifies rare companies that simultaneously survive BOTH:
      1. The Main Compounder Screener (fundamental_screener_leaderboard.csv)
      2. The Asymmetric Moonshot Screener (asymmetric_moonshot_leaderboard.csv)
    Prints a prominent highlight table after every run and maintains a persistent,
    cumulative historical record in exports/dual_survivor_overlap_log.csv.
    """
    if moonshot_df is None or moonshot_df.empty or not os.path.exists(FUNDAMENTAL_LEADERBOARD_CSV):
        return pd.DataFrame()

    fund_df = pd.read_csv(FUNDAMENTAL_LEADERBOARD_CSV)
    moat_df = pd.read_csv(QUALITATIVE_MOAT_CSV) if os.path.exists(QUALITATIVE_MOAT_CSV) else pd.DataFrame()

    fund_map = {str(r["Ticker"]): r for _, r in fund_df.iterrows()}
    moat_map = {str(r["Ticker"]): r for _, r in moat_df.iterrows()} if not moat_df.empty else {}

    current_overlap_df = moonshot_df[moonshot_df["Ticker"].astype(str).isin(fund_map.keys())].copy()
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load existing persistent log if it exists
    existing_log = {}
    if os.path.exists(DUAL_SURVIVOR_LOG_CSV):
        try:
            prev_df = pd.read_csv(DUAL_SURVIVOR_LOG_CSV)
            for _, pr in prev_df.iterrows():
                tk = str(pr["Ticker"])
                existing_log[tk] = pr.to_dict()
        except Exception:
            existing_log = {}

    # Mark all existing entries as not active on latest run until confirmed below
    for tk in existing_log:
        existing_log[tk]["Active on Latest Run"] = "No"

    for _, mr in current_overlap_df.iterrows():
        tk = str(mr["Ticker"])
        fr = fund_map.get(tk, {})
        qr = moat_map.get(tk, {})

        prev_entry = existing_log.get(tk)
        first_seen = prev_entry.get("First Seen Date", today_str) if prev_entry else today_str
        last_seen_prev = prev_entry.get("Last Seen Date", "") if prev_entry else ""
        prev_count = int(prev_entry.get("Times Appeared", 0)) if prev_entry else 0
        # Increment count if first time or seen on a new date; ensure at least 1
        new_count = (prev_count + 1) if (not prev_entry or last_seen_prev != today_str) else max(1, prev_count)

        moat_val = clean_float(qr.get("Total Moat Score (100)")) or clean_float(mr.get("Compounder Moat Score (100)"))
        passed_elite_moat = "Yes" if tk in moat_map else "No (Passed Fundamental Screener)"

        existing_log[tk] = {
            "Ticker": tk,
            "Company Name": mr.get("Company Name"),
            "Sector": mr.get("Sector"),
            "Industry": mr.get("Industry"),
            "Market Cap ($B)": mr.get("Market Cap ($B)"),
            "Market Cap Tier": mr.get("Market Cap Tier"),
            "Active on Latest Run": "YES",
            "Passed Elite Moat Gate": passed_elite_moat,
            "First Seen Date": first_seen,
            "Last Seen Date": today_str,
            "Times Appeared": new_count,
            "Current Price ($)": mr.get("Current Price ($)"),
            "3Y Inflection Target ($)": mr.get("3Y Inflection Target ($)"),
            "3Y Moonshot Return (%)": mr.get("3Y Projected Return (%)"),
            "5Y Compounder Target ($)": clean_float(fr.get("5Y Target Price ($)")),
            "5Y Compounder CAGR (%)": clean_float(fr.get("5Y Projected CAGR (%)")),
            "Moonshot Inflection Score (100)": mr.get("Moonshot Inflection Score (100)"),
            "Compounder Moat Score (100)": moat_val,
            "Revenue Growth (%)": mr.get("Revenue Growth (%)"),
            "Operating Margin (%)": mr.get("Operating Margin (%)"),
            "ROIC (%)": mr.get("ROIC (%)"),
            "Current Ratio": mr.get("Current Ratio"),
            "Debt / Equity": mr.get("Debt / Equity"),
            "3Y Share Dilution CAGR (%)": clean_float(fr.get("3Y Share Dilution CAGR (%)")),
            "Last Updated At": now_ts,
        }

    log_df = pd.DataFrame(list(existing_log.values()))
    if not log_df.empty:
        log_df.sort_values(
            by=["Active on Latest Run", "Moonshot Inflection Score (100)", "Compounder Moat Score (100)"],
            ascending=[False, False, False],
            inplace=True,
        )
        os.makedirs(EXPORT_DIR, exist_ok=True)
        log_df.to_csv(DUAL_SURVIVOR_LOG_CSV, index=False)

    print("\n" + "=" * 76)
    print(f"★ DUAL-SURVIVOR HIGHLIGHT: {len(current_overlap_df)} COMPANIES SURVIVED BOTH FILTERS TODAY ★")
    print(f"  (Cumulative Running Log: {len(log_df)} total historical dual-survivors in {DUAL_SURVIVOR_LOG_CSV})")
    print("=" * 76)
    if not log_df.empty:
        cols = [
            "Ticker",
            "Company Name",
            "Market Cap Tier",
            "Active on Latest Run",
            "First Seen Date",
            "Last Seen Date",
            "Times Appeared",
            "Current Price ($)",
            "3Y Moonshot Return (%)",
            "5Y Compounder CAGR (%)",
            "Moonshot Inflection Score (100)",
            "Compounder Moat Score (100)",
        ]
        existing_cols = [c for c in cols if c in log_df.columns]
        print(log_df[existing_cols].to_string(index=False))
    print("=" * 76 + "\n")

    return log_df


if __name__ == "__main__":
    score_and_export_moonshots()
