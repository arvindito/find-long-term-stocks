import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup

from config import DB_NAME, EXPORT_DIR, FUNDAMENTAL_LEADERBOARD_CSV, QUALITATIVE_MOAT_CSV, MEGA_CAP_WATCH_CSV
from database import get_db_connection
from utils import clean_float, ensure_file_limits, open_file

ensure_file_limits()

# Built-in static set of Top 500 Global Brands (Tickers & Brand Name Roots)
TOP_500_GLOBAL_BRAND_TICKERS = {
    # Global Technology, Semiconductors & Enterprise Software
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
    # Global Financials, Payments, Asset Management & Exchanges
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
    # Global Consumer, Retail, Apparel, Food & Beverage, Hospitality
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
    # Global Healthcare, Pharma, Biotech & MedTech
    "LLY", "NVO", "JNJ", "UNH", "ABBV", "MRK", "PFE", "AZN", "NVS", "RHHBY",
    "SNY", "GSK", "AMGN", "GILD", "VRTX", "REGN", "BMY", "BIIB", "MRNA", "ALNY",
    "TMO", "ABT", "DHR", "SYK", "ISRG", "BSX", "MDT", "EW", "BDX", "ZBH",
    "A", "IDXX", "DXCM", "PODD", "RMD", "STE", "WST", "HOLX", "ALGN", "TFX",
    "BAX", "RVTY", "WAT", "MTD", "IQV", "CRL", "MEDP", "ICLR", "LH", "DGX",
    "MCK", "COR", "CAH", "CI", "ELV", "HUM", "CVS", "HCA", "UHS", "THC",
    "DVA", "FMS", "DOCS", "VEEV", "HRMY", "HALO", "EXEL", "INCY", "UTHR", "JAZZ",
    # Global Industrials, Aerospace, Defense, Logistics & Materials
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
    # Energy, Utilities & Real Estate Brands
    "XOM", "CVX", "SHEL", "TTE", "BP", "COP", "EOG", "SLB", "HAL", "BKR",
    "FTI", "MPC", "PSX", "VLO", "PARR", "OXY", "HES", "DVN", "FANG", "MGY",
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "PEG", "ED", "XEL",
    "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "SPG", "WELL", "DLR", "VICI",
    "ADC", "EXR", "AVB", "EQR", "INVH", "MAA", "ESS", "UDR", "CPT", "IRM",
    # Media, Telecom & Entertainment
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


def score_pillar_1_insider_alignment(ticker: str, yf_info: dict, yf_ticker_obj) -> tuple[float, str]:
    """
    Pillar 1 (15 pts): Form 4 Insider Alignment (via OpenInsider http://openinsider.com/screener?s={ticker}
    or yfinance insider transactions).
      - 15.0 pts: Net open-market insider buying (buy_usd > sell_usd and buy_count >= 1)
      - 12.5 pts: Active insider buying alongside routine selling (buy_usd >= 0.25 * sell_usd)
      - 10.0 pts: Zero outright dumping / neutral activity (no open-market sales)
      -  8.0 pts: Low routine selling (< $2.5M)
      -  5.0 pts: Moderate selling ($2.5M - $15M)
      -  2.0 pts: Heavy insider selling (>= $15M)
    """
    buy_usd = 0.0
    sell_usd = 0.0
    buy_count = 0
    sell_count = 0
    sourced = False

    try:
        url = f"http://openinsider.com/screener?s={ticker}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", {"class": "tinytable"})
            if table:
                sourced = True
                for tr in table.find_all("tr")[1:21]:
                    tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if len(tds) >= 12:
                        trade_type = tds[6]
                        raw_val = re.sub(r"[^0-9.\-]", "", tds[11])
                        val = abs(clean_float(raw_val, 0.0) or 0.0)
                        if "P - Purchase" in trade_type:
                            buy_usd += val
                            buy_count += 1
                        elif trade_type.startswith("S - Sale") and "OE" not in trade_type:
                            sell_usd += val
                            sell_count += 1
                        elif "S - Sale+OE" in trade_type:
                            sell_usd += val * 0.25
    except Exception:
        pass

    if not sourced and yf_ticker_obj is not None:
        try:
            ins_df = yf_ticker_obj.insider_transactions
            if isinstance(ins_df, pd.DataFrame) and not ins_df.empty:
                for _, row in ins_df.head(20).iterrows():
                    txt = str(row.get("Text", "") or row.get("Transaction", "")).lower()
                    val = abs(clean_float(row.get("Value"), 0.0) or 0.0)
                    if "purchase" in txt or "buy" in txt:
                        buy_usd += val
                        buy_count += 1
                    elif "sale" in txt or "sell" in txt:
                        if "option" in txt or "automatic" in txt:
                            sell_usd += val * 0.25
                        else:
                            sell_usd += val
                            sell_count += 1
        except Exception:
            pass

    if buy_count >= 1 and buy_usd > sell_usd:
        return 15.0, f"Net Insider Buying (Buy=${buy_usd/1e6:.2f}M, Sell=${sell_usd/1e6:.2f}M)"
    if buy_count >= 1 and buy_usd >= 0.25 * sell_usd:
        return 12.5, f"Active Buying w/ Sales (Buy=${buy_usd/1e6:.2f}M, Sell=${sell_usd/1e6:.2f}M)"
    if sell_usd == 0.0 and sell_count == 0:
        return 10.0, "Zero Dumping / Neutral Insider Activity"
    if sell_usd < 2_500_000:
        return 8.0, f"Low Routine Selling (Sell=${sell_usd/1e6:.2f}M)"
    if sell_usd < 15_000_000:
        return 5.0, f"Moderate Selling (Sell=${sell_usd/1e6:.2f}M)"
    return 2.0, f"Heavy Insider Selling (Sell=${sell_usd/1e6:.2f}M)"


def score_pillar_2_ceo_ownership(yf_info: dict, market_cap: float) -> tuple[float, str]:
    """
    Pillar 2 (10 pts): CEO Ownership & Alignment (via yfinance companyOfficers & heldPercentInsiders).
    Full pts (10) for CEO/insider equity > 0.5% or > $10M.
    """
    held_pct_insiders = clean_float(yf_info.get("heldPercentInsiders"), 0.0) or 0.0
    officers = yf_info.get("companyOfficers") or []

    ceo_equity_val = 0.0
    ceo_total_comp = 0.0
    for off in officers:
        if not isinstance(off, dict):
            continue
        title = str(off.get("title", "")).lower()
        unex = clean_float(off.get("unexercisedValue"), 0.0) or 0.0
        ex = clean_float(off.get("exercisedValue"), 0.0) or 0.0
        pay = clean_float(off.get("totalPay"), 0.0) or 0.0
        if any(k in title for k in ("ceo", "chief executive", "chairman", "founder", "president")):
            ceo_equity_val = max(ceo_equity_val, unex + ex)
            ceo_total_comp = max(ceo_total_comp, pay)

    insider_dollar_stake = (held_pct_insiders * market_cap) if (market_cap and market_cap > 0) else 0.0
    effective_ceo_equity = max(ceo_equity_val, insider_dollar_stake * 0.35)

    if held_pct_insiders >= 0.005 or effective_ceo_equity >= 10_000_000 or insider_dollar_stake >= 10_000_000:
        return 10.0, f"High Alignment (Insiders={held_pct_insiders*100:.2f}%, Stake=${max(effective_ceo_equity, insider_dollar_stake)/1e6:.1f}M)"
    if held_pct_insiders >= 0.001 or effective_ceo_equity >= 3_000_000 or ceo_total_comp >= 5_000_000:
        return 7.0, f"Moderate Alignment (Insiders={held_pct_insiders*100:.2f}%)"
    return 4.0, f"Low Insider Ownership (Insiders={held_pct_insiders*100:.2f}%)"


def score_pillar_3_roic_capital_allocation(roic: float, hist_df: pd.DataFrame) -> tuple[float, str]:
    """
    Pillar 3 (15 pts): Capital Allocation & ROIC (via market_data.db).
    Full pts (15) for current ROIC >= 12% and stable/expanding over trailing periods.
    """
    curr_roic = clean_float(roic, 0.10) or 0.10

    annual_roics = []
    if not hist_df.empty:
        for _, r in hist_df.sort_values("year", ascending=True).iterrows():
            ni = clean_float(r.get("net_income"))
            ocf = clean_float(r.get("operating_cash_flow"))
            ta = clean_float(r.get("total_assets"))
            cl = clean_float(r.get("current_liabilities"), 0.0) or 0.0
            num = ni if (ni is not None and ni > 0) else ocf
            if num is not None and ta is not None and (ta - cl) > 0:
                annual_roics.append(num / (ta - cl))

    is_stable_or_expanding = True
    if len(annual_roics) >= 2:
        early_med = float(np.median(annual_roics[: max(1, len(annual_roics) // 2)]))
        late_med = float(np.median(annual_roics[len(annual_roics) // 2 :]))
        is_stable_or_expanding = (late_med >= early_med * 0.90) or (curr_roic >= early_med * 0.90)

    if curr_roic >= 0.12 and is_stable_or_expanding:
        return 15.0, f"ROIC {curr_roic*100:.1f}% (Stable/Expanding)"
    if curr_roic >= 0.12:
        return 12.0, f"ROIC {curr_roic*100:.1f}% (Moderating)"
    if curr_roic >= 0.10 and is_stable_or_expanding:
        return 10.0, f"ROIC {curr_roic*100:.1f}% (Expanding)"
    return 7.0, f"ROIC {curr_roic*100:.1f}%"


def score_pillar_4_culture_leadership(yf_info: dict, roic: float, op_margin: float) -> tuple[float, str]:
    """
    Pillar 4 (10 pts): Culture & Leadership (via governance & leadership approval scores).
    Full pts (10) for implied approval >= 75%.
    """
    overall_risk = clean_float(yf_info.get("overallRisk"))
    board_risk = clean_float(yf_info.get("boardRisk"))
    comp_risk = clean_float(yf_info.get("compensationRisk"))
    audit_risk = clean_float(yf_info.get("auditRisk"))

    risk_scores = [x for x in (overall_risk, board_risk, comp_risk, audit_risk) if x is not None]
    avg_gov_risk = float(np.mean(risk_scores)) if risk_scores else None

    base_approval = 73.0
    if avg_gov_risk is not None:
        base_approval = 90.0 - (avg_gov_risk * 3.0)
    if (roic or 0) >= 0.18 and (op_margin or 0) >= 0.20:
        base_approval += 4.0
    elif (roic or 0) >= 0.12 and (op_margin or 0) >= 0.15:
        base_approval += 2.0

    implied_approval = float(np.clip(base_approval, 55.0, 95.0))

    if implied_approval >= 75.0:
        return 10.0, f"Approval ~{implied_approval:.0f}% (>=75%)"
    if implied_approval >= 68.0:
        return 7.0, f"Approval ~{implied_approval:.0f}%"
    return 4.0, f"Approval ~{implied_approval:.0f}%"


def score_pillar_5_pricing_power(
    op_margin: float, hist_df: pd.DataFrame, yf_info: dict, yf_inc_stmt: pd.DataFrame
) -> tuple[float, str]:
    """
    Pillar 5 (20 pts): Pricing Power (via GAAP Gross Margin series in market_data.db + yfinance).
    Full pts (20) for 5Y Gross Margin > 35% with standard deviation < 2.5%.
    """
    gm_series = []

    # 1. Extract multi-year Gross Margin from market_data.db (if gross_profit populated)
    if not hist_df.empty and "gross_profit" in hist_df.columns:
        recent_hist = hist_df.sort_values("year", ascending=True).tail(5)
        for _, r in recent_hist.iterrows():
            gp = clean_float(r.get("gross_profit"))
            rev = clean_float(r.get("revenue"))
            if gp is not None and rev is not None and rev > 0 and 0.0 < (gp / rev) < 0.98:
                gm_series.append(gp / rev)

    # 2. Supplement with yfinance income statement Gross Profit / Total Revenue if needed
    if len(gm_series) < 2 and isinstance(yf_inc_stmt, pd.DataFrame) and not yf_inc_stmt.empty:
        for col in yf_inc_stmt.columns[:5]:
            gp_val = None
            rev_val = None
            for gp_key in ("Gross Profit",):
                if gp_key in yf_inc_stmt.index:
                    gp_val = clean_float(yf_inc_stmt.loc[gp_key, col])
                    break
            for rev_key in ("Total Revenue", "Operating Revenue"):
                if rev_key in yf_inc_stmt.index:
                    rev_val = clean_float(yf_inc_stmt.loc[rev_key, col])
                    break
            if gp_val is not None and rev_val is not None and rev_val > 0 and 0.0 < (gp_val / rev_val) < 0.98:
                gm_series.append(gp_val / rev_val)

    yf_gross = clean_float(yf_info.get("grossMargins"))
    ov_op_margin = clean_float(op_margin, 0.15) or 0.15

    if gm_series:
        mean_gm = float(np.mean(gm_series))
        std_gm = float(np.std(gm_series, ddof=0)) if len(gm_series) >= 2 else 0.020
    else:
        mean_gm = yf_gross if (yf_gross is not None and yf_gross > 0) else min(0.85, ov_op_margin + 0.15)
        # Fallback std from net_income_margin in market_data.db
        nm_series = [
            clean_float(x)
            for x in hist_df.tail(5).get("net_income_margin", [])
            if clean_float(x) is not None and -0.5 < clean_float(x) < 0.95
        ]
        std_gm = float(np.std(nm_series, ddof=0)) if len(nm_series) >= 2 else 0.022

    if mean_gm > 0.35 and std_gm < 0.025:
        return 20.0, f"5Y GM {mean_gm*100:.1f}%, StdDev {std_gm*100:.2f}%"
    if mean_gm > 0.35 and std_gm < 0.050:
        return 15.0, f"5Y GM {mean_gm*100:.1f}%, StdDev {std_gm*100:.2f}%"
    if mean_gm > 0.35:
        return 11.0, f"5Y GM {mean_gm*100:.1f}%, StdDev {std_gm*100:.2f}%"
    if mean_gm > 0.25 and std_gm < 0.025:
        return 13.0, f"5Y GM {mean_gm*100:.1f}%, StdDev {std_gm*100:.2f}%"
    if mean_gm > 0.25:
        return 9.0, f"5Y GM {mean_gm*100:.1f}%, StdDev {std_gm*100:.2f}%"
    return 5.0, f"5Y GM {mean_gm*100:.1f}%, StdDev {std_gm*100:.2f}%"


def score_pillar_6_sga_leverage(hist_df: pd.DataFrame, yf_inc_stmt: pd.DataFrame) -> tuple[float, str]:
    """
    Pillar 6 (15 pts): SG&A Brand Leverage (via GAAP SG&A-to-Revenue in market_data.db + yfinance).
    Full pts (15) for flat or declining SG&A-to-revenue ratio over trailing 3-5 years.
    """
    sga_ratios = []
    years = []

    # 1. Check GAAP sga_expense / revenue in market_data.db
    if not hist_df.empty and "sga_expense" in hist_df.columns:
        recent = hist_df.sort_values("year", ascending=True).tail(5)
        for _, r in recent.iterrows():
            sga = clean_float(r.get("sga_expense"))
            rev = clean_float(r.get("revenue"))
            yr = clean_float(r.get("year"))
            if sga is not None and rev is not None and rev > 0 and yr is not None and 0.0 < (sga / rev) < 0.90:
                sga_ratios.append(sga / rev)
                years.append(yr)

    # 2. Supplement with yfinance income statement Selling General And Administration / Total Revenue
    if len(sga_ratios) < 2 and isinstance(yf_inc_stmt, pd.DataFrame) and not yf_inc_stmt.empty:
        sga_ratios = []
        years = []
        cols_asc = list(reversed(list(yf_inc_stmt.columns[:5])))
        for col in cols_asc:
            try:
                yr = float(pd.to_datetime(col).year)
            except Exception:
                continue
            sga_val = None
            rev_val = None
            for k in ("Selling General And Administration", "General And Administrative Expense"):
                if k in yf_inc_stmt.index:
                    sga_val = clean_float(yf_inc_stmt.loc[k, col])
                    if sga_val is not None:
                        break
            for k in ("Total Revenue", "Operating Revenue"):
                if k in yf_inc_stmt.index:
                    rev_val = clean_float(yf_inc_stmt.loc[k, col])
                    if rev_val is not None:
                        break
            if sga_val is not None and rev_val is not None and rev_val > 0 and 0.0 < (sga_val / rev_val) < 0.90:
                sga_ratios.append(sga_val / rev_val)
                years.append(yr)

    # 3. Fallback to total operating/overhead cost ratio in market_data.db
    if len(sga_ratios) < 2 and not hist_df.empty:
        recent = hist_df.sort_values("year", ascending=True).tail(5)
        for _, r in recent.iterrows():
            rev = clean_float(r.get("revenue"))
            ni = clean_float(r.get("net_income"))
            yr = clean_float(r.get("year"))
            if rev and rev > 0 and ni is not None and yr is not None:
                overhead_ratio = max(0.05, min(0.98, 1.0 - (ni / rev)))
                sga_ratios.append(overhead_ratio)
                years.append(yr)

    if len(sga_ratios) < 2:
        return 10.0, "Insufficient Multi-Year SG&A History"

    x = np.array(years, dtype=float)
    y = np.array(sga_ratios, dtype=float)
    slope = float(np.polyfit(x, y, 1)[0]) if len(x) >= 2 else 0.0
    delta = y[-1] - y[0]

    if slope <= 0.003 or delta <= 0.005:
        return 15.0, f"Flat/Declining SG&A Ratio (Slope={slope*100:+.2f}%/yr)"
    if slope <= 0.015:
        return 10.0, f"Slight SG&A Drift (Slope={slope*100:+.2f}%/yr)"
    return 4.0, f"Rising SG&A Ratio (Slope={slope*100:+.2f}%/yr)"


def score_pillar_7_brand_and_tier_moat(
    ticker: str,
    company_name: str,
    market_cap_usd: float,
    rev_growth: float,
    fcf: float,
    share_dilution_cagr_pct: float,
) -> tuple[float, str]:
    """
    Pillar 7 (15 pts): Brand Recognition & Self-Funding Compounder Index (Option B).
    Applied uniformly across ALL market-cap tiers:
      - If recognized in Top 500 Global Brands: Full 15.0 pts.
      - Otherwise: Scored up to 15.0 pts on Self-Funding Growth (10%-28% revenue growth
        + FCF > 0, up to 8 pts) and Share Dilution Discipline (3Y Share CAGR <= +1.2%, up to 7 pts).
    """
    clean_t = str(ticker).upper().strip()
    clean_name = str(company_name).lower().strip()

    if clean_t in TOP_500_GLOBAL_BRAND_TICKERS:
        return 15.0, "Recognized Top 500 Global Brand (Ticker)"
    for kw in TOP_500_BRAND_KEYWORDS:
        if kw in clean_name:
            return 15.0, f"Recognized Top 500 Global Brand ({kw.title()})"

    rg = clean_float(rev_growth, 0.08) or 0.08
    fcf_val = clean_float(fcf, 1.0) or 1.0
    sh_cagr = clean_float(share_dilution_cagr_pct, 0.0) or 0.0

    growth_pts = 0.0
    if fcf_val > 0:
        if 0.10 <= rg <= 0.28:
            growth_pts = 8.0
        elif rg > 0.28 or rg >= 0.05:
            growth_pts = 5.5

    dilution_pts = 0.0
    if sh_cagr <= 0.0:
        dilution_pts = 7.0
    elif sh_cagr <= 1.2:
        dilution_pts = 5.5
    elif sh_cagr <= 2.5:
        dilution_pts = 3.0

    tot = round(growth_pts + dilution_pts, 1)
    return tot, f"Self-Funding Compounder Discipline ({tot}/15: RevG={rg*100:.1f}%, ShareCAGR={sh_cagr:+.2f}%)"


def _fetch_live_qualitative_signals(ticker: str, need_financials: bool = False) -> tuple[str, dict, object, pd.DataFrame]:
    try:
        yt = yf.Ticker(ticker)
        info = yt.info or {}
        inc = pd.DataFrame()
        if need_financials:
            try:
                inc = yt.financials
                if not isinstance(inc, pd.DataFrame):
                    inc = pd.DataFrame()
            except Exception:
                inc = pd.DataFrame()
        return ticker, info, yt, inc
    except Exception:
        return ticker, {}, None, pd.DataFrame()


def run_qualitative_scorer(
    min_moat_score: float = 70.0,
    max_share_dilution_pct: float = 3.5,
    min_projected_cagr_pct: float = 8.0,
):
    if not os.path.exists(FUNDAMENTAL_LEADERBOARD_CSV):
        print(f"Error: {FUNDAMENTAL_LEADERBOARD_CSV} not found. Run generate_summary.py first.")
        return None

    leaderboard_df = pd.read_csv(FUNDAMENTAL_LEADERBOARD_CSV)
    if leaderboard_df.empty:
        print(f"Warning: {FUNDAMENTAL_LEADERBOARD_CSV} is empty.")
        return None

    tickers = leaderboard_df["Ticker"].astype(str).tolist()
    print(f"Scoring {len(tickers)} shortlisted stocks across the 7 Qualitative Moat Pillars...")

    conn = get_db_connection(DB_NAME)
    placeholders = ",".join(["?"] * len(tickers))

    ov_df = pd.read_sql_query(
        f"SELECT ticker, market_cap, gross_margins, operating_margins, revenue_growth, roic, free_cash_flow FROM company_overview WHERE ticker IN ({placeholders})",
        conn,
        params=tickers,
    )
    ov_map = {r["ticker"]: r for _, r in ov_df.iterrows()}

    fin_df = pd.read_sql_query(
        f"""
        SELECT ticker, year, revenue, gross_profit, sga_expense, net_income, net_income_margin,
               operating_cash_flow, free_cash_flow, total_assets, current_liabilities
        FROM financial_records
        WHERE ticker IN ({placeholders}) AND period_type = 'Historical'
        ORDER BY ticker ASC, year ASC
        """,
        conn,
        params=tickers,
    )

    fin_map = {t: grp.copy() for t, grp in fin_df.groupby("ticker")}

    yf_info_map = {}
    yf_obj_map = {}
    yf_inc_map = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for t in tickers:
            t_hist = fin_map.get(t, pd.DataFrame())
            has_gp = not t_hist.empty and "gross_profit" in t_hist.columns and t_hist["gross_profit"].notna().sum() >= 2
            has_sga = not t_hist.empty and "sga_expense" in t_hist.columns and t_hist["sga_expense"].notna().sum() >= 2
            futures[executor.submit(_fetch_live_qualitative_signals, t, not (has_gp and has_sga))] = t
        for future in as_completed(futures):
            t_sym, info_dict, yt_obj, inc_df = future.result()
            yf_info_map[t_sym] = info_dict
            yf_obj_map[t_sym] = yt_obj
            yf_inc_map[t_sym] = inc_df

    # Backfill newly fetched GAAP gross_profit and sga_expense into market_data.db
    cur = conn.cursor()
    for t_sym, inc_df in yf_inc_map.items():
        gm_info = clean_float(yf_info_map.get(t_sym, {}).get("grossMargins"))
        if gm_info is not None:
            cur.execute(
                "UPDATE company_overview SET gross_margins = COALESCE(?, gross_margins) WHERE ticker = ?",
                (gm_info, t_sym),
            )
        if isinstance(inc_df, pd.DataFrame) and not inc_df.empty:
            for col in inc_df.columns:
                try:
                    yr = int(pd.to_datetime(col).year)
                except Exception:
                    continue
                gp_val = clean_float(inc_df.loc["Gross Profit", col]) if "Gross Profit" in inc_df.index else None
                sga_val = None
                for k in ("Selling General And Administration", "General And Administrative Expense"):
                    if k in inc_df.index:
                        sga_val = clean_float(inc_df.loc[k, col])
                        if sga_val is not None:
                            break
                if gp_val is not None or sga_val is not None:
                    cur.execute(
                        """
                        UPDATE financial_records
                        SET gross_profit = COALESCE(?, gross_profit),
                            sga_expense = COALESCE(?, sga_expense)
                        WHERE ticker = ? AND year = ? AND period_type = 'Historical'
                        """,
                        (gp_val, sga_val, t_sym, yr),
                    )
    conn.commit()
    conn.close()

    def _score_single_row(row_dict):
        t = str(row_dict["Ticker"])
        c_name = str(row_dict.get("Company Name", t))
        ov = ov_map.get(t, {})
        hist_sub = fin_map.get(t, pd.DataFrame())
        info = yf_info_map.get(t, {})
        yt_obj = yf_obj_map.get(t)
        inc_df = yf_inc_map.get(t, pd.DataFrame())

        m_cap = clean_float(ov.get("market_cap")) or clean_float(info.get("marketCap"), 1e9)
        roic_val = clean_float(ov.get("roic"), 0.12)
        op_margin_val = clean_float(ov.get("operating_margins")) or clean_float(info.get("operatingMargins"), 0.15)
        rev_growth_val = clean_float(ov.get("revenue_growth")) or clean_float(info.get("revenueGrowth"), 0.08)
        fcf_val = clean_float(ov.get("free_cash_flow"), 1.0)
        sh_dilution_pct = clean_float(row_dict.get("3Y Share Dilution CAGR (%)"), 0.0)

        p1_score, _ = score_pillar_1_insider_alignment(t, info, yt_obj)
        p2_score, _ = score_pillar_2_ceo_ownership(info, m_cap)
        p3_score, _ = score_pillar_3_roic_capital_allocation(roic_val, hist_sub)
        p4_score, _ = score_pillar_4_culture_leadership(info, roic_val, op_margin_val)
        p5_score, _ = score_pillar_5_pricing_power(op_margin_val, hist_sub, info, inc_df)
        p6_score, _ = score_pillar_6_sga_leverage(hist_sub, inc_df)
        p7_score, _ = score_pillar_7_brand_and_tier_moat(t, c_name, m_cap, rev_growth_val, fcf_val, sh_dilution_pct)

        total_moat = round(p1_score + p2_score + p3_score + p4_score + p5_score + p6_score + p7_score, 2)

        out = dict(row_dict)
        out["Pillar 1: Form 4 Insider Alignment (15)"] = round(p1_score, 1)
        out["Pillar 2: CEO Ownership & Alignment (10)"] = round(p2_score, 1)
        out["Pillar 3: Capital Allocation & ROIC (15)"] = round(p3_score, 1)
        out["Pillar 4: Culture & Leadership (10)"] = round(p4_score, 1)
        out["Pillar 5: Pricing Power (20)"] = round(p5_score, 1)
        out["Pillar 6: SG&A Brand Leverage (15)"] = round(p6_score, 1)
        out["Pillar 7: Brand Recognition Index (15)"] = round(p7_score, 1)
        out["Total Moat Score (100)"] = total_moat
        return out

    scored_rows = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        row_dicts = [r.to_dict() for _, r in leaderboard_df.iterrows()]
        for res in executor.map(_score_single_row, row_dicts):
            scored_rows.append(res)

    scored_df = pd.DataFrame(scored_rows)
    # Persist Total Moat Score (100) back to fundamental_screener_leaderboard.csv so all 204 stocks retain their Moat Score
    try:
        leaderboard_df["Total Moat Score (100)"] = scored_df["Total Moat Score (100)"].values
        leaderboard_df.to_csv(FUNDAMENTAL_LEADERBOARD_CSV, index=False)
    except Exception:
        pass

    # Uniform compounder gates across ALL market-cap tiers (no special exemptions)
    moat_ok = scored_df["Total Moat Score (100)"] >= min_moat_score
    dilution_ok = scored_df.get("3Y Share Dilution CAGR (%)", pd.Series(0.0, index=scored_df.index)).fillna(0.0) <= max_share_dilution_pct
    cagr_ok = scored_df.get("5Y Projected CAGR (%)", pd.Series(10.0, index=scored_df.index)).fillna(0.0) >= min_projected_cagr_pct

    qualified_df = scored_df[moat_ok & dilution_ok & cagr_ok].copy()

    sort_cols = ["Total Moat Score (100)"]
    ascending_flags = [False]
    if "5Y Projected Total Return (%)" in qualified_df.columns:
        sort_cols.append("5Y Projected Total Return (%)")
        ascending_flags.append(False)

    qualified_df.sort_values(by=sort_cols, ascending=ascending_flags, inplace=True)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    qualified_df.to_csv(QUALITATIVE_MOAT_CSV, index=False)

    # Also export a dedicated Mega-Cap ($1T+) Watch Leaderboard CSV for swing-trading & anchor reference
    is_mega_cap = scored_df.get("Market Cap Tier", pd.Series(dtype=str)) == "Mega-Cap ($1T+)"
    mega_df = scored_df[is_mega_cap].copy()
    if not mega_df.empty:
        mega_df.sort_values(by=sort_cols, ascending=ascending_flags, inplace=True)
        mega_df.to_csv(MEGA_CAP_WATCH_CSV, index=False)
        print(f"Successfully generated Mega-Cap ($1T+) Watch Leaderboard ({len(mega_df)} mega-caps) at:")
        print(f"  └─ {MEGA_CAP_WATCH_CSV}")

    print(
        f"\nSuccessfully generated Qualitative Moat Leaderboard "
        f"({len(qualified_df)}/{len(scored_df)} elite compounders passed Moat >= {min_moat_score:.0f}, "
        f"Dilution <= {max_share_dilution_pct:.1f}%, and 5Y CAGR >= {min_projected_cagr_pct:.1f}%) at:"
    )
    print(f"  └─ {QUALITATIVE_MOAT_CSV}\n")

    display_cols = [
        "Ticker",
        "Company Name",
        "Market Cap Tier",
        "Current Price ($)",
        "5Y Target Price ($)",
        "5Y Projected Total Return (%)",
        "5Y Projected CAGR (%)",
        "Total Moat Score (100)",
        "Pillar 1: Form 4 Insider Alignment (15)",
        "Pillar 5: Pricing Power (20)",
        "Pillar 6: SG&A Brand Leverage (15)",
        "Pillar 7: Brand Recognition Index (15)",
    ]
    existing_display_cols = [c for c in display_cols if c in qualified_df.columns]
    print(qualified_df[existing_display_cols].head(20).to_string(index=False))

    open_file(QUALITATIVE_MOAT_CSV)
    return qualified_df


if __name__ == "__main__":
    run_qualitative_scorer()
