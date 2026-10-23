import gspread
from config import GOOGLE_CREDS_FILE, GOOGLE_SHEET_NAME
from screener import run_screener


def sync_to_google_sheets():
    """
    Runs the SQL screener and pushes the shortlisted stocks
    directly to Google Sheets.
    """
    print("Running SQL Screener...")
    df = run_screener()

    if df.empty:
        print("No stocks passed screening criteria. Skipping Google Sheets update.")
        return

    try:
        gc = gspread.service_account(filename=GOOGLE_CREDS_FILE)

        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
        except gspread.SpreadsheetNotFound:
            print(f"Spreadsheet '{GOOGLE_SHEET_NAME}' not found. Creating a new one...")
            sh = gc.create(GOOGLE_SHEET_NAME)

        worksheet = sh.sheet1
        worksheet.title = "Screener Shortlist"
        worksheet.clear()

        display_df = df.copy()
        display_df["market_cap"] = (display_df["market_cap"] / 1e9).round(2)
        display_df["free_cash_flow"] = (display_df["free_cash_flow"] / 1e6).round(2)

        rename_map = {
            "ticker": "Ticker",
            "company_name": "Company Name",
            "sector": "Sector",
            "industry": "Industry",
            "market_cap": "Market Cap ($B)",
            "market_cap_tier": "Market Cap Tier",
            "current_price": "Price ($)",
            "forward_pe": "Forward P/E",
            "earnings_growth": "EPS Growth (YoY)",
            "revenue_growth": "Rev Growth (YoY)",
            "operating_margins": "Operating Margin",
            "current_ratio": "Current Ratio",
            "debt_to_equity": "Debt / Equity",
            "beta": "Beta",
            "free_cash_flow": "Free Cash Flow ($M)",
            "roic": "ROIC",
        }
        display_df.rename(columns=rename_map, inplace=True)
        display_df = display_df.fillna("")

        data_to_write = [display_df.columns.values.tolist()] + display_df.values.tolist()
        worksheet.update("A1", data_to_write)

        print(f"Successfully synced {len(display_df)} stocks to Google Sheet: '{GOOGLE_SHEET_NAME}'")
        print(f"Sheet URL: {sh.url}")

    except FileNotFoundError:
        print(f"\n[Error] '{GOOGLE_CREDS_FILE}' not found.")
        print(f"Please place your Google Service Account key as '{GOOGLE_CREDS_FILE}' in this directory.")
    except Exception as e:
        print(f"\n[Error] Google Sheets sync failed: {e}")


if __name__ == "__main__":
    sync_to_google_sheets()
