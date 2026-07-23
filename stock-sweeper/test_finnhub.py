import requests
from config import FINNHUB_API_KEY

def test_finnhub_estimates(ticker="AAPL"):
    print(f"--- Testing Finnhub API Estimates for {ticker} ---")
    print(f"API Key: {FINNHUB_API_KEY[:6]}...{FINNHUB_API_KEY[-4:]}\n")

    # 1. Fetch EPS Estimates
    eps_url = f"https://finnhub.io/api/v1/stock/eps-estimate?symbol={ticker}&token={FINNHUB_API_KEY}"
    try:
        eps_res = requests.get(eps_url, timeout=10)
        print(f"EPS Request Status: {eps_res.status_code}")
        if eps_res.status_code == 200:
            eps_data = eps_res.json().get('data', [])
            print(f"Found {len(eps_data)} EPS Consensus Periods:")
            for item in eps_data[:5]:
                print(f"  └─ Period: {item.get('period')} | Avg EPS: ${item.get('epsAvg')} | Number of Analysts: {item.get('numberAnalysts')}")
        else:
            print(f"Error Response: {eps_res.text}")
    except Exception as e:
        print(f"EPS Request Failed: {e}")

    print("\n" + "-"*40 + "\n")

    # 2. Fetch Revenue Estimates
    rev_url = f"https://finnhub.io/api/v1/stock/revenue-estimate?symbol={ticker}&token={FINNHUB_API_KEY}"
    try:
        rev_res = requests.get(rev_url, timeout=10)
        print(f"Revenue Request Status: {rev_res.status_code}")
        if rev_res.status_code == 200:
            rev_data = rev_res.json().get('data', [])
            print(f"Found {len(rev_data)} Revenue Consensus Periods:")
            for item in rev_data[:5]:
                rev_m = (item.get('revenueAvg', 0) or 0) / 1e6
                print(f"  └─ Period: {item.get('period')} | Avg Revenue: ${rev_m:.2f}M | Number of Analysts: {item.get('numberAnalysts')}")
        else:
            print(f"Error Response: {rev_res.text}")
    except Exception as e:
        print(f"Revenue Request Failed: {e}")

if __name__ == "__main__":
    test_finnhub_estimates("AAPL")
