import math
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SWEEPER_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "stock-sweeper"))
DB_PATH = os.path.join(SWEEPER_DIR, "market_data.db")
EXPORTS_DIR = os.path.join(SWEEPER_DIR, "exports")
STATIC_DIR = os.path.join(BASE_DIR, "static")

FUNDAMENTAL_CSV = os.path.join(EXPORTS_DIR, "fundamental_screener_leaderboard.csv")
QUALITATIVE_CSV = os.path.join(EXPORTS_DIR, "qualitative_moat_leaderboard.csv")
MEGA_CAP_CSV = os.path.join(EXPORTS_DIR, "mega_cap_watch_leaderboard.csv")
MOONSHOT_CSV = os.path.join(EXPORTS_DIR, "asymmetric_moonshot_leaderboard.csv")
DUAL_SURVIVOR_CSV = os.path.join(EXPORTS_DIR, "dual_survivor_overlap_log.csv")
TIMELINE_CSV = os.path.join(EXPORTS_DIR, "valuation_model_timeline.csv")

TOP_500_GLOBAL_BRAND_TICKERS = {
    "AAPL", "MSFT", "GOOG", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "TSM", "ASML",
    "AVGO", "ORCL", "CRM", "SAP", "ADBE", "CSCO", "ACN", "IBM", "INTU", "TXN",
    "QCOM", "AMD", "AMAT", "LRCX", "KLAC", "MU", "ADI", "NXPI", "MPWR", "ON",
    "MCHP", "MRVL", "ARM", "SNPS", "CDNS", "ADSK", "NOW", "PANW", "FTNT", "CRWD",
    "WDAY", "PLTR", "SNOW", "DDOG", "TEAM", "ZS", "NET", "SHOP", "UBER", "ABNB",
    "BKNG", "EXPE", "EBAY", "DELL", "HPQ", "HPE", "STX", "WDC", "NTAP", "PSTG",
    "SONY", "ERIC", "NOK", "LOGI", "GRMN", "TER", "APH", "TEL", "GLW", "KEYS",
    "TRMB", "ZBRA", "JBL", "FLEX", "DOCU", "ZM", "SPOT", "NFLX", "APP", "TTD",
    "RAMP", "CARG", "FFIV", "UI", "BSY", "TYL", "ROP", "FICO", "GDDY", "AKAM",
    "CTSH", "INFY", "WIT", "G", "EXLS", "BR", "ADP", "PAYX", "PAYC", "DAY",
    "V", "MA", "AXP", "PYPL", "SQ", "FI", "FIS", "FISV", "GPN", "JPM",
    "BAC", "WFC", "C", "GS", "MS", "BLK", "BX", "APO", "KKR", "BAM",
    "BN", "ARES", "CG", "SCHW", "IBKR", "TROW", "BEN", "IVZ", "AMG", "APAM",
    "HLNE", "PJT", "LAZ", "EVR", "MC", "PIPR", "RJF", "SF", "JMP", "OPY",
    "HSBC", "RY", "TD", "BMO", "BNS", "CM", "UBS", "DB", "ING", "SAN",
    "BBVA", "BNP", "BCS", "LYG", "SMFG", "MUFG", "MFG", "ITUB", "BBD", "NU",
    "SPGI", "MCO", "MSCI", "ICE", "CME", "NDAQ", "CBOE", "FDS", "MORN", "TW",
    "MKTX", "VIRT", "BRK-A", "BRK-B", "CB", "PGR", "TRV", "ALL", "AIG", "MET",
    "PRU", "AFL", "HIG", "CINF", "WRB", "ACGL", "AJG", "MMC", "AON", "WTW",
    "BRO", "GL", "ESNT", "MTG", "RDN", "COF", "SYF", "DFS", "ALLY", "INDB",
    "WMT", "COST", "TGT", "HD", "LOW", "TJX", "ROST", "BURL", "ULTA", "NKE",
    "LULU", "RL", "TPR", "VFC", "PVH", "UAA", "DECK", "CROX", "SKX", "BOOT",
    "WSM", "RH", "BBY", "TSCO", "ORLY", "AZO", "GPC", "KMX", "AN", "PAG",
    "FIVE", "DG", "DLTR", "BJ", "KR", "ACI", "SYY", "USFD", "PFGC", "CASY",
    "MCD", "SBUX", "YUM", "CMG", "DPZ", "QSR", "DRI", "WEN", "PZZA", "TXRH",
    "WING", "SHAK", "CAVA", "BROS", "MAR", "HLT", "H", "IHG", "WH", "CHH",
    "RCL", "CCL", "NCLH", "DAL", "UAL", "AAL", "LUV", "ALK", "RYAAY",
    "PG", "KO", "PEP", "PM", "MO", "BTI", "UL", "NSRGY", "LRLCY", "EL",
    "CL", "KMB", "CHD", "CLX", "KVUE", "HLN", "MDLZ", "HSY", "KHC", "GIS",
    "K", "CPB", "CAG", "SJM", "HRL", "MKC", "TSN", "PPC", "MNST", "CELH",
    "KDP", "STZ", "BF-B", "TAP", "DEO", "BUD", "SAM", "COCO", "CART", "DASH",
    "BABA", "JD", "PDD", "MELI", "CPNG", "SE", "TM", "HMC", "F", "GM",
    "STLA", "RACE", "MBGAF", "BMWYY", "VWAGY", "POAHY", "GOLF", "YETI", "MAT", "HAS",
    "LLY", "NVO", "JNJ", "UNH", "ABBV", "MRK", "PFE", "AZN", "NVS", "RHHBY",
    "SNY", "GSK", "AMGN", "GILD", "VRTX", "REGN", "BMY", "BIIB", "MRNA", "ALNY",
    "TMO", "ABT", "DHR", "SYK", "ISRG", "BSX", "MDT", "EW", "BDX", "ZBH",
    "A", "IDXX", "DXCM", "PODD", "RMD", "STE", "WST", "HOLX", "ALGN", "TFX",
    "BAX", "RVTY", "WAT", "MTD", "IQV", "CRL", "MEDP", "ICLR", "LH", "DGX",
    "MCK", "COR", "CAH", "CI", "ELV", "HUM", "CVS", "HCA", "UHS", "THC",
    "DVA", "FMS", "DOCS", "VEEV", "HRMY", "HALO", "EXEL", "INCY", "UTHR", "JAZZ",
    "GE", "CAT", "DE", "HON", "ETN", "ITW", "EMR", "PH", "ROK", "AME",
    "DOV", "IR", "CMI", "PCAR", "OTIS", "CARR", "TT", "JCI", "LII", "WSO",
    "GWW", "FAST", "URI", "HRI", "CTAS", "ROL", "WM", "RSG", "WCN", "VLTO",
    "VRT", "XYL", "IEX", "GGG", "NDSN", "LECO", "SNA", "SWK", "TTC", "MIDD",
    "UNP", "CSX", "NSC", "CP", "CNI", "UPS", "FDX", "ODFL", "JBHT", "XPO",
    "SAIA", "KNX", "CHRW", "EXPD", "LMT", "RTX", "BA", "NOC", "GD",
    "LHX", "TDG", "HWM", "HEI", "TXT", "HII", "CW", "AXON", "LDOS", "BAH",
    "LIN", "APD", "SHW", "ECL", "PPG", "DD", "DOW", "LYB", "EMN", "IFF",
    "ALB", "CE", "RPM", "AXTA", "FUL", "BCPC", "NUE", "STLD", "RS", "CLF",
    "FCX", "SCCO", "BHP", "RIO", "VALE", "NEM", "GOLD", "B", "AEM", "WPM",
    "FNV", "AU", "KGC", "HMY", "AGI", "PAAS", "CDE", "HL", "BTG", "IAG",
    "VMC", "MLM", "CRH", "CSL", "OC", "BLDR", "MAS", "ALLE", "AOS", "AWI",
    "SSD", "WMS", "FIX", "EME", "PWR", "STRL", "ACM", "J", "STN", "TTEK",
    "XOM", "CVX", "SHEL", "TTE", "BP", "COP", "EOG", "SLB", "HAL", "BKR",
    "FTI", "MPC", "PSX", "VLO", "PARR", "OXY", "HES", "DVN", "FANG", "MGY",
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "PEG", "ED", "XEL",
    "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "SPG", "WELL", "DLR", "VICI",
    "ADC", "EXR", "AVB", "EQR", "INVH", "MAA", "ESS", "UDR", "CPT", "IRM",
    "DIS", "CMCSA", "WBD", "PARA", "FOX", "FOXA", "NYT", "NWS", "NWSA",
    "OMC", "IPG", "T", "VZ", "TMUS", "CHTR", "BCE", "TU", "RCI", "VOD",
    "RELX", "TRI", "WKL", "VRSK", "EFX", "TRU", "KFY", "RHI", "MAN",
}

TOP_500_BRAND_KEYWORDS = [
    "apple", "microsoft", "alphabet", "google", "amazon", "nvidia", "tsmc", "taiwan semiconductor",
    "asml", "broadcom", "oracle", "salesforce", "sap", "adobe", "cisco", "accenture",
    "texas instruments", "applied materials", "lam research", "kla", "cadence", "autodesk",
    "fortinet", "workday", "palantir", "sony", "uber", "airbnb", "ebay", "seagate",
    "western digital", "garmin", "teradyne", "amphenol", "te connectivity", "docusign",
    "applovin", "cargurus", "f5", "ubiquiti", "bentley systems", "tyler technologies",
    "automatic data", "paychex", "paycom", "broadridge", "genpact",
    "visa", "mastercard", "american express", "apollo", "brookfield", "interactive brokers",
    "t. rowe price", "raymond james", "piper sandler", "morningstar", "tradeweb", "cme group",
    "essent", "globe life", "hsbc", "ross stores", "ulta", "ralph lauren", "boot barn",
    "williams-sonoma", "domino's", "monster beverage", "eli lilly", "universal health",
    "agilent", "idexx", "dexcom", "insulet", "west pharmaceutical", "medpace", "stryker",
    "general electric", "caterpillar", "union pacific", "old dominion", "expeditors",
    "rockwell", "dover", "ametek", "graco", "nordson", "lincoln electric", "trane",
    "veralto", "vertiv", "ww grainger", "grainger", "united rentals", "cintas", "republic services",
    "howmet", "curtiss-wright", "linde", "eastman chemical", "southern copper", "barrick",
    "anglogold", "kinross", "pan american silver", "harmony gold", "alamos gold", "b2gold",
    "carlisle", "allegion", "armstrong", "simpson", "comfort systems", "stantec", "korn ferry",
    "technipfmc", "acushnet", "titleist",
]

TIER_ORDER = [
    "Micro-Cap (<$500M)",
    "Small-Cap ($500M-$5B)",
    "Mid-Cap ($5B-$50B)",
    "Large-Cap ($50B-$1T)",
    "Mega-Cap ($1T+)",
]

app = FastAPI(
    title="AlphaTerminal — Equity Research & Valuation Command Center",
    description="Decoupled Read-Only Analytics & Equation Simulation Engine over stock-sweeper",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_ro_conn() -> sqlite3.Connection:
    """Connects to ../stock-sweeper/market_data.db in strictly read-only URI mode."""
    uri = f"file:{DB_PATH}?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


def clean_num(val: Any, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def classify_tier(mcap_usd: Optional[float]) -> str:
    m = clean_num(mcap_usd, 0.0) or 0.0
    if m < 500_000_000:
        return "Micro-Cap (<$500M)"
    if m < 5_000_000_000:
        return "Small-Cap ($500M-$5B)"
    if m < 50_000_000_000:
        return "Mid-Cap ($5B-$50B)"
    if m < 1_000_000_000_000:
        return "Large-Cap ($50B-$1T)"
    return "Mega-Cap ($1T+)"


def sanitize_records(obj: Any) -> Any:
    """Recursively converts NaN/Inf/numpy types into clean JSON-safe Python primitives."""
    if isinstance(obj, dict):
        return {k: sanitize_records(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_records(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if pd.isna(obj):
        return None
    return obj


def read_csv_safe(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def compute_db_moat_pillars(
    ticker: str,
    company_name: str,
    ov_row: Dict[str, Any],
    hist_df: pd.DataFrame,
    share_dilution_pct: float = 0.0,
    known_total_moat: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Computes or reconstructs all 7 Qualitative Moat Pillars (100 pts) from read-only DB data
    so any of the 204 compounders (or any of the 8,768 DB tickers) has an exact 7-pillar breakdown.
    """
    roic = clean_num(ov_row.get("roic"), 0.10) or 0.10
    op_margin = clean_num(ov_row.get("operating_margins"), 0.12) or 0.12
    gross_margin = clean_num(ov_row.get("gross_margins"))
    rev_growth = clean_num(ov_row.get("revenue_growth"), 0.08) or 0.08
    fcf = clean_num(ov_row.get("free_cash_flow"), 1.0) or 1.0

    # Pillar 3 (15 pts): Capital Allocation & ROIC
    annual_roics = []
    if not hist_df.empty:
        for _, r in hist_df.sort_values("year", ascending=True).iterrows():
            ni = clean_num(r.get("net_income"))
            ocf = clean_num(r.get("operating_cash_flow"))
            ta = clean_num(r.get("total_assets"))
            cl = clean_num(r.get("current_liabilities"), 0.0) or 0.0
            num = ni if (ni is not None and ni > 0) else ocf
            if num is not None and ta is not None and (ta - cl) > 0:
                annual_roics.append(num / (ta - cl))
    is_stable = True
    if len(annual_roics) >= 2:
        early_med = float(np.median(annual_roics[: max(1, len(annual_roics) // 2)]))
        late_med = float(np.median(annual_roics[len(annual_roics) // 2 :]))
        is_stable = (late_med >= early_med * 0.90) or (roic >= early_med * 0.90)
    if roic >= 0.12 and is_stable:
        p3 = 15.0
    elif roic >= 0.12:
        p3 = 12.0
    elif roic >= 0.10 and is_stable:
        p3 = 10.0
    else:
        p3 = 7.0

    # Pillar 4 (10 pts): Culture & Leadership
    base_app = 73.0
    if roic >= 0.18 and op_margin >= 0.20:
        base_app += 4.0
    elif roic >= 0.12 and op_margin >= 0.15:
        base_app += 2.0
    p4 = 10.0 if base_app >= 75.0 else (7.0 if base_app >= 68.0 else 4.0)

    # Pillar 5 (20 pts): Pricing Power (Gross Margin stability)
    gm_series = []
    if not hist_df.empty and "gross_profit" in hist_df.columns:
        for _, r in hist_df.sort_values("year", ascending=True).tail(5).iterrows():
            gp = clean_num(r.get("gross_profit"))
            rev = clean_num(r.get("revenue"))
            if gp is not None and rev is not None and rev > 0 and 0.0 < (gp / rev) < 0.98:
                gm_series.append(gp / rev)
    if gm_series:
        mean_gm = float(np.mean(gm_series))
        std_gm = float(np.std(gm_series, ddof=0)) if len(gm_series) >= 2 else 0.020
    else:
        mean_gm = gross_margin if (gross_margin is not None and gross_margin > 0) else min(0.85, op_margin + 0.15)
        std_gm = 0.022
    if mean_gm > 0.35 and std_gm < 0.025:
        p5 = 20.0
    elif mean_gm > 0.35 and std_gm < 0.050:
        p5 = 15.0
    elif mean_gm > 0.35:
        p5 = 11.0
    elif mean_gm > 0.25 and std_gm < 0.025:
        p5 = 13.0
    elif mean_gm > 0.25:
        p5 = 9.0
    else:
        p5 = 5.0

    # Pillar 6 (15 pts): SG&A Brand Leverage
    sga_ratios, sga_years = [], []
    if not hist_df.empty and "sga_expense" in hist_df.columns:
        for _, r in hist_df.sort_values("year", ascending=True).tail(5).iterrows():
            sga = clean_num(r.get("sga_expense"))
            rev = clean_num(r.get("revenue"))
            yr = clean_num(r.get("year"))
            if sga is not None and rev is not None and rev > 0 and yr is not None and 0.0 < (sga / rev) < 0.90:
                sga_ratios.append(sga / rev)
                sga_years.append(yr)
    if len(sga_ratios) >= 2:
        slope = float(np.polyfit(np.array(sga_years), np.array(sga_ratios), 1)[0])
        delta = sga_ratios[-1] - sga_ratios[0]
        if slope <= 0.003 or delta <= 0.005:
            p6 = 15.0
        elif slope <= 0.015:
            p6 = 10.0
        else:
            p6 = 4.0
    else:
        p6 = 10.0

    # Pillar 7 (15 pts): Brand Recognition & Self-Funding Discipline
    clean_t = str(ticker).upper().strip()
    clean_name = str(company_name or "").lower().strip()
    is_top_brand = clean_t in TOP_500_GLOBAL_BRAND_TICKERS or any(kw in clean_name for kw in TOP_500_BRAND_KEYWORDS)
    if is_top_brand:
        p7 = 15.0
    else:
        g_pts = 8.0 if (fcf > 0 and 0.10 <= rev_growth <= 0.28) else (5.5 if (fcf > 0 and rev_growth >= 0.05) else 0.0)
        d_pts = 7.0 if share_dilution_pct <= 0.0 else (5.5 if share_dilution_pct <= 1.2 else (3.0 if share_dilution_pct <= 2.5 else 0.0))
        p7 = round(g_pts + d_pts, 1)

    # Pillars 1 (15 pts) & 2 (10 pts): Form 4 Insider & CEO Ownership
    subtotal_3_to_7 = p3 + p4 + p5 + p6 + p7
    if known_total_moat is not None and known_total_moat > 0:
        rem = max(6.0, min(25.0, round(known_total_moat - subtotal_3_to_7, 1)))
        p2 = min(10.0, max(4.0, round(rem * 0.42, 1)))
        p1 = min(15.0, max(2.0, round(rem - p2, 1)))
        total_moat = round(known_total_moat, 1)
    else:
        p1 = 10.0
        p2 = 7.0
        total_moat = round(p1 + p2 + subtotal_3_to_7, 1)

    return {
        "Pillar 1: Form 4 Insider Alignment (15)": p1,
        "Pillar 2: CEO Ownership & Alignment (10)": p2,
        "Pillar 3: Capital Allocation & ROIC (15)": p3,
        "Pillar 4: Culture & Leadership (10)": p4,
        "Pillar 5: Pricing Power (20)": p5,
        "Pillar 6: SG&A Brand Leverage (15)": p6,
        "Pillar 7: Brand Recognition Index (15)": p7,
        "Total Moat Score (100)": total_moat,
    }


@app.get("/api/overview")
def get_overview():
    """Executive Command Center & Market Universe Pulse."""
    conn = get_ro_conn()
    ov_df = pd.read_sql_query(
        """
        SELECT ticker, company_name, sector, industry, market_cap, current_price,
               forward_pe, operating_margins, gross_margins, revenue_growth,
               earnings_growth, roic, free_cash_flow, current_ratio, debt_to_equity,
               beta, is_active
        FROM company_overview
        """,
        conn,
    )
    conn.close()

    fund_df = read_csv_safe(FUNDAMENTAL_CSV)
    qual_df = read_csv_safe(QUALITATIVE_CSV)
    mega_df = read_csv_safe(MEGA_CAP_CSV)
    moon_df = read_csv_safe(MOONSHOT_CSV)
    dual_df = read_csv_safe(DUAL_SURVIVOR_CSV)

    total_tickers = len(ov_df)
    active_df = ov_df[ov_df["is_active"] == 1].copy()
    active_df["market_cap_tier"] = active_df["market_cap"].apply(classify_tier)

    # Market Cap Tier Breakdown across all 4 stages
    tier_summary = []
    for tier in TIER_ORDER:
        act_c = int((active_df["market_cap_tier"] == tier).sum())
        comp_c = int((fund_df["Market Cap Tier"] == tier).sum()) if not fund_df.empty else 0
        moat_c = int((qual_df["Market Cap Tier"] == tier).sum()) if not qual_df.empty else 0
        moon_c = int((moon_df["Market Cap Tier"] == tier).sum()) if not moon_df.empty else 0
        tier_summary.append({
            "tier": tier,
            "active_universe": act_c,
            "compounder_shortlist": comp_c,
            "elite_moat_survivors": moat_c,
            "asymmetric_moonshots": moon_c,
            "compounder_pass_rate_pct": round((comp_c / act_c) * 100.0, 2) if act_c > 0 else 0.0,
            "moat_retention_rate_pct": round((moat_c / comp_c) * 100.0, 1) if comp_c > 0 else 0.0,
        })

    # Sector Breakdown
    sector_counts = (
        active_df.groupby("sector")
        .size()
        .reset_index(name="active_count")
        .sort_values("active_count", ascending=False)
    )
    comp_sec = fund_df.groupby("Sector").size().to_dict() if not fund_df.empty else {}
    moat_sec = qual_df.groupby("Sector").size().to_dict() if not qual_df.empty else {}
    moon_sec = moon_df.groupby("Sector").size().to_dict() if not moon_df.empty else {}

    sector_summary = []
    for _, r in sector_counts.iterrows():
        sec = str(r["sector"] or "Unknown")
        if not sec or sec == "None":
            continue
        sector_summary.append({
            "sector": sec,
            "active_universe": int(r["active_count"]),
            "compounder_shortlist": int(comp_sec.get(sec, 0)),
            "elite_moat_survivors": int(moat_sec.get(sec, 0)),
            "asymmetric_moonshots": int(moon_sec.get(sec, 0)),
        })

    # Build unified Risk/Reward Scatter Dataset (204 Compounders + 60 Moonshots)
    qual_set = set(qual_df["Ticker"].astype(str)) if not qual_df.empty else set()
    dual_set = set(dual_df["Ticker"].astype(str)) if not dual_df.empty else set()
    mega_set = set(mega_df["Ticker"].astype(str)) if not mega_df.empty else set()
    ov_lookup = {str(r["ticker"]): r for _, r in active_df.iterrows()}

    scatter_points = []
    seen_scatter = set()
    if not fund_df.empty:
        for _, r in fund_df.iterrows():
            t = str(r["Ticker"])
            seen_scatter.add(t)
            ov_r = ov_lookup.get(t, {})
            in_moat = t in qual_set
            in_dual = t in dual_set
            in_mega = t in mega_set
            badge = (
                "Dual-Survivor Unicorn"
                if in_dual
                else ("Mega-Cap Anchor ($1T+)" if in_mega else ("Elite Moat Compounder" if in_moat else "Compounder Shortlist"))
            )
            scatter_points.append({
                "ticker": t,
                "company_name": r.get("Company Name", t),
                "sector": r.get("Sector", "Unknown"),
                "industry": r.get("Industry", "Unknown"),
                "market_cap_b": clean_num(r.get("Market Cap ($B)"), 1.0),
                "market_cap_tier": r.get("Market Cap Tier", "Small-Cap ($500M-$5B)"),
                "current_price": clean_num(r.get("Current Price ($)")),
                "target_price_3y": clean_num(r.get("3Y Target Price ($)")),
                "target_price_5y": clean_num(r.get("5Y Target Price ($)")),
                "cagr_5y_pct": clean_num(r.get("5Y Projected CAGR (%)"), 0.0),
                "return_3y_pct": clean_num(r.get("3Y Projected Return (%)"), 0.0),
                "return_5y_pct": clean_num(r.get("5Y Projected Total Return (%)"), 0.0),
                "moat_score": clean_num(r.get("Total Moat Score (100)"), 65.0),
                "dilution_3y_pct": clean_num(r.get("3Y Share Dilution CAGR (%)"), 0.0),
                "roic_pct": round((clean_num(ov_r.get("roic"), 0.12) or 0.12) * 100.0, 1),
                "operating_margin_pct": round((clean_num(ov_r.get("operating_margins"), 0.15) or 0.15) * 100.0, 1),
                "revenue_growth_pct": round((clean_num(ov_r.get("revenue_growth"), 0.08) or 0.08) * 100.0, 1),
                "forward_pe": round(clean_num(ov_r.get("forward_pe"), 18.0) or 18.0, 1),
                "category": badge,
            })

    if not moon_df.empty:
        for _, r in moon_df.iterrows():
            t = str(r["Ticker"])
            if t in seen_scatter:
                continue
            ret_3y = clean_num(r.get("3Y Projected Return (%)"), 100.0) or 100.0
            implied_cagr = round(((1.0 + max(-0.5, ret_3y / 100.0)) ** (1.0 / 3.0) - 1.0) * 100.0, 2)
            scatter_points.append({
                "ticker": t,
                "company_name": r.get("Company Name", t),
                "sector": r.get("Sector", "Unknown"),
                "industry": r.get("Industry", "Unknown"),
                "market_cap_b": clean_num(r.get("Market Cap ($B)"), 1.0),
                "market_cap_tier": r.get("Market Cap Tier", "Small-Cap ($500M-$5B)"),
                "current_price": clean_num(r.get("Current Price ($)")),
                "target_price_3y": clean_num(r.get("3Y Inflection Target ($)")),
                "target_price_5y": None,
                "cagr_5y_pct": implied_cagr,
                "return_3y_pct": ret_3y,
                "return_5y_pct": None,
                "moat_score": clean_num(r.get("Moonshot Inflection Score (100)"), 75.0),
                "dilution_3y_pct": 0.0,
                "roic_pct": clean_num(r.get("ROIC (%)"), 0.0),
                "operating_margin_pct": clean_num(r.get("Operating Margin (%)"), 0.0),
                "revenue_growth_pct": clean_num(r.get("Revenue Growth (%)"), 30.0),
                "forward_pe": clean_num(r.get("Forward P/E"), 25.0),
                "category": "Asymmetric Moonshot",
            })

    return JSONResponse(
        content=sanitize_records({
            "kpis": {
                "total_tickers": total_tickers,
                "active_tickers": int(len(active_df)),
                "compounders_count": int(len(fund_df)),
                "elite_moat_count": int(len(qual_df)),
                "moonshots_count": int(len(moon_df)),
                "dual_survivors_count": int(len(dual_df)),
                "mega_caps_count": int(len(mega_df)),
                "median_compounder_cagr_pct": round(float(fund_df["5Y Projected CAGR (%)"].median()), 2) if not fund_df.empty else 0.0,
                "median_elite_moat_score": round(float(qual_df["Total Moat Score (100)"].median()), 1) if not qual_df.empty else 0.0,
                "median_moonshot_3y_return_pct": round(float(moon_df["3Y Projected Return (%)"].median()), 1) if not moon_df.empty else 0.0,
            },
            "tier_summary": tier_summary,
            "sector_summary": sector_summary,
            "scatter_points": scatter_points,
            "dual_survivors": dual_df.to_dict(orient="records") if not dual_df.empty else [],
            "top_compounders": qual_df.head(25).to_dict(orient="records") if not qual_df.empty else [],
            "top_moonshots": moon_df.head(20).to_dict(orient="records") if not moon_df.empty else [],
        })
    )


class ScreenerFilterPayload(BaseModel):
    active_only: bool = True
    min_market_cap_m: Optional[float] = 500.0
    max_market_cap_m: Optional[float] = None
    enable_market_cap: bool = True
    tiers: Optional[List[str]] = None

    enable_roic: bool = True
    min_roic_pct: float = 10.0

    enable_fcf_positive: bool = True

    enable_operating_margin: bool = True
    min_operating_margin_pct: float = 10.0
    max_operating_margin_pct: Optional[float] = None

    enable_gross_margin: bool = False
    min_gross_margin_pct: float = 25.0

    enable_revenue_growth: bool = True
    min_revenue_growth_pct: float = 5.0
    max_revenue_growth_pct: Optional[float] = None

    enable_earnings_growth: bool = True
    min_earnings_growth_pct: float = 5.0

    enable_forward_pe: bool = True
    min_forward_pe: float = 5.0
    max_forward_pe: Optional[float] = None

    enable_current_ratio: bool = True
    min_current_ratio: float = 0.5

    enable_debt_to_equity: bool = True
    max_debt_to_equity: float = 2.0
    allow_null_debt: bool = False

    enable_beta: bool = True
    min_beta: float = 0.7
    max_beta: Optional[float] = None

    enable_accel_rule: bool = False
    min_accel_pct: float = 30.0

    exclude_sectors: Optional[List[str]] = None
    include_sectors: Optional[List[str]] = None
    search_query: Optional[str] = None
    sort_by: str = "market_cap"
    sort_desc: bool = True
    limit: int = 500


@app.post("/api/screener")
def run_custom_screener(payload: ScreenerFilterPayload):
    """
    Live Custom Screener Sandbox ('What-If Filter Lab') across all 7,300+ active stocks in market_data.db.
    Computes step-by-step funnel waterfall counts and enriches matches with Moat/Valuation/Moonshot metadata.
    """
    conn = get_ro_conn()
    df = pd.read_sql_query(
        """
        SELECT ticker, company_name, sector, industry, market_cap, current_price,
               beta, current_ratio, debt_to_equity, operating_margins, gross_margins,
               earnings_growth, revenue_growth, forward_pe, free_cash_flow, roic,
               target_mean_price, finviz_eps_5y, yahoo_lt_growth, is_active
        FROM company_overview
        """,
        conn,
    )
    conn.close()

    df["market_cap_tier"] = df["market_cap"].apply(classify_tier)

    funnel = [{"stage": "Total Database Universe", "count": int(len(df)), "dropped": 0}]

    def apply_gate(curr_df: pd.DataFrame, label: str, mask: pd.Series) -> pd.DataFrame:
        before = len(curr_df)
        next_df = curr_df[mask].copy()
        after = len(next_df)
        funnel.append({
            "stage": label,
            "count": int(after),
            "dropped": int(before - after),
            "retention_pct": round((after / before) * 100.0, 1) if before > 0 else 0.0,
        })
        return next_df

    if payload.active_only:
        df = apply_gate(df, "Active Primary Listings", df["is_active"] == 1)

    if payload.enable_market_cap:
        mask = pd.Series(True, index=df.index)
        if payload.min_market_cap_m is not None:
            mask &= df["market_cap"].notna() & (df["market_cap"] >= payload.min_market_cap_m * 1e6)
        if payload.max_market_cap_m is not None and payload.max_market_cap_m > 0:
            mask &= df["market_cap"].notna() & (df["market_cap"] <= payload.max_market_cap_m * 1e6)
        if payload.tiers and len(payload.tiers) > 0:
            mask &= df["market_cap_tier"].isin(payload.tiers)
        df = apply_gate(df, "Market Cap & Size Tier", mask)

    if payload.include_sectors and len(payload.include_sectors) > 0:
        df = apply_gate(df, "Sector Inclusion Filter", df["sector"].isin(payload.include_sectors))
    if payload.exclude_sectors and len(payload.exclude_sectors) > 0:
        df = apply_gate(df, "Sector Exclusion Filter", ~df["sector"].isin(payload.exclude_sectors))

    if payload.enable_fcf_positive:
        df = apply_gate(df, "Positive Free Cash Flow (FCF > $0)", df["free_cash_flow"].notna() & (df["free_cash_flow"] > 0))

    if payload.enable_roic:
        thr = payload.min_roic_pct / 100.0
        df = apply_gate(df, f"ROIC >= {payload.min_roic_pct:.1f}%", df["roic"].notna() & (df["roic"] >= thr))

    if payload.enable_operating_margin:
        thr = payload.min_operating_margin_pct / 100.0
        mask = df["operating_margins"].notna() & (df["operating_margins"] >= thr)
        if payload.max_operating_margin_pct is not None:
            mask &= df["operating_margins"] <= (payload.max_operating_margin_pct / 100.0)
        df = apply_gate(df, f"Operating Margin >= {payload.min_operating_margin_pct:.1f}%", mask)

    if payload.enable_gross_margin:
        thr = payload.min_gross_margin_pct / 100.0
        eff_gm = df["gross_margins"].fillna(df["operating_margins"] + 0.15)
        df = apply_gate(df, f"Gross Margin >= {payload.min_gross_margin_pct:.1f}%", eff_gm.notna() & (eff_gm >= thr))

    if payload.enable_revenue_growth:
        thr = payload.min_revenue_growth_pct / 100.0
        mask = df["revenue_growth"].notna() & (df["revenue_growth"] >= thr)
        if payload.max_revenue_growth_pct is not None and payload.max_revenue_growth_pct > 0:
            mask &= df["revenue_growth"] <= (payload.max_revenue_growth_pct / 100.0)
        df = apply_gate(df, f"Revenue Growth >= {payload.min_revenue_growth_pct:.1f}%", mask)

    if payload.enable_earnings_growth:
        thr = payload.min_earnings_growth_pct / 100.0
        df = apply_gate(df, f"Earnings Growth >= {payload.min_earnings_growth_pct:.1f}%", df["earnings_growth"].notna() & (df["earnings_growth"] >= thr))

    if payload.enable_accel_rule:
        thr = payload.min_accel_pct / 100.0
        mask = (df["revenue_growth"].notna() & (df["revenue_growth"] >= thr)) | (
            df["earnings_growth"].notna() & (df["earnings_growth"] >= thr)
        )
        df = apply_gate(df, f"Torque Gate (RevG or EPSG >= {payload.min_accel_pct:.0f}%)", mask)

    if payload.enable_current_ratio:
        df = apply_gate(
            df,
            f"Current Ratio >= {payload.min_current_ratio:.2f}x",
            df["current_ratio"].notna() & (df["current_ratio"] >= payload.min_current_ratio),
        )

    if payload.enable_debt_to_equity:
        if payload.allow_null_debt:
            mask = df["debt_to_equity"].isna() | (df["debt_to_equity"] <= payload.max_debt_to_equity)
        else:
            mask = df["debt_to_equity"].notna() & (df["debt_to_equity"] <= payload.max_debt_to_equity)
        df = apply_gate(df, f"Debt / Equity <= {payload.max_debt_to_equity:.2f}x", mask)

    if payload.enable_forward_pe:
        mask = df["forward_pe"].notna() & (df["forward_pe"] >= payload.min_forward_pe)
        if payload.max_forward_pe is not None and payload.max_forward_pe > 0:
            mask &= df["forward_pe"] <= payload.max_forward_pe
        df = apply_gate(df, f"Forward P/E >= {payload.min_forward_pe:.1f}x", mask)

    if payload.enable_beta:
        mask = df["beta"].notna() & (df["beta"] >= payload.min_beta)
        if payload.max_beta is not None and payload.max_beta > 0:
            mask &= df["beta"] <= payload.max_beta
        df = apply_gate(df, f"Beta >= {payload.min_beta:.2f}", mask)

    if payload.search_query and payload.search_query.strip():
        q = payload.search_query.strip().lower()
        mask = df["ticker"].astype(str).str.lower().str.contains(q, na=False) | df["company_name"].astype(str).str.lower().str.contains(q, na=False)
        df = apply_gate(df, f"Search '{payload.search_query.strip()}'", mask)

    # Enrich surviving rows with known Moat, 5Y CAGR, Dilution, and Moonshot scores
    fund_df = read_csv_safe(FUNDAMENTAL_CSV)
    qual_df = read_csv_safe(QUALITATIVE_CSV)
    moon_df = read_csv_safe(MOONSHOT_CSV)
    dual_df = read_csv_safe(DUAL_SURVIVOR_CSV)

    fund_map = {str(r["Ticker"]): r for _, r in fund_df.iterrows()} if not fund_df.empty else {}
    qual_set = set(qual_df["Ticker"].astype(str)) if not qual_df.empty else set()
    moon_map = {str(r["Ticker"]): r for _, r in moon_df.iterrows()} if not moon_df.empty else {}
    dual_set = set(dual_df["Ticker"].astype(str)) if not dual_df.empty else set()

    df["market_cap_b"] = (df["market_cap"] / 1e9).round(2)
    df["roic_pct"] = (df["roic"] * 100.0).round(2)
    df["operating_margin_pct"] = (df["operating_margins"] * 100.0).round(2)
    df["gross_margin_pct"] = (df["gross_margins"] * 100.0).round(2)
    df["revenue_growth_pct"] = (df["revenue_growth"] * 100.0).round(2)
    df["earnings_growth_pct"] = (df["earnings_growth"] * 100.0).round(2)
    df["fcf_m"] = (df["free_cash_flow"] / 1e6).round(1)

    moat_scores, cagr_5y, target_5y, dilution_3y, moonshot_scores, badges = [], [], [], [], [], []
    for _, r in df.iterrows():
        t = str(r["ticker"])
        f_row = fund_map.get(t)
        m_row = moon_map.get(t)
        moat_scores.append(clean_num(f_row.get("Total Moat Score (100)")) if f_row is not None else (clean_num(m_row.get("Compounder Moat Score (100)")) if m_row is not None else None))
        cagr_5y.append(clean_num(f_row.get("5Y Projected CAGR (%)")) if f_row is not None else None)
        target_5y.append(clean_num(f_row.get("5Y Target Price ($)")) if f_row is not None else None)
        dilution_3y.append(clean_num(f_row.get("3Y Share Dilution CAGR (%)")) if f_row is not None else None)
        moonshot_scores.append(clean_num(m_row.get("Moonshot Inflection Score (100)")) if m_row is not None else None)
        if t in dual_set:
            badges.append("Dual-Survivor")
        elif t in qual_set:
            badges.append("Elite Moat")
        elif t in fund_map:
            badges.append("Compounder")
        elif t in moon_map:
            badges.append("Moonshot")
        else:
            badges.append("Custom Match")

    df["moat_score"] = moat_scores
    df["cagr_5y_pct"] = cagr_5y
    df["target_price_5y"] = target_5y
    df["dilution_3y_pct"] = dilution_3y
    df["moonshot_score"] = moonshot_scores
    df["pipeline_badge"] = badges

    sort_col = payload.sort_by if payload.sort_by in df.columns else "market_cap"
    df.sort_values(by=sort_col, ascending=not payload.sort_desc, inplace=True, na_position="last")

    tier_dist = [
        {"tier": t, "count": int((df["market_cap_tier"] == t).sum())}
        for t in TIER_ORDER
    ]
    sec_dist = (
        df.groupby("sector")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(12)
        .to_dict(orient="records")
    )

    summary_stats = {
        "total_survivors": int(len(df)),
        "median_roic_pct": round(float(df["roic_pct"].median()), 1) if not df["roic_pct"].dropna().empty else 0.0,
        "median_forward_pe": round(float(df["forward_pe"].median()), 1) if not df["forward_pe"].dropna().empty else 0.0,
        "median_rev_growth_pct": round(float(df["revenue_growth_pct"].median()), 1) if not df["revenue_growth_pct"].dropna().empty else 0.0,
        "median_op_margin_pct": round(float(df["operating_margin_pct"].median()), 1) if not df["operating_margin_pct"].dropna().empty else 0.0,
        "elite_moat_overlap": int((df["pipeline_badge"].isin(["Elite Moat", "Dual-Survivor"])).sum()),
        "moonshot_overlap": int((df["pipeline_badge"].isin(["Moonshot", "Dual-Survivor"])).sum()),
    }

    records = df.head(payload.limit).to_dict(orient="records")
    return JSONResponse(
        content=sanitize_records({
            "funnel": funnel,
            "tier_distribution": tier_dist,
            "sector_distribution": sec_dist,
            "summary_stats": summary_stats,
            "results": records,
        })
    )


@app.get("/api/moat-studio")
def get_moat_studio():
    """
    Returns all 204 shortlisted compounders with their complete 7-Pillar Moat breakdown,
    fundamental metrics, dilution CAGR, and 5Y target prices for live interactive re-weighting.
    """
    fund_df = read_csv_safe(FUNDAMENTAL_CSV)
    qual_df = read_csv_safe(QUALITATIVE_CSV)
    mega_df = read_csv_safe(MEGA_CAP_CSV)
    dual_df = read_csv_safe(DUAL_SURVIVOR_CSV)

    if fund_df.empty:
        return JSONResponse(content={"stocks": []})

    pillar_cols = [
        "Pillar 1: Form 4 Insider Alignment (15)",
        "Pillar 2: CEO Ownership & Alignment (10)",
        "Pillar 3: Capital Allocation & ROIC (15)",
        "Pillar 4: Culture & Leadership (10)",
        "Pillar 5: Pricing Power (20)",
        "Pillar 6: SG&A Brand Leverage (15)",
        "Pillar 7: Brand Recognition Index (15)",
    ]

    known_pillars: Dict[str, Dict[str, float]] = {}
    for src_df in (qual_df, mega_df):
        if not src_df.empty:
            for _, r in src_df.iterrows():
                t = str(r["Ticker"])
                known_pillars[t] = {c: clean_num(r.get(c), 0.0) or 0.0 for c in pillar_cols}

    tickers = fund_df["Ticker"].astype(str).tolist()
    placeholders = ",".join(["?"] * len(tickers))
    conn = get_ro_conn()
    ov_df = pd.read_sql_query(
        f"""
        SELECT ticker, market_cap, gross_margins, operating_margins, revenue_growth,
               earnings_growth, roic, free_cash_flow, forward_pe, debt_to_equity
        FROM company_overview
        WHERE ticker IN ({placeholders})
        """,
        conn,
        params=tickers,
    )
    fin_df = pd.read_sql_query(
        f"""
        SELECT ticker, year, revenue, gross_profit, sga_expense, net_income,
               net_income_margin, operating_cash_flow, free_cash_flow,
               total_assets, current_liabilities
        FROM financial_records
        WHERE ticker IN ({placeholders}) AND period_type = 'Historical'
        ORDER BY ticker ASC, year ASC
        """,
        conn,
        params=tickers,
    )
    conn.close()

    ov_map = {str(r["ticker"]): r.to_dict() for _, r in ov_df.iterrows()}
    fin_map = {str(t): grp.copy() for t, grp in fin_df.groupby("ticker")}
    qual_set = set(qual_df["Ticker"].astype(str)) if not qual_df.empty else set()
    dual_set = set(dual_df["Ticker"].astype(str)) if not dual_df.empty else set()
    mega_set = set(mega_df["Ticker"].astype(str)) if not mega_df.empty else set()

    out_rows = []
    for _, r in fund_df.iterrows():
        row_d = r.to_dict()
        t = str(row_d["Ticker"])
        ov_r = ov_map.get(t, {})
        sh_dil = clean_num(row_d.get("3Y Share Dilution CAGR (%)"), 0.0) or 0.0
        known_tot = clean_num(row_d.get("Total Moat Score (100)"))

        if t in known_pillars:
            for c, val in known_pillars[t].items():
                row_d[c] = val
        else:
            computed = compute_db_moat_pillars(
                t,
                str(row_d.get("Company Name", t)),
                ov_r,
                fin_map.get(t, pd.DataFrame()),
                share_dilution_pct=sh_dil,
                known_total_moat=known_tot,
            )
            row_d.update(computed)

        row_d["ROIC (%)"] = round((clean_num(ov_r.get("roic"), 0.12) or 0.12) * 100.0, 1)
        row_d["Operating Margin (%)"] = round((clean_num(ov_r.get("operating_margins"), 0.15) or 0.15) * 100.0, 1)
        gm_v = clean_num(ov_r.get("gross_margins"))
        row_d["Gross Margin (%)"] = round(gm_v * 100.0, 1) if gm_v is not None else round(row_d["Operating Margin (%)"] + 15.0, 1)
        row_d["Revenue Growth (%)"] = round((clean_num(ov_r.get("revenue_growth"), 0.08) or 0.08) * 100.0, 1)
        row_d["Forward P/E"] = round(clean_num(ov_r.get("forward_pe"), 18.0) or 18.0, 1)
        row_d["in_elite_moat"] = t in qual_set
        row_d["in_dual_survivor"] = t in dual_set
        row_d["in_mega_cap"] = t in mega_set
        out_rows.append(row_d)

    return JSONResponse(content=sanitize_records({"stocks": out_rows}))


def _compounded_growth_factor(annual_rate: float, steps: int, decay_rate: float = 0.88, hyper_threshold: float = 0.18) -> float:
    if steps <= 0:
        return 1.0
    factor = 1.0
    for s in range(1, steps + 1):
        if annual_rate > hyper_threshold:
            step_r = hyper_threshold + (annual_rate - hyper_threshold) * (decay_rate ** (s - 1))
        else:
            step_r = annual_rate
        factor *= (1.0 + step_r)
    return factor


@app.get("/api/company/{ticker}")
def get_company_deep_dive(ticker: str):
    """
    15-Year Valuation Time-Machine & 4-Method Equation Builder for ANY ticker in market_data.db.
    """
    clean_t = ticker.strip().upper()
    conn = get_ro_conn()
    ov_df = pd.read_sql_query("SELECT * FROM company_overview WHERE UPPER(ticker) = ?", conn, params=(clean_t,))
    if ov_df.empty:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Ticker '{clean_t}' not found in market_data.db")

    ov = ov_df.iloc[0].to_dict()
    fin_df = pd.read_sql_query(
        "SELECT * FROM financial_records WHERE UPPER(ticker) = ? ORDER BY year ASC, period_type ASC",
        conn,
        params=(clean_t,),
    )
    conn.close()

    # Check CSV leaderboards for pre-computed timeline, Moat, Moonshot, and Dual-Survivor data
    tl_df = read_csv_safe(TIMELINE_CSV)
    sub_tl = tl_df[tl_df["Ticker"].astype(str).str.upper() == clean_t].copy() if not tl_df.empty else pd.DataFrame()

    fund_df = read_csv_safe(FUNDAMENTAL_CSV)
    qual_df = read_csv_safe(QUALITATIVE_CSV)
    mega_df = read_csv_safe(MEGA_CAP_CSV)
    moon_df = read_csv_safe(MOONSHOT_CSV)
    dual_df = read_csv_safe(DUAL_SURVIVOR_CSV)

    f_row = fund_df[fund_df["Ticker"].astype(str).str.upper() == clean_t].iloc[0].to_dict() if (not fund_df.empty and (fund_df["Ticker"].astype(str).str.upper() == clean_t).any()) else None
    q_row = qual_df[qual_df["Ticker"].astype(str).str.upper() == clean_t].iloc[0].to_dict() if (not qual_df.empty and (qual_df["Ticker"].astype(str).str.upper() == clean_t).any()) else None
    mg_row = mega_df[mega_df["Ticker"].astype(str).str.upper() == clean_t].iloc[0].to_dict() if (not mega_df.empty and (mega_df["Ticker"].astype(str).str.upper() == clean_t).any()) else None
    mn_row = moon_df[moon_df["Ticker"].astype(str).str.upper() == clean_t].iloc[0].to_dict() if (not moon_df.empty and (moon_df["Ticker"].astype(str).str.upper() == clean_t).any()) else None
    dl_row = dual_df[dual_df["Ticker"].astype(str).str.upper() == clean_t].iloc[0].to_dict() if (not dual_df.empty and (dual_df["Ticker"].astype(str).str.upper() == clean_t).any()) else None

    hist_fin = fin_df[fin_df["period_type"] == "Historical"].sort_values("year", ascending=True) if not fin_df.empty else pd.DataFrame()
    sh_dilution_pct = clean_num(f_row.get("3Y Share Dilution CAGR (%)")) if f_row else 0.0
    if sh_dilution_pct is None:
        sh_dilution_pct = 0.0

    # Moat breakdown (from CSV if available, else computed from DB)
    if q_row is not None:
        moat_pillars = {k: q_row.get(k) for k in q_row.keys() if k.startswith("Pillar ") or k == "Total Moat Score (100)"}
    elif mg_row is not None:
        moat_pillars = {k: mg_row.get(k) for k in mg_row.keys() if k.startswith("Pillar ") or k == "Total Moat Score (100)"}
    else:
        known_tot = clean_num(f_row.get("Total Moat Score (100)")) if f_row else None
        moat_pillars = compute_db_moat_pillars(clean_t, ov.get("company_name", clean_t), ov, hist_fin, sh_dilution_pct, known_tot)

    # If ticker is not in valuation_model_timeline.csv (i.e., one of the other 8,564 tickers), build a dynamic 15-year timeline from financial_records + company_overview!
    current_year = 2026
    curr_price = clean_num(ov.get("current_price"), 50.0) or 50.0
    fwd_pe = clean_num(ov.get("forward_pe"), 18.0) or 18.0
    if fwd_pe <= 0:
        fwd_pe = 18.0

    if not sub_tl.empty:
        sub_tl.sort_values(by=["Year", "Period Type"], ascending=[True, True], inplace=True)
        timeline_rows = sub_tl.to_dict(orient="records")
        # Extract baseline equation parameters from the 2027 Projected row
        proj_2027 = sub_tl[(sub_tl["Year"] == current_year + 1) & (sub_tl["Period Type"] == "Projected")]
        proj_2031 = sub_tl[(sub_tl["Year"] == current_year + 5) & (sub_tl["Period Type"] == "Projected")]
        r27 = proj_2027.iloc[0].to_dict() if not proj_2027.empty else sub_tl.iloc[-1].to_dict()
        r31 = proj_2031.iloc[0].to_dict() if not proj_2031.empty else r27

        equation_defaults = {
            "current_price": curr_price,
            "base_2027_eps": clean_num(r27.get("M1: Projected EPS ($)") or r27.get("Diluted EPS ($)"), round(curr_price / fwd_pe, 2)),
            "base_2027_rev_m": clean_num(r27.get("M2: Projected Revenue ($M)") or r27.get("Revenue ($M)"), 1000.0),
            "base_shares_m": clean_num(r27.get("Shares Outstanding (M)"), 100.0),
            "target_2027_price": clean_num(r27.get("Target Price ($)"), round(curr_price * 1.10, 2)),
            "starting_pe_2027": clean_num(r27.get("Target P/E Multiple"), round(fwd_pe, 2)),
            "terminal_pe_2031": clean_num(r31.get("Target P/E Multiple"), round(fwd_pe * 0.9, 2)),
            "m1_eps_cagr_pct": clean_num(r27.get("Hist EPS CAGR (%)"), 10.0),
            "m2_rev_cagr_pct": clean_num(r27.get("Hist EPS CAGR (%)"), 10.0),
            "m2_net_margin_pct": clean_num(r27.get("Hist Net Margin (%)"), 15.0),
            "m3_yahoo_lt_pct": clean_num(r27.get("Yahoo LT Growth Rate (%)"), 12.0),
            "m4_finviz_5y_pct": clean_num(r27.get("Finviz EPS 5Y Rate (%)"), 12.0),
            "share_dilution_cagr_pct": clean_num(r27.get("3Y Share Dilution CAGR (%)"), 0.0),
        }
        # Compute exact M2 rev CAGR from 2027 -> 2028 M2 projected revenue if available
        proj_2028 = sub_tl[(sub_tl["Year"] == current_year + 2) & (sub_tl["Period Type"] == "Projected")]
        if not proj_2028.empty and equation_defaults["base_2027_rev_m"] and equation_defaults["base_2027_rev_m"] > 0:
            rev28 = clean_num(proj_2028.iloc[0].get("M2: Projected Revenue ($M)"))
            if rev28 and rev28 > 0:
                equation_defaults["m2_rev_cagr_pct"] = round(((rev28 / equation_defaults["base_2027_rev_m"]) - 1.0) * 100.0, 2)
    else:
        # Build synthetic 15-year timeline from financial_records for non-shortlist tickers
        rev_g = float(np.clip(clean_num(ov.get("revenue_growth"), 0.10) or 0.10, -0.25, 0.35))
        eps_g = float(np.clip(clean_num(ov.get("earnings_growth"), rev_g) or rev_g, -0.25, 0.35))
        finviz_g = float(np.clip(clean_num(ov.get("finviz_eps_5y"), eps_g) or eps_g, -0.25, 0.35))
        yahoo_g = float(np.clip(clean_num(ov.get("yahoo_lt_growth"), rev_g) or rev_g, -0.25, 0.35))
        net_m = float(np.clip(clean_num(ov.get("operating_margins"), 0.12) or 0.12, 0.03, 0.50))
        base_eps = round(curr_price / fwd_pe, 2) if fwd_pe > 0 else 2.50
        mcap = clean_num(ov.get("market_cap"), 1e9) or 1e9
        shares_m = round((mcap / curr_price) / 1e6, 2) if curr_price > 0 else 100.0
        base_rev_m = round((base_eps * shares_m) / max(0.05, net_m), 2)
        tgt_2027 = clean_num(ov.get("target_mean_price")) or round(curr_price * (1.0 + rev_g), 2)
        term_pe = round(max(12.0, min(35.0, fwd_pe * 0.90)), 2)

        equation_defaults = {
            "current_price": curr_price,
            "base_2027_eps": base_eps,
            "base_2027_rev_m": base_rev_m,
            "base_shares_m": shares_m,
            "target_2027_price": round(tgt_2027, 2),
            "starting_pe_2027": round(fwd_pe, 2),
            "terminal_pe_2031": term_pe,
            "m1_eps_cagr_pct": round(eps_g * 100.0, 2),
            "m2_rev_cagr_pct": round(rev_g * 100.0, 2),
            "m2_net_margin_pct": round(net_m * 100.0, 2),
            "m3_yahoo_lt_pct": round(yahoo_g * 100.0, 2),
            "m4_finviz_5y_pct": round(finviz_g * 100.0, 2),
            "share_dilution_cagr_pct": 0.0,
        }
        timeline_rows = []
        for _, r in fin_df.iterrows():
            timeline_rows.append({
                "Ticker": clean_t,
                "Company Name": ov.get("company_name", clean_t),
                "Sector": ov.get("sector", "Unknown"),
                "Industry": ov.get("industry", "Unknown"),
                "Year": int(r["year"]),
                "Period Type": r["period_type"],
                "Price ($)": clean_num(r.get("year_end_price")) or (curr_price if int(r["year"]) == current_year else None),
                "Revenue ($M)": round(clean_num(r.get("revenue"), 0.0) / 1e6, 2) if clean_num(r.get("revenue")) else None,
                "Net Income ($M)": round(clean_num(r.get("net_income"), 0.0) / 1e6, 2) if clean_num(r.get("net_income")) else None,
                "Net Profit Margin (%)": round(clean_num(r.get("net_income_margin"), 0.0) * 100.0, 2) if clean_num(r.get("net_income_margin")) else None,
                "Diluted EPS ($)": clean_num(r.get("eps_diluted")),
                "Shares Outstanding (M)": round(clean_num(r.get("shares_outstanding"), 0.0) / 1e6, 2) if clean_num(r.get("shares_outstanding")) else shares_m,
                "P/E Ratio": clean_num(r.get("pe_ratio")),
            })

    # Extract multi-year GAAP Gross Profit, SG&A, OCF, CapEx, FCF from financial_records
    gaap_history = []
    for _, r in hist_fin.iterrows():
        rev = clean_num(r.get("revenue"))
        gp = clean_num(r.get("gross_profit"))
        sga = clean_num(r.get("sga_expense"))
        ni = clean_num(r.get("net_income"))
        ocf = clean_num(r.get("operating_cash_flow"))
        capex = clean_num(r.get("capital_expenditures"))
        fcf = clean_num(r.get("free_cash_flow"))
        ta = clean_num(r.get("total_assets"))
        cl = clean_num(r.get("current_liabilities"), 0.0) or 0.0
        roic_yr = ((ni if (ni and ni > 0) else ocf) / (ta - cl) * 100.0) if (ta and (ta - cl) > 0 and (ni or ocf)) else None
        gaap_history.append({
            "year": int(r["year"]),
            "revenue_m": round(rev / 1e6, 2) if rev is not None else None,
            "gross_profit_m": round(gp / 1e6, 2) if gp is not None else None,
            "sga_expense_m": round(sga / 1e6, 2) if sga is not None else None,
            "net_income_m": round(ni / 1e6, 2) if ni is not None else None,
            "operating_cash_flow_m": round(ocf / 1e6, 2) if ocf is not None else None,
            "capex_m": round(abs(capex) / 1e6, 2) if capex is not None else None,
            "free_cash_flow_m": round(fcf / 1e6, 2) if fcf is not None else None,
            "gross_margin_pct": round((gp / rev) * 100.0, 2) if (gp is not None and rev and rev > 0) else None,
            "sga_to_rev_pct": round((sga / rev) * 100.0, 2) if (sga is not None and rev and rev > 0) else None,
            "net_margin_pct": round((ni / rev) * 100.0, 2) if (ni is not None and rev and rev > 0) else None,
            "roic_pct": round(roic_yr, 2) if roic_yr is not None else None,
            "shares_m": round(clean_num(r.get("shares_outstanding"), 0.0) / 1e6, 2) if clean_num(r.get("shares_outstanding")) else None,
            "eps_diluted": clean_num(r.get("eps_diluted")),
            "year_end_price": clean_num(r.get("year_end_price")),
        })

    return JSONResponse(
        content=sanitize_records({
            "ticker": clean_t,
            "overview": {
                **ov,
                "market_cap_b": round((clean_num(ov.get("market_cap"), 0.0) or 0.0) / 1e9, 2),
                "market_cap_tier": classify_tier(ov.get("market_cap")),
                "roic_pct": round((clean_num(ov.get("roic"), 0.0) or 0.0) * 100.0, 2),
                "operating_margin_pct": round((clean_num(ov.get("operating_margins"), 0.0) or 0.0) * 100.0, 2),
                "gross_margin_pct": round((clean_num(ov.get("gross_margins"), 0.0) or 0.0) * 100.0, 2) if clean_num(ov.get("gross_margins")) is not None else None,
                "revenue_growth_pct": round((clean_num(ov.get("revenue_growth"), 0.0) or 0.0) * 100.0, 2),
                "earnings_growth_pct": round((clean_num(ov.get("earnings_growth"), 0.0) or 0.0) * 100.0, 2) if clean_num(ov.get("earnings_growth")) is not None else None,
                "fcf_m": round((clean_num(ov.get("free_cash_flow"), 0.0) or 0.0) / 1e6, 1),
            },
            "leaderboard_summary": f_row,
            "moat_pillars": moat_pillars,
            "moonshot_summary": mn_row,
            "dual_survivor_summary": dl_row,
            "equation_defaults": equation_defaults,
            "gaap_history": gaap_history,
            "timeline": timeline_rows,
        })
    )


@app.get("/api/moonshots")
def get_moonshots():
    """Asymmetric 5x Moonshot Lab ($300M-$10B) + Dual-Survivor Overlap Log."""
    moon_df = read_csv_safe(MOONSHOT_CSV)
    dual_df = read_csv_safe(DUAL_SURVIVOR_CSV)
    return JSONResponse(
        content=sanitize_records({
            "moonshots": moon_df.to_dict(orient="records") if not moon_df.empty else [],
            "dual_survivors": dual_df.to_dict(orient="records") if not dual_df.empty else [],
        })
    )


@app.get("/api/mega-caps")
def get_mega_caps():
    """Mega-Cap ($1T+) Swing-Trade & Anchor Desk."""
    mega_df = read_csv_safe(MEGA_CAP_CSV)
    tl_df = read_csv_safe(TIMELINE_CSV)
    mega_tickers = mega_df["Ticker"].astype(str).tolist() if not mega_df.empty else []
    sub_tl = tl_df[tl_df["Ticker"].astype(str).isin(mega_tickers)] if not tl_df.empty else pd.DataFrame()
    return JSONResponse(
        content=sanitize_records({
            "mega_caps": mega_df.to_dict(orient="records") if not mega_df.empty else [],
            "timelines": sub_tl.to_dict(orient="records") if not sub_tl.empty else [],
        })
    )


@app.get("/api/search")
def search_tickers(q: str = Query("", min_length=1), limit: int = 25):
    """Instant global search across all 8,768 tickers in market_data.db with pipeline badges."""
    term = q.strip().lower()
    conn = get_ro_conn()
    df = pd.read_sql_query(
        """
        SELECT ticker, company_name, sector, industry, market_cap, current_price, forward_pe, roic, is_active
        FROM company_overview
        WHERE LOWER(ticker) LIKE ? OR LOWER(company_name) LIKE ?
        ORDER BY
            CASE WHEN LOWER(ticker) = ? THEN 0
                 WHEN LOWER(ticker) LIKE ? THEN 1
                 ELSE 2 END,
            market_cap DESC
        LIMIT ?
        """,
        conn,
        params=(f"%{term}%", f"%{term}%", term, f"{term}%", limit),
    )
    conn.close()

    fund_df = read_csv_safe(FUNDAMENTAL_CSV)
    qual_df = read_csv_safe(QUALITATIVE_CSV)
    moon_df = read_csv_safe(MOONSHOT_CSV)
    dual_df = read_csv_safe(DUAL_SURVIVOR_CSV)
    mega_df = read_csv_safe(MEGA_CAP_CSV)

    fund_set = set(fund_df["Ticker"].astype(str)) if not fund_df.empty else set()
    qual_set = set(qual_df["Ticker"].astype(str)) if not qual_df.empty else set()
    moon_set = set(moon_df["Ticker"].astype(str)) if not moon_df.empty else set()
    dual_set = set(dual_df["Ticker"].astype(str)) if not dual_df.empty else set()
    mega_set = set(mega_df["Ticker"].astype(str)) if not mega_df.empty else set()

    results = []
    for _, r in df.iterrows():
        t = str(r["ticker"])
        badges = []
        if t in dual_set:
            badges.append("Dual-Survivor")
        if t in mega_set:
            badges.append("Mega-Cap $1T+")
        if t in qual_set:
            badges.append("Elite Moat")
        elif t in fund_set:
            badges.append("Compounder")
        if t in moon_set and "Dual-Survivor" not in badges:
            badges.append("Moonshot")
        results.append({
            "ticker": t,
            "company_name": r.get("company_name") or t,
            "sector": r.get("sector") or "Unknown",
            "market_cap_b": round((clean_num(r.get("market_cap"), 0.0) or 0.0) / 1e9, 2),
            "current_price": clean_num(r.get("current_price")),
            "forward_pe": clean_num(r.get("forward_pe")),
            "roic_pct": round((clean_num(r.get("roic"), 0.0) or 0.0) * 100.0, 1) if clean_num(r.get("roic")) is not None else None,
            "badges": badges,
        })
    return JSONResponse(content=sanitize_records({"results": results}))


class ArenaPayload(BaseModel):
    tickers: List[str]


@app.post("/api/arena")
def compare_stocks_arena(payload: ArenaPayload):
    """Side-by-side Head-to-Head Stock Arena & Barbell Portfolio comparison."""
    clean_tickers = [t.strip().upper() for t in payload.tickers if t.strip()][:8]
    if not clean_tickers:
        return JSONResponse(content={"stocks": []})

    out = []
    for t in clean_tickers:
        try:
            resp = get_company_deep_dive(t)
            import json
            data = json.loads(resp.body.decode("utf-8"))
            out.append(data)
        except Exception:
            continue
    return JSONResponse(content=sanitize_records({"stocks": out}))


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
