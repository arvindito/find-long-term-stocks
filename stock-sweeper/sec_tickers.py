import requests
import re
from config import USER_EMAIL

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def fetch_sec_tickers(user_email: str = USER_EMAIL) -> list[str]:
    """
    Fetches the master ticker list from SEC EDGAR.
    SEC guidelines mandate a descriptive User-Agent header (App/1.0 email).
    """
    headers = {
        'User-Agent': f'StockSweeper/1.0 ({user_email})'
    }

    try:
        response = requests.get(SEC_TICKERS_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        valid_tickers = set()

        for entry in data.values():
            raw_symbol = entry.get('ticker', '').strip().upper()
            title = entry.get('title', '').upper()
            if not raw_symbol:
                continue

            # Exclude SPACs / blank check shells and preferred/unit/warrant series
            if 'ACQUISITION CORP' in title or 'BLANK CHECK' in title:
                continue

            # Keep standard 1-4 letter tickers, dual-class share tickers (e.g., BRK-B, BF-B, HEI-A),
            # and 5-letter common stocks (excluding 5-letter warrants/units/rights/preferreds ending in W/U/R/P)
            if re.match(r'^[A-Z]{1,4}(-[A-B])?$', raw_symbol) or (
                re.match(r'^[A-Z]{5}$', raw_symbol) and raw_symbol[-1] not in ('W', 'U', 'R', 'P')
            ):
                valid_tickers.add(raw_symbol)

        sorted_tickers = sorted(list(valid_tickers))
        print(f"Successfully fetched {len(sorted_tickers)} active tickers from SEC EDGAR.")
        return sorted_tickers

    except Exception as e:
        print(f"Error fetching SEC ticker directory: {e}")
        return []


if __name__ == "__main__":
    tickers = fetch_sec_tickers()
    if tickers:
        print(f"Sample tickers (first 10): {tickers[:10]}")
