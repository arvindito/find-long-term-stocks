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
            if not raw_symbol:
                continue
                
            # Normalize SEC format (BRK-B) to Yahoo Finance format (BRK.B)
            symbol = raw_symbol.replace('-', '.')
            
            # Filter out warrants, units, and preferred share symbols (e.g., AAPLW, PR-A)
            # Standard US equity tickers are typically <= 4 letters, or 5 if a dual-class share (like GOOGL / BRK.B)
            if re.match(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$', symbol):
                valid_tickers.add(symbol)
                
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
