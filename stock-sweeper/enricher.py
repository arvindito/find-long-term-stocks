import sqlite3
import time
import requests
import re
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from datetime import datetime
from config import DB_NAME
from screener import run_screener
from edgar import set_identity, Company

set_identity("Arvind Advani arvind.advani@gmail.com")

def fetch_finviz_eps_next_5y(ticker: str):
    """
    Scrapes 'EPS next 5Y' growth rate string from Finviz.
    """
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            label_cell = soup.find(text=re.compile(r'EPS next 5Y', re.I))
            if label_cell:
                val_cell = label_cell.find_parent('td').find_next_sibling('td')
                if val_cell:
                    raw_val = val_cell.text.strip().replace('%', '')
                    return float(raw_val) / 100.0
    except Exception:
        pass
    return None

def fetch_historical_year_end_prices(ticker: str, start_year: int, end_year: int):
    price_map = {}
    try:
        data = yf.download(ticker, start=f"{start_year}-01-01", end=f"{end_year+1}-01-15", progress=False)
        if not data.empty:
            close_data = data['Close'][ticker] if isinstance(data.columns, pd.MultiIndex) else data['Close']
            close_data = close_data.dropna()

            for yr in range(start_year, end_year + 1):
                yr_data = close_data[close_data.index.year == yr]
                if not yr_data.empty:
                    price_map[yr] = float(yr_data.iloc[-1])
    except Exception as e:
        print(f"    Price history fetch note for {ticker}: {e}")
    return price_map

def fetch_sec_historical_years_5_to_10(ticker: str, current_year: int, price_map: dict):
    min_year = current_year - 10
    max_year = current_year - 5

    records_by_year = {}

    try:
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
            'revenue': ['revenues', 'revenuefromcontractwithcustomerexcludingassessedtax', 'salesrevenuenet', 'totalrevenuesandotherincome'],
            'net_income': ['netincomeloss', 'profitloss', 'netincomelossavailabletocommonstockholdersbasic'],
            'eps_diluted': ['earningspersharediluted'],
            'shares_outstanding': ['weightedaveragenumberofdilutedsharesoutstanding', 'commonstocksharesoutstanding', 'entitycommonstocksharesoutstanding'],
            'total_assets': ['assets'],
            'total_liabilities': ['liabilities'],
            'current_assets': ['assetscurrent'],
            'current_liabilities': ['liabilitiescurrent']
        }

        for fy in range(min_year, max_year + 1):
            records_by_year[fy] = {
                'ticker': ticker, 'year': fy, 'period_type': 'Historical',
                'revenue': None, 'net_income': None, 'net_income_margin': None,
                'eps_diluted': None, 'shares_outstanding': None,
                'total_assets': None, 'total_liabilities': None,
                'current_assets': None, 'current_liabilities': None,
                'pe_ratio': None, 'source_provider': 'SEC_EDGAR_10K',
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
            val = row.get(val_col)

            if pd.notnull(val) and val != '':
                try:
                    num_val = float(val)
                    for field, concept_list in concept_map.items():
                        if clean_concept in concept_list and records_by_year[fy][field] is None:
                            records_by_year[fy][field] = num_val
                except (ValueError, TypeError):
                    pass

        valid_records = []
        for fy, rec in records_by_year.items():
            if rec['revenue'] or rec['net_income'] or rec['total_assets']:
                if rec['revenue'] and rec['net_income'] and rec['revenue'] != 0:
                    rec['net_income_margin'] = rec['net_income'] / rec['revenue']

                year_end_price = price_map.get(fy)
                if year_end_price and rec['eps_diluted'] and rec['eps_diluted'] > 0:
                    rec['pe_ratio'] = year_end_price / rec['eps_diluted']

                valid_records.append(rec)

        return valid_records

    except Exception as e:
        print(f"    SEC fetch note for {ticker}: {e}")
        return []

def fetch_yahoo_current_and_consensus(ticker: str, current_year: int, price_map: dict, max_retries: int = 3):
    records = []
    for attempt in range(max_retries):
        try:
            yt = yf.Ticker(ticker)
            info = yt.info or {}
            rev_est = yt.revenue_estimate
            eps_est = yt.earnings_estimate
            shares = info.get('sharesOutstanding')

            ttm_rev = info.get('totalRevenue')
            ttm_eps = info.get('trailingEps')
            ttm_netinc = (ttm_eps * shares) if (ttm_eps and shares) else None
            ttm_margin = (ttm_netinc / ttm_rev) if (ttm_netinc and ttm_rev and ttm_rev != 0) else None
            
            curr_price = info.get('currentPrice') or info.get('regularMarketPrice')
            pe_2026 = (curr_price / ttm_eps) if (curr_price and ttm_eps and ttm_eps > 0) else None

            tot_assets = info.get('totalAssets')
            tot_liab = None
            curr_assets = None
            curr_liab = None

            try:
                bs = yt.balance_sheet
                if bs is not None and not bs.empty:
                    latest_col = bs.columns[0]
                    def get_bs_val(keys):
                        for k in keys:
                            if k in bs.index:
                                val = bs.loc[k, latest_col]
                                if pd.notnull(val):
                                    return float(val)
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
                tot_assets, tot_liab, curr_assets, curr_liab, pe_2026,
                'YahooFinance', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

            if rev_est is not None and '0y' in rev_est.index:
                r_0y = float(rev_est.loc['0y', 'avg']) if pd.notnull(rev_est.loc['0y', 'avg']) else None
                e_0y = float(eps_est.loc['0y', 'avg']) if (eps_est is not None and '0y' in eps_est.index and pd.notnull(eps_est.loc['0y', 'avg'])) else None
                net_inc_0y = (e_0y * shares) if (e_0y and shares) else None
                margin_0y = (net_inc_0y / r_0y) if (net_inc_0y and r_0y and r_0y != 0) else None
                fwd_pe = (curr_price / e_0y) if (curr_price and e_0y and e_0y > 0) else None

                records.append((
                    ticker, current_year, 'Projected',
                    r_0y, net_inc_0y, margin_0y, e_0y, shares,
                    None, None, None, None, fwd_pe,
                    'Yahoo_Consensus', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))

            if rev_est is not None and '+1y' in rev_est.index:
                r_1y = float(rev_est.loc['+1y', 'avg']) if pd.notnull(rev_est.loc['+1y', 'avg']) else None
                e_1y = float(eps_est.loc['+1y', 'avg']) if (eps_est is not None and '+1y' in eps_est.index and pd.notnull(eps_est.loc['+1y', 'avg'])) else None
                net_inc_1y = (e_1y * shares) if (e_1y and shares) else None
                margin_1y = (net_inc_1y / r_1y) if (net_inc_1y and r_1y and r_1y != 0) else None

                records.append((
                    ticker, current_year + 1, 'Projected',
                    r_1y, net_inc_1y, margin_1y, e_1y, shares,
                    None, None, None, None, None,
                    'Yahoo_Consensus', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))
            break

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"    Yahoo fetch note for {ticker}: {e}")

    return records

def enrich_shortlist_history(current_year: int = 2026):
    print("Running SQL Screener...")
    shortlist_df = run_screener()
    if shortlist_df.empty: return

    tickers = shortlist_df['ticker'].tolist()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM financial_records WHERE source_provider = 'Yahoo_Extrapolated'")
    conn.commit()

    for ticker in tickers:
        print(f"\n -> Enriching {ticker}...")

        price_map = fetch_historical_year_end_prices(ticker, current_year - 10, current_year - 1)

        sec_records = fetch_sec_historical_years_5_to_10(ticker, current_year, price_map)
        if sec_records:
            records_tuple = [
                (r['ticker'], r['year'], r['period_type'], r['revenue'], r['net_income'],
                 r['net_income_margin'], r['eps_diluted'], r['shares_outstanding'],
                 r['total_assets'], r['total_liabilities'], r['current_assets'],
                 r['current_liabilities'], r['pe_ratio'], r['source_provider'], r['updated_at'])
                for r in sec_records
            ]
            cursor.executemany("""
            INSERT INTO financial_records 
            (ticker, year, period_type, revenue, net_income, net_income_margin, eps_diluted, shares_outstanding, total_assets, total_liabilities, current_assets, current_liabilities, pe_ratio, source_provider, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, year, period_type) DO UPDATE SET
                revenue = excluded.revenue,
                net_income = excluded.net_income,
                net_income_margin = excluded.net_income_margin,
                eps_diluted = excluded.eps_diluted,
                shares_outstanding = excluded.shares_outstanding,
                total_assets = excluded.total_assets,
                total_liabilities = excluded.total_liabilities,
                current_assets = excluded.current_assets,
                current_liabilities = excluded.current_liabilities,
                pe_ratio = COALESCE(excluded.pe_ratio, pe_ratio),
                source_provider = 'SEC_EDGAR_10K',
                updated_at = excluded.updated_at;
            """, records_tuple)
            conn.commit()
            print(f"    ✓ Sourced {len(sec_records)} deep historical years via SEC 10-K filings.")

        yahoo_records = fetch_yahoo_current_and_consensus(ticker, current_year, price_map)
        if yahoo_records:
            cursor.executemany("""
            INSERT INTO financial_records 
            (ticker, year, period_type, revenue, net_income, net_income_margin, eps_diluted, shares_outstanding, total_assets, total_liabilities, current_assets, current_liabilities, pe_ratio, source_provider, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                pe_ratio = COALESCE(excluded.pe_ratio, pe_ratio),
                source_provider = excluded.source_provider,
                updated_at = excluded.updated_at;
            """, yahoo_records)
            conn.commit()
            print(f"    ✓ Populated 2026 Historical YTD + 2026/2027 Wall Street Consensus.")

        time.sleep(1)

    conn.close()
    print("\nEnrichment complete!")

if __name__ == "__main__":
    enrich_shortlist_history()
