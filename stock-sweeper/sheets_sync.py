import gspread
import pandas as pd
from screener import run_screener

# Path to your Google Service Account Credentials JSON file
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_NAME = "Stock Sweeper Dashboard"

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
        # Authenticate with Google Sheets API
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        
        # Open existing spreadsheet or create a new one
        try:
            sh = gc.open(SPREADSHEET_NAME)
        except gspread.SpreadsheetNotFound:
            print(f"Spreadsheet '{SPREADSHEET_NAME}' not found. Creating a new one...")
            sh = gc.create(SPREADSHEET_NAME)
            # Share with your own email if needed: sh.share('your_email@gmail.com', perm_type='user', role='writer')
            
        worksheet = sh.sheet1
        worksheet.title = "Screener Shortlist"
        
        # Clear existing sheet content
        worksheet.clear()
        
        # Prepare Data for Google Sheets
        # Format columns cleanly (e.g. Market Cap in Billions, percentages formatted)
        display_df = df.copy()
        display_df['market_cap'] = display_df['market_cap'] / 1e9  # Convert to $ Billions
        
        # Rename headers for human readability
        display_df.columns = [
            'Ticker', 'Company Name', 'Sector', 'Industry', 'Market Cap ($B)',
            'Price ($)', 'Forward P/E', 'EPS Growth (YoY)', 'Rev Growth (YoY)',
            'Operating Margin', 'Current Ratio', 'Debt / Equity', 'Beta'
        ]
        
        # Write Headers + Rows
        data_to_write = [display_df.columns.values.tolist()] + display_df.values.tolist()
        worksheet.update('A1', data_to_write)
        
        print(f"Successfully synced {len(display_df)} stocks to Google Sheet: '{SPREADSHEET_NAME}'")
        print(f"Sheet URL: {sh.url}")

    except FileNotFoundError:
        print(f"\n[Error] '{CREDENTIALS_FILE}' not found.")
        print("Please place your Google Service Account key as 'credentials.json' in this directory.")
    except Exception as e:
        print(f"\n[Error] Google Sheets sync failed: {e}")

if __name__ == "__main__":
    sync_to_google_sheets()
