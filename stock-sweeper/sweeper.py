import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pandas as pd
import yfinance as yf
from yfinance.data import YfData, new_session

from config import DB_NAME, BATCH_SIZE, BATCH_PAUSE_SECONDS
from database import init_db, get_db_connection
from sec_tickers import fetch_sec_tickers
from utils import clean_float, ensure_file_limits

ensure_file_limits()

_session_reset_lock = threading.Lock()
_last_session_reset = 0.0


def reset_yfinance_session(force: bool = False):
    global _last_session_reset
    with _session_reset_lock:
        now = time.time()
        if not force and (now - _last_session_reset) < 10.0:
            return
        try:
            d = YfData()
            with d._cookie_lock:
                old_session = getattr(d, "_session", None)
                if old_session is not None and hasattr(old_session, "close"):
                    try:
                        old_session.close()
                    except Exception:
                        pass
                d._session = new_session()
                d._crumb = None
                d._cookie = None
                d._cookie_strategy = "basic"
            _last_session_reset = time.time()
        except Exception:
            pass


def _get_row_val(df: pd.DataFrame, row_names: list[str], col):
    if not isinstance(df, pd.DataFrame) or df.empty or col not in df.columns:
        return None
    for name in row_names:
        if name in df.index:
            val = df.loc[name, col]
            if isinstance(val, pd.Series):
                val = val.iloc[0]
            cleaned = clean_float(val)
            if cleaned is not None:
                return cleaned
    return None


def _inactive_overview(ticker_symbol: str) -> dict:
    return {
        "ticker": ticker_symbol,
        "company_name": ticker_symbol,
        "sector": "Unknown",
        "industry": "Unknown",
        "market_cap": None,
        "current_price": None,
        "beta": None,
        "current_ratio": None,
        "debt_to_equity": None,
        "gross_margins": None,
        "operating_margins": None,
        "earnings_growth": None,
        "revenue_growth": None,
        "forward_pe": None,
        "free_cash_flow": None,
        "roic": None,
        "is_active": 0,
        "source_provider": "YahooFinance",
        "last_scraped": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def extract_ticker_data(ticker_symbol: str, fetch_full_statements: bool = True) -> tuple[dict, list[dict]]:
    info = {}
    yt = None
    for attempt in range(3):
        try:
            yt = yf.Ticker(ticker_symbol)
            info = yt.info or {}
            if info.get("currentPrice") or info.get("regularMarketPrice") or info.get("marketCap"):
                break
            if len(info) <= 2 and attempt < 2:
                reset_yfinance_session()
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        except Exception as e:
            err_str = str(e).lower()
            if "404" in err_str or "not found" in err_str:
                return _inactive_overview(ticker_symbol), []
            if "401" in err_str or "crumb" in err_str or "429" in err_str or "rate" in err_str or "too many" in err_str:
                reset_yfinance_session()
                time.sleep(1.5 * (attempt + 1))
            elif attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
            else:
                return None, []

    try:
        current_price = clean_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        market_cap = clean_float(info.get("marketCap"))

        if not current_price or not market_cap:
            if info is not None and len(info) > 2:
                return _inactive_overview(ticker_symbol), []
            return None, []

        raw_dte = clean_float(info.get("debtToEquity"))
        dte_ratio = (raw_dte / 100.0) if raw_dte is not None else None

        fcf = clean_float(info.get("freeCashflow"))
        gross_margins = clean_float(info.get("grossMargins"))
        operating_margins = clean_float(info.get("operatingMargins"))
        current_ratio = clean_float(info.get("currentRatio"))
        earnings_growth = clean_float(info.get("earningsGrowth"))
        revenue_growth = clean_float(info.get("revenueGrowth"))
        forward_pe = clean_float(info.get("forwardPE"))
        beta = clean_float(info.get("beta"))

        total_rev_info = clean_float(info.get("totalRevenue"))
        operating_income = clean_float(info.get("operatingIncome") or info.get("ebitda"))
        if operating_income is None and total_rev_info is not None and operating_margins is not None:
            operating_income = total_rev_info * operating_margins
        total_assets = clean_float(info.get("totalAssets"))

        passes_basic_gates = (
            market_cap >= 450_000_000
            and (current_ratio is None or current_ratio >= 0.4)
            and (dte_ratio is None or dte_ratio <= 2.2)
            and (operating_margins is None or operating_margins >= 0.08)
            and (earnings_growth is None or earnings_growth >= 0.03)
            and (revenue_growth is None or revenue_growth >= 0.03)
            and (forward_pe is None or forward_pe >= 4.0)
        )
        should_pull_statements = fetch_full_statements or passes_basic_gates

        inc_stmt = pd.DataFrame()
        bal_sheet = pd.DataFrame()
        cf_stmt = pd.DataFrame()

        if should_pull_statements:
            try:
                inc_stmt = yt.financials
            except Exception:
                inc_stmt = pd.DataFrame()
            try:
                bal_sheet = yt.balance_sheet
            except Exception:
                bal_sheet = pd.DataFrame()
            try:
                cf_stmt = yt.cashflow
            except Exception:
                cf_stmt = pd.DataFrame()

        # Extract ROIC = NOPAT / Invested Capital
        roic = None
        try:
            if isinstance(bal_sheet, pd.DataFrame) and not bal_sheet.empty:
                latest_bs_col = bal_sheet.columns[0]
                tot_assets_val = _get_row_val(bal_sheet, ["Total Assets"], latest_bs_col) or total_assets
                curr_liab_val = _get_row_val(bal_sheet, ["Current Liabilities", "Total Current Liabilities"], latest_bs_col) or 0.0
                cash_val = _get_row_val(
                    bal_sheet,
                    [
                        "Cash Cash Equivalents And Short Term Investments",
                        "Cash And Cash Equivalents",
                        "Cash Financial",
                    ],
                    latest_bs_col,
                ) or 0.0

                op_inc_val = None
                if isinstance(inc_stmt, pd.DataFrame) and not inc_stmt.empty:
                    latest_inc_col = inc_stmt.columns[0]
                    op_inc_val = _get_row_val(inc_stmt, ["Operating Income", "EBIT", "Operating Revenue"], latest_inc_col)
                if op_inc_val is None:
                    op_inc_val = operating_income

                if tot_assets_val is not None and op_inc_val is not None:
                    invested_capital = tot_assets_val - curr_liab_val - cash_val
                    if invested_capital <= 0:
                        invested_capital = _get_row_val(bal_sheet, ["Invested Capital", "Total Capitalization"], latest_bs_col) or tot_assets_val
                    if invested_capital and invested_capital > 0:
                        nopat = op_inc_val * (1.0 - 0.21)
                        roic = clean_float(nopat / invested_capital)
        except Exception:
            pass

        if roic is None:
            roa = clean_float(info.get("returnOnAssets"))
            roe = clean_float(info.get("returnOnEquity"))
            tot_cash = clean_float(info.get("totalCash")) or 0.0
            if operating_income is not None and total_assets is not None and total_assets > tot_cash:
                inv_cap = total_assets - tot_cash
                if inv_cap > 0:
                    roic = clean_float((operating_income * (1.0 - 0.21)) / inv_cap)
            elif roe is not None and dte_ratio is not None and dte_ratio >= 0:
                roic = clean_float(roe / (1.0 + dte_ratio))
            elif roa is not None:
                roic = roa

        financial_records = []
        latest_shares_count = clean_float(info.get("sharesOutstanding"))

        if isinstance(inc_stmt, pd.DataFrame) and not inc_stmt.empty:
            for date_col in inc_stmt.columns:
                try:
                    year = pd.to_datetime(date_col).year
                except Exception:
                    continue

                rev = _get_row_val(inc_stmt, ["Total Revenue", "Operating Revenue"], date_col)
                gross_prof = _get_row_val(inc_stmt, ["Gross Profit"], date_col)
                sga = _get_row_val(
                    inc_stmt,
                    ["Selling General And Administration", "General And Administrative Expense"],
                    date_col,
                )
                net_inc = _get_row_val(inc_stmt, ["Net Income", "Net Income Common Stockholders"], date_col)
                eps = _get_row_val(inc_stmt, ["Diluted EPS", "Basic EPS"], date_col)
                shares = _get_row_val(inc_stmt, ["Diluted Average Shares", "Basic Average Shares"], date_col)

                if shares is not None and latest_shares_count is None:
                    latest_shares_count = shares

                tot_assets_yr = _get_row_val(bal_sheet, ["Total Assets"], date_col)
                tot_liab_yr = _get_row_val(bal_sheet, ["Total Liabilities Net Minority Interest", "Total Liabilities"], date_col)
                curr_assets_yr = _get_row_val(bal_sheet, ["Current Assets", "Total Current Assets"], date_col)
                curr_liab_yr = _get_row_val(bal_sheet, ["Current Liabilities", "Total Current Liabilities"], date_col)

                ocf = _get_row_val(cf_stmt, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], date_col)
                capex = _get_row_val(cf_stmt, ["Capital Expenditure", "Capital Expenditures"], date_col)
                direct_fcf = _get_row_val(cf_stmt, ["Free Cash Flow"], date_col)

                if ocf is not None and capex is not None:
                    rec_fcf = clean_float(ocf + capex if capex <= 0 else ocf - capex)
                else:
                    rec_fcf = direct_fcf

                if fcf is None and rec_fcf is not None:
                    fcf = rec_fcf

                net_margin = clean_float(net_inc / rev) if (net_inc is not None and rev is not None and rev != 0) else None
                pe = clean_float(current_price / eps) if (eps is not None and eps > 0) else None

                financial_records.append({
                    "ticker": ticker_symbol,
                    "year": int(year),
                    "period_type": "Historical",
                    "revenue": rev,
                    "gross_profit": gross_prof,
                    "sga_expense": sga,
                    "net_income": net_inc,
                    "net_income_margin": net_margin,
                    "eps_diluted": eps,
                    "shares_outstanding": shares,
                    "total_assets": tot_assets_yr,
                    "total_liabilities": tot_liab_yr,
                    "current_assets": curr_assets_yr,
                    "current_liabilities": curr_liab_yr,
                    "operating_cash_flow": ocf,
                    "capital_expenditures": capex,
                    "free_cash_flow": rec_fcf,
                    "pe_ratio": pe,
                    "source_provider": "YahooFinance",
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

        overview_data = {
            "ticker": ticker_symbol,
            "company_name": info.get("longName") or info.get("shortName") or ticker_symbol,
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": market_cap,
            "current_price": current_price,
            "beta": beta,
            "current_ratio": current_ratio,
            "debt_to_equity": dte_ratio,
            "gross_margins": gross_margins,
            "operating_margins": operating_margins,
            "earnings_growth": earnings_growth,
            "revenue_growth": revenue_growth,
            "forward_pe": forward_pe,
            "free_cash_flow": fcf,
            "roic": roic,
            "is_active": 1,
            "source_provider": "YahooFinance",
            "last_scraped": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        if should_pull_statements:
            try:
                earnings_est = yt.earnings_estimate
                revenue_est = yt.revenue_estimate

                if isinstance(earnings_est, pd.DataFrame) and not earnings_est.empty:
                    for idx, row in earnings_est.iterrows():
                        if idx in ["0y", "+1y"]:
                            proj_year = datetime.now().year if idx == "0y" else datetime.now().year + 1
                            proj_eps = clean_float(row.get("avg"))

                            proj_rev = None
                            if isinstance(revenue_est, pd.DataFrame) and idx in revenue_est.index and "avg" in revenue_est.columns:
                                proj_rev = clean_float(revenue_est.loc[idx, "avg"])

                            proj_net_inc = clean_float(proj_eps * latest_shares_count) if (proj_eps is not None and latest_shares_count is not None) else None
                            proj_net_margin = clean_float(proj_net_inc / proj_rev) if (proj_net_inc is not None and proj_rev is not None and proj_rev != 0) else None
                            proj_pe = clean_float(current_price / proj_eps) if (proj_eps is not None and proj_eps > 0) else None

                            financial_records.append({
                                "ticker": ticker_symbol,
                                "year": int(proj_year),
                                "period_type": "Projected",
                                "revenue": proj_rev,
                                "gross_profit": None,
                                "sga_expense": None,
                                "net_income": proj_net_inc,
                                "net_income_margin": proj_net_margin,
                                "eps_diluted": proj_eps,
                                "shares_outstanding": latest_shares_count,
                                "total_assets": None,
                                "total_liabilities": None,
                                "current_assets": None,
                                "current_liabilities": None,
                                "operating_cash_flow": None,
                                "capital_expenditures": None,
                                "free_cash_flow": None,
                                "pe_ratio": proj_pe,
                                "source_provider": "Yahoo_Consensus",
                                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            })
            except Exception:
                pass

        return overview_data, financial_records

    except Exception:
        return None, []


def save_to_database(conn, overview_batch, financial_batch):
    cursor = conn.cursor()
    if overview_batch:
        cursor.executemany("""
        INSERT INTO company_overview 
        (ticker, company_name, sector, industry, market_cap, current_price, beta, 
         current_ratio, debt_to_equity, gross_margins, operating_margins, earnings_growth, 
         revenue_growth, forward_pe, free_cash_flow, roic, is_active, source_provider, last_scraped)
        VALUES (:ticker, :company_name, :sector, :industry, :market_cap, :current_price, :beta,
                :current_ratio, :debt_to_equity, :gross_margins, :operating_margins, :earnings_growth,
                :revenue_growth, :forward_pe, :free_cash_flow, :roic, :is_active, :source_provider, :last_scraped)
        ON CONFLICT(ticker) DO UPDATE SET
            company_name = excluded.company_name,
            sector = excluded.sector,
            industry = excluded.industry,
            market_cap = excluded.market_cap,
            current_price = excluded.current_price,
            beta = excluded.beta,
            current_ratio = excluded.current_ratio,
            debt_to_equity = excluded.debt_to_equity,
            gross_margins = COALESCE(excluded.gross_margins, gross_margins),
            operating_margins = excluded.operating_margins,
            earnings_growth = excluded.earnings_growth,
            revenue_growth = excluded.revenue_growth,
            forward_pe = excluded.forward_pe,
            free_cash_flow = excluded.free_cash_flow,
            roic = excluded.roic,
            is_active = excluded.is_active,
            source_provider = excluded.source_provider,
            last_scraped = excluded.last_scraped,
            updated_at = CURRENT_TIMESTAMP;
        """, overview_batch)

    if financial_batch:
        cursor.executemany("""
        INSERT INTO financial_records
        (ticker, year, period_type, revenue, gross_profit, sga_expense, net_income, net_income_margin, eps_diluted, 
         shares_outstanding, total_assets, total_liabilities, current_assets, current_liabilities, 
         operating_cash_flow, capital_expenditures, free_cash_flow, pe_ratio, source_provider, updated_at)
        VALUES (:ticker, :year, :period_type, :revenue, :gross_profit, :sga_expense, :net_income, :net_income_margin, :eps_diluted,
                :shares_outstanding, :total_assets, :total_liabilities, :current_assets, :current_liabilities,
                :operating_cash_flow, :capital_expenditures, :free_cash_flow, :pe_ratio, :source_provider, :updated_at)
        ON CONFLICT(ticker, year, period_type) DO UPDATE SET
            revenue = COALESCE(excluded.revenue, revenue),
            gross_profit = COALESCE(excluded.gross_profit, gross_profit),
            sga_expense = COALESCE(excluded.sga_expense, sga_expense),
            net_income = COALESCE(excluded.net_income, net_income),
            net_income_margin = COALESCE(excluded.net_income_margin, net_income_margin),
            eps_diluted = COALESCE(excluded.eps_diluted, eps_diluted),
            shares_outstanding = COALESCE(excluded.shares_outstanding, shares_outstanding),
            total_assets = COALESCE(excluded.total_assets, total_assets),
            total_liabilities = COALESCE(excluded.total_liabilities, total_liabilities),
            current_assets = COALESCE(excluded.current_assets, current_assets),
            current_liabilities = COALESCE(excluded.current_liabilities, current_liabilities),
            operating_cash_flow = COALESCE(excluded.operating_cash_flow, operating_cash_flow),
            capital_expenditures = COALESCE(excluded.capital_expenditures, capital_expenditures),
            free_cash_flow = COALESCE(excluded.free_cash_flow, free_cash_flow),
            pe_ratio = COALESCE(excluded.pe_ratio, pe_ratio),
            source_provider = excluded.source_provider,
            updated_at = excluded.updated_at;
        """, financial_batch)
    conn.commit()


def run_sweeper(limit: int = None, max_workers: int = 8):
    init_db(reset=False)

    conn = get_db_connection(DB_NAME)
    sec_tickers = fetch_sec_tickers()
    if not sec_tickers:
        conn.close()
        return

    if limit:
        sec_tickers = sec_tickers[:limit]

    cursor = conn.cursor()
    # Tiered cache TTL:
    # - Active candidates (market_cap >= $100M): fresh for 24 hours
    # - Inactive/delisted/404 tickers (is_active = 0) or deep micro-caps (< $100M): fresh for 7 days
    cursor.execute("""
        SELECT ticker FROM company_overview
        WHERE last_scraped >= datetime('now', '-24 hours')
           OR (
               last_scraped >= datetime('now', '-7 days')
               AND (is_active = 0 OR market_cap IS NULL OR market_cap < 100000000)
           )
    """)
    scraped_recent = {row[0] for row in cursor.fetchall()}

    pending_tickers = [t for t in sec_tickers if t not in scraped_recent]

    print(f"Total Tickers: {len(sec_tickers)} | Scraped Recently: {len(scraped_recent)} | Pending: {len(pending_tickers)}")

    if not pending_tickers:
        conn.close()
        print("Market sweep completed successfully (all requested tickers already scraped today).")
        return

    fetch_full = True if (limit is not None and limit <= 200) else False

    total_pending = len(pending_tickers)
    for start_idx in range(0, total_pending, BATCH_SIZE):
        batch_tickers = pending_tickers[start_idx : start_idx + BATCH_SIZE]
        overview_map = {}
        financial_batch = []
        remaining = list(batch_tickers)

        for batch_attempt in range(3):
            if not remaining:
                break
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ticker = {
                    executor.submit(extract_ticker_data, ticker, fetch_full): ticker
                    for ticker in remaining
                }
                for future in as_completed(future_to_ticker):
                    t_sym = future_to_ticker[future]
                    try:
                        overview, records = future.result()
                        if overview:
                            overview_map[t_sym] = overview
                            financial_batch.extend(records)
                    except Exception:
                        pass

            active_in_batch = sum(1 for v in overview_map.values() if v.get("is_active") == 1)
            if active_in_batch >= max(1, int(len(batch_tickers) * 0.4)) or batch_attempt == 2:
                break

            remaining = [t for t in batch_tickers if overview_map.get(t, {}).get("is_active") != 1]
            print(
                f"    [!] Batch had only {active_in_batch}/{len(batch_tickers)} active companies "
                f"(attempt {batch_attempt+1}/3). Refreshing Yahoo session & retrying {len(remaining)} tickers..."
            )
            reset_yfinance_session(force=True)
            time.sleep(4.0 * (batch_attempt + 1))

        overview_batch = list(overview_map.values())
        active_count = sum(1 for v in overview_batch if v.get("is_active") == 1)
        save_to_database(conn, overview_batch, financial_batch)
        done_count = min(start_idx + BATCH_SIZE, total_pending)
        print(
            f"[{done_count}/{total_pending}] Saved batch ({active_count} active / {len(overview_batch)} total companies, "
            f"{len(financial_batch)} financial records) to DB."
        )
        if done_count < total_pending:
            time.sleep(BATCH_PAUSE_SECONDS)

    conn.close()
    print("Market sweep completed successfully.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Yahoo Finance market sweeper.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tickers to sweep.")
    args = parser.parse_args()
    run_sweeper(limit=args.limit)
