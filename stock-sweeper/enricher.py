import sqlite3
import time
import math
import random
import requests
import re
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from datetime import datetime
from config import DB_NAME, USER_EMAIL
from screener import run_screener
from edgar import set_identity, Company

set_identity(f"StockSweeper/1.0 {USER_EMAIL}")


def _clean_float(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


_last_finviz_call = 0.0
_last_sec_call = 0.0


def fetch_finviz_eps_next_5y(ticker: str, max_retries: int = 3):
    """
    Scrapes 'EPS next 5Y' growth rate string from Finviz with token-bucket pacing (~2 req/sec) and exponential backoff.
    """
    global _last_finviz_call
    elapsed = time.time() - _last_finviz_call
    if elapsed < 0.45:
        time.sleep(0.45 - elapsed)

    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    for attempt in range(max_retries):
        try:
            _last_finviz_call = time.time()
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                label_cell = soup.find(string=re.compile(r'EPS next 5Y', re.I))
                if label_cell:
                    parent_td = label_cell.find_parent('td')
                    val_cell = parent_td.find_next_sibling('td') if parent_td else None
                    if val_cell:
                        raw_val = val_cell.text.strip().replace('%', '')
                        val = _clean_float(raw_val)
                        if val is not None:
                            return val / 100.0
                return None
            elif resp.status_code in (429, 500, 502, 503, 504):
                time.sleep((2 ** attempt) + random.uniform(0.2, 0.6))
            else:
                return None
        except Exception:
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) + random.uniform(0.2, 0.6))
    return None


def fetch_batch_historical_year_end_prices(tickers: list[str], start_year: int, end_year: int, chunk_size: int = 50) -> dict[str, dict[int, float]]:
    """
    Fetches historical year-end prices in multi-ticker batches using yf.download to minimize HTTP calls.
    """
    all_price_maps = {t: {} for t in tickers}
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        for attempt in range(3):
            try:
                data = yf.download(chunk, start=f"{start_year}-01-01", end=f"{end_year+1}-01-15", progress=False, threads=True)
                if not data.empty and 'Close' in data:
                    close_df = data['Close']
                    for t in chunk:
                        if isinstance(close_df, pd.DataFrame):
                            if t not in close_df.columns:
                                continue
                            s_close = close_df[t].dropna()
                        else:
                            s_close = close_df.dropna()
                        for yr in range(start_year, end_year + 1):
                            yr_data = s_close[s_close.index.year == yr]
                            if not yr_data.empty:
                                cleaned = _clean_float(yr_data.iloc[-1])
                                if cleaned is not None:
                                    all_price_maps[t][yr] = cleaned
                break
            except Exception:
                if attempt < 2:
                    time.sleep((2 ** attempt) + random.uniform(0.1, 0.5))
    return all_price_maps


def fetch_historical_year_end_prices(ticker: str, start_year: int, end_year: int, max_retries: int = 3):
    price_map = {}
    for attempt in range(max_retries):
        try:
            data = yf.download(ticker, start=f"{start_year}-01-01", end=f"{end_year+1}-01-15", progress=False)
            if not data.empty:
                close_data = data['Close'][ticker] if isinstance(data.columns, pd.MultiIndex) else data['Close']
                close_data = close_data.dropna()

                for yr in range(start_year, end_year + 1):
                    yr_data = close_data[close_data.index.year == yr]
                    if not yr_data.empty:
                        cleaned = _clean_float(yr_data.iloc[-1])
                        if cleaned is not None:
                            price_map[yr] = cleaned
            break
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) + random.uniform(0.1, 0.5))
            else:
                print(f"    Price history fetch note for {ticker}: {e}")
    return price_map


def fetch_sec_historical_years_5_to_10(ticker: str, current_year: int, price_map: dict, max_retries: int = 3):
    global _last_sec_call
    min_year = current_year - 10
    max_year = current_year - 1

    for attempt in range(max_retries):
        try:
            elapsed = time.time() - _last_sec_call
            if elapsed < 0.12:
                time.sleep(0.12 - elapsed)
            _last_sec_call = time.time()

            c = Company(ticker)
            facts = c.get_facts()
            if not facts:
                return []

            df = facts.to_dataframe()
            if df.empty:
                return []

            if 'fiscal_period' in df.columns:
                df_fy = df[(df['fiscal_period'] == 'FY') & (df['fiscal_year'] >= min_year) & (df['fiscal_year'] <= max_year)].copy()
            else:
                df_fy = df[(df['fiscal_year'] >= min_year) & (df['fiscal_year'] <= max_year)].copy()

            if df_fy.empty:
                return []

            val_col = 'numeric_value' if 'numeric_value' in df_fy.columns else 'value'

            concept_map = {
                'revenue': ['revenues', 'revenuefromcontractwithcustomerexcludingassessedtax', 'salesrevenuenet', 'totalrevenuesandotherincome', 'revenue', 'interestanddividendincomeoperating', 'revenuesnetofinterestexpense'],
                'net_income': ['netincomeloss', 'profitloss', 'netincomelossavailabletocommonstockholdersbasic', 'profitlossattributabletoownersofparent'],
                'eps_diluted': ['earningspersharediluted', 'earningspersharebasic', 'dilutedearningslosspershare', 'basicearningslosspershare'],
                'shares_outstanding': ['weightedaveragenumberofdilutedsharesoutstanding', 'commonstocksharesoutstanding', 'entitycommonstocksharesoutstanding', 'weightedaverageshares', 'adjustedweightedaverageshares'],
                'total_assets': ['assets'],
                'total_liabilities': ['liabilities', 'liabilitiesandstockholdersequity'],
                'current_assets': ['assetscurrent', 'currentassets'],
                'current_liabilities': ['liabilitiescurrent', 'currentliabilities'],
                'operating_cash_flow': ['netcashprovidedbyusedinoperatingactivities', 'netcashprovidedbyusedinoperatingactivitiescontinuingoperations', 'cashflowsfromusedinoperatingactivities'],
                'capital_expenditures': ['paymentstoacquirepropertyplantandequipment', 'paymentstoacquireproductiveassets', 'purchaseofpropertyplantandequipmentclassifiedasinvestingactivities'],
            }

            records_by_year = {}
            for fy in range(min_year, max_year + 1):
                records_by_year[fy] = {
                    'ticker': ticker,
                    'year': fy,
                    'period_type': 'Historical',
                    'revenue': None,
                    'net_income': None,
                    'net_income_margin': None,
                    'eps_diluted': None,
                    'shares_outstanding': None,
                    'total_assets': None,
                    'total_liabilities': None,
                    'current_assets': None,
                    'current_liabilities': None,
                    'operating_cash_flow': None,
                    'capital_expenditures': None,
                    'free_cash_flow': None,
                    'pe_ratio': None,
                    'year_end_price': price_map.get(fy),
                    'consensus_eps_growth': None,
                    'consensus_rev_growth': None,
                    'source_provider': 'SEC_EDGAR_10K',
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }

            for _, row in df_fy.iterrows():
                try:
                    fy = int(row['fiscal_year'])
                except (ValueError, TypeError):
                    continue

                if fy not in records_by_year:
                    continue

                raw_concept = str(row.get('concept', '')).lower()
                clean_concept = raw_concept.split(':')[-1] if ':' in raw_concept else raw_concept
                num_val = _clean_float(row.get(val_col))

                if num_val is not None:
                    for field, concept_list in concept_map.items():
                        if clean_concept in concept_list and records_by_year[fy][field] is None:
                            records_by_year[fy][field] = num_val

            valid_records = []
            for fy, rec in records_by_year.items():
                if rec['revenue'] is not None or rec['net_income'] is not None or rec['total_assets'] is not None:
                    if rec['revenue'] and rec['net_income'] is not None and rec['revenue'] != 0:
                        rec['net_income_margin'] = _clean_float(rec['net_income'] / rec['revenue'])

                    if rec['operating_cash_flow'] is not None and rec['capital_expenditures'] is not None:
                        capex_val = rec['capital_expenditures']
                        rec['free_cash_flow'] = _clean_float(
                            rec['operating_cash_flow'] + capex_val if capex_val <= 0 else rec['operating_cash_flow'] - capex_val
                        )

                    year_end_price = price_map.get(fy)
                    if year_end_price and rec['eps_diluted'] and rec['eps_diluted'] > 0:
                        rec['pe_ratio'] = _clean_float(year_end_price / rec['eps_diluted'])

                    valid_records.append(rec)

            return valid_records

        except Exception as e:
            if attempt < max_retries - 1:
                backoff = (2 ** attempt) + random.uniform(0.2, 0.8)
                time.sleep(backoff)
            else:
                print(f"    SEC fetch note for {ticker}: {e}")
                return []
    return []


def fetch_yahoo_current_and_consensus(ticker: str, current_year: int, price_map: dict, max_retries: int = 3):
    records = []
    overview_meta = {'target_mean_price': None, 'yahoo_lt_growth': None}
    for attempt in range(max_retries):
        try:
            yt = yf.Ticker(ticker)
            info = yt.info or {}
            rev_est = yt.revenue_estimate
            eps_est = yt.earnings_estimate
            shares = _clean_float(info.get('sharesOutstanding'))

            overview_meta['target_mean_price'] = _clean_float(info.get('targetMeanPrice'))
            raw_y_lt = _clean_float(info.get('longTermPotentialGrowth'))
            if raw_y_lt is None:
                raw_y_lt = _clean_float(info.get('earningsGrowth'))
            overview_meta['yahoo_lt_growth'] = raw_y_lt

            ttm_rev = _clean_float(info.get('totalRevenue'))
            ttm_eps = _clean_float(info.get('trailingEps'))
            ttm_netinc = _clean_float(ttm_eps * shares) if (ttm_eps is not None and shares is not None) else None
            ttm_margin = _clean_float(ttm_netinc / ttm_rev) if (ttm_netinc is not None and ttm_rev is not None and ttm_rev != 0) else None

            curr_price = _clean_float(info.get('currentPrice') or info.get('regularMarketPrice'))
            pe_curr = _clean_float(curr_price / ttm_eps) if (curr_price is not None and ttm_eps is not None and ttm_eps > 0) else None

            tot_assets = _clean_float(info.get('totalAssets'))
            tot_liab = None
            curr_assets = None
            curr_liab = None
            ocf = _clean_float(info.get('operatingCashflow'))
            fcf = _clean_float(info.get('freeCashflow'))
            capex = _clean_float(fcf - ocf) if (fcf is not None and ocf is not None) else None

            try:
                bs = yt.balance_sheet
                if bs is not None and not bs.empty:
                    latest_col = bs.columns[0]

                    def get_bs_val(keys):
                        for k in keys:
                            if k in bs.index:
                                val = _clean_float(bs.loc[k, latest_col])
                                if val is not None:
                                    return val
                        return None

                    tot_assets = tot_assets or get_bs_val(['Total Assets'])
                    tot_liab = get_bs_val(['Total Liabilities Net Minority Interest', 'Total Debt', 'Total Liabilities'])
                    curr_assets = get_bs_val(['Current Assets', 'Total Current Assets'])
                    curr_liab = get_bs_val(['Current Liabilities', 'Total Current Liabilities'])
            except Exception:
                pass

            records.append((
                ticker, current_year, 'Historical',
                ttm_rev, ttm_netinc, ttm_margin, ttm_eps, shares,
                tot_assets, tot_liab, curr_assets, curr_liab,
                ocf, capex, fcf, pe_curr,
                curr_price, None, None,
                'YahooFinance', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

            if isinstance(rev_est, pd.DataFrame) and '0y' in rev_est.index:
                r_0y = _clean_float(rev_est.loc['0y', 'avg']) if 'avg' in rev_est.columns else None
                e_0y = _clean_float(eps_est.loc['0y', 'avg']) if (isinstance(eps_est, pd.DataFrame) and '0y' in eps_est.index and 'avg' in eps_est.columns) else None
                rg_0y = _clean_float(rev_est.loc['0y', 'growth']) if 'growth' in rev_est.columns else None
                eg_0y = _clean_float(eps_est.loc['0y', 'growth']) if (isinstance(eps_est, pd.DataFrame) and '0y' in eps_est.index and 'growth' in eps_est.columns) else None
                net_inc_0y = _clean_float(e_0y * shares) if (e_0y is not None and shares is not None) else None
                margin_0y = _clean_float(net_inc_0y / r_0y) if (net_inc_0y is not None and r_0y is not None and r_0y != 0) else None
                fwd_pe = _clean_float(curr_price / e_0y) if (curr_price is not None and e_0y is not None and e_0y > 0) else _clean_float(info.get('forwardPE'))

                records.append((
                    ticker, current_year, 'Projected',
                    r_0y, net_inc_0y, margin_0y, e_0y, shares,
                    tot_assets, tot_liab, curr_assets, curr_liab,
                    ocf, capex, fcf, fwd_pe,
                    curr_price, eg_0y, rg_0y,
                    'Yahoo_Consensus', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))
            else:
                e_0y = _clean_float(info.get('forwardEps')) or ttm_eps
                r_0y = ttm_rev
                eg_0y = _clean_float(info.get('earningsGrowth'))
                rg_0y = _clean_float(info.get('revenueGrowth'))
                net_inc_0y = _clean_float(e_0y * shares) if (e_0y is not None and shares is not None) else ttm_netinc
                margin_0y = _clean_float(net_inc_0y / r_0y) if (net_inc_0y is not None and r_0y is not None and r_0y != 0) else ttm_margin
                fwd_pe = _clean_float(curr_price / e_0y) if (curr_price is not None and e_0y is not None and e_0y > 0) else _clean_float(info.get('forwardPE'))
                records.append((
                    ticker, current_year, 'Projected',
                    r_0y, net_inc_0y, margin_0y, e_0y, shares,
                    tot_assets, tot_liab, curr_assets, curr_liab,
                    ocf, capex, fcf, fwd_pe,
                    curr_price, eg_0y, rg_0y,
                    'Yahoo_Consensus', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))

            if isinstance(rev_est, pd.DataFrame) and '+1y' in rev_est.index:
                r_1y = _clean_float(rev_est.loc['+1y', 'avg']) if 'avg' in rev_est.columns else None
                e_1y = _clean_float(eps_est.loc['+1y', 'avg']) if (isinstance(eps_est, pd.DataFrame) and '+1y' in eps_est.index and 'avg' in eps_est.columns) else None
                rg_1y = _clean_float(rev_est.loc['+1y', 'growth']) if 'growth' in rev_est.columns else None
                eg_1y = _clean_float(eps_est.loc['+1y', 'growth']) if (isinstance(eps_est, pd.DataFrame) and '+1y' in eps_est.index and 'growth' in eps_est.columns) else None
                net_inc_1y = _clean_float(e_1y * shares) if (e_1y is not None and shares is not None) else None
                margin_1y = _clean_float(net_inc_1y / r_1y) if (net_inc_1y is not None and r_1y is not None and r_1y != 0) else None
                fwd_pe_1y = _clean_float(curr_price / e_1y) if (curr_price is not None and e_1y is not None and e_1y > 0) else None

                records.append((
                    ticker, current_year + 1, 'Projected',
                    r_1y, net_inc_1y, margin_1y, e_1y, shares,
                    None, None, None, None,
                    None, None, None, fwd_pe_1y,
                    overview_meta['target_mean_price'], eg_1y, rg_1y,
                    'Yahoo_Consensus', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))
            else:
                eg = _clean_float(info.get('earningsGrowth')) or 0.08
                rg = _clean_float(info.get('revenueGrowth')) or 0.08
                e_1y = _clean_float(e_0y * (1.0 + eg)) if e_0y is not None else _clean_float(info.get('forwardEps'))
                r_1y = _clean_float(r_0y * (1.0 + rg)) if r_0y is not None else ttm_rev
                net_inc_1y = _clean_float(e_1y * shares) if (e_1y is not None and shares is not None) else None
                margin_1y = _clean_float(net_inc_1y / r_1y) if (net_inc_1y is not None and r_1y is not None and r_1y != 0) else None
                fwd_pe_1y = _clean_float(curr_price / e_1y) if (curr_price is not None and e_1y is not None and e_1y > 0) else _clean_float(info.get('forwardPE'))
                records.append((
                    ticker, current_year + 1, 'Projected',
                    r_1y, net_inc_1y, margin_1y, e_1y, shares,
                    None, None, None, None,
                    None, None, None, fwd_pe_1y,
                    overview_meta['target_mean_price'], eg, rg,
                    'Yahoo_Consensus', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))
            break

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) + random.uniform(0.2, 0.6))
            else:
                print(f"    Yahoo fetch note for {ticker}: {e}")

    return records, overview_meta


def enrich_shortlist_history(current_year: int = None, force: bool = False):
    from database import init_db
    init_db(reset=False)

    if current_year is None:
        current_year = datetime.now().year

    print("Running SQL Screener...")
    shortlist_df = run_screener()
    if shortlist_df.empty:
        return

    all_tickers = shortlist_df['ticker'].tolist()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM financial_records WHERE source_provider = 'Yahoo_Extrapolated'")
    conn.commit()

    if not force:
        placeholders = ",".join(["?"] * len(all_tickers))
        cursor.execute(
            f"SELECT ticker FROM company_overview WHERE ticker IN ({placeholders}) AND last_enriched >= datetime('now', '-24 hours')",
            all_tickers,
        )
        recently_enriched = {row[0] for row in cursor.fetchall()}
        tickers = [t for t in all_tickers if t not in recently_enriched]
        print(f"Shortlist: {len(all_tickers)} | Enriched Recently (<24h): {len(recently_enriched)} | Pending Enrichment: {len(tickers)}")
    else:
        tickers = all_tickers

    if not tickers:
        conn.close()
        print("All shortlisted tickers already enriched within the last 24 hours!")
        return

    print(f"Fetching 10-year historical prices for {len(tickers)} shortlisted stocks in batch...")
    batch_price_maps = fetch_batch_historical_year_end_prices(tickers, current_year - 10, current_year - 1)

    for idx, ticker in enumerate(tickers, 1):
        print(f"\n[{idx}/{len(tickers)}] -> Enriching {ticker}...")

        price_map = batch_price_maps.get(ticker) or fetch_historical_year_end_prices(ticker, current_year - 10, current_year - 1)

        # Update year_end_price & pe_ratio on any existing historical rows from YahooFinance
        for yr, p_val in price_map.items():
            cursor.execute(
                """
                UPDATE financial_records
                SET year_end_price = COALESCE(year_end_price, ?),
                    pe_ratio = CASE WHEN eps_diluted > 0 THEN ? / eps_diluted ELSE pe_ratio END
                WHERE ticker = ? AND year = ? AND period_type = 'Historical';
                """,
                (p_val, p_val, ticker, yr),
            )

        sec_records = fetch_sec_historical_years_5_to_10(ticker, current_year, price_map)
        if sec_records:
            records_tuple = [
                (
                    r['ticker'], r['year'], r['period_type'], r['revenue'], r['net_income'],
                    r['net_income_margin'], r['eps_diluted'], r['shares_outstanding'],
                    r['total_assets'], r['total_liabilities'], r['current_assets'],
                    r['current_liabilities'], r['operating_cash_flow'], r['capital_expenditures'],
                    r['free_cash_flow'], r['pe_ratio'], r['year_end_price'],
                    r['consensus_eps_growth'], r['consensus_rev_growth'],
                    r['source_provider'], r['updated_at']
                )
                for r in sec_records
            ]
            cursor.executemany("""
            INSERT INTO financial_records 
            (ticker, year, period_type, revenue, net_income, net_income_margin, eps_diluted, shares_outstanding, total_assets, total_liabilities, current_assets, current_liabilities, operating_cash_flow, capital_expenditures, free_cash_flow, pe_ratio, year_end_price, consensus_eps_growth, consensus_rev_growth, source_provider, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, year, period_type) DO UPDATE SET
                revenue = COALESCE(excluded.revenue, revenue),
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
                year_end_price = COALESCE(excluded.year_end_price, year_end_price),
                source_provider = 'SEC_EDGAR_10K',
                updated_at = excluded.updated_at;
            """, records_tuple)
            conn.commit()
            print(f"    ✓ Sourced {len(sec_records)} historical years via SEC 10-K filings.")

        yahoo_records, overview_meta = fetch_yahoo_current_and_consensus(ticker, current_year, price_map)
        finviz_5y = fetch_finviz_eps_next_5y(ticker)

        cursor.execute(
            """
            UPDATE company_overview
            SET target_mean_price = COALESCE(?, target_mean_price),
                finviz_eps_5y = COALESCE(?, finviz_eps_5y),
                yahoo_lt_growth = COALESCE(?, yahoo_lt_growth),
                last_enriched = ?
            WHERE ticker = ?;
            """,
            (
                overview_meta.get('target_mean_price'),
                finviz_5y,
                overview_meta.get('yahoo_lt_growth'),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ticker,
            ),
        )

        if yahoo_records:
            cursor.executemany("""
            INSERT INTO financial_records 
            (ticker, year, period_type, revenue, net_income, net_income_margin, eps_diluted, shares_outstanding, total_assets, total_liabilities, current_assets, current_liabilities, operating_cash_flow, capital_expenditures, free_cash_flow, pe_ratio, year_end_price, consensus_eps_growth, consensus_rev_growth, source_provider, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, year, period_type) DO UPDATE SET
                revenue = COALESCE(excluded.revenue, revenue),
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
                year_end_price = COALESCE(excluded.year_end_price, year_end_price),
                consensus_eps_growth = COALESCE(excluded.consensus_eps_growth, consensus_eps_growth),
                consensus_rev_growth = COALESCE(excluded.consensus_rev_growth, consensus_rev_growth),
                source_provider = excluded.source_provider,
                updated_at = excluded.updated_at;
            """, yahoo_records)
            conn.commit()
            print(f"    ✓ Populated {current_year} Historical YTD + {current_year}/{current_year+1} Wall Street Consensus.")

    conn.close()
    print("\nEnrichment complete!")


if __name__ == "__main__":
    enrich_shortlist_history()
