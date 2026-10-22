import os

# Your contact email for SEC EDGAR API compliance
USER_EMAIL = os.environ.get("SEC_USER_EMAIL", "sup.101@hotmail.com")

# Local database file name
DB_NAME = "market_data.db"

# Google Sheets Workbook Name
GOOGLE_SHEET_NAME = "Long Term Stocks"

# Google Service Account credentials file name
GOOGLE_CREDS_FILE = "google_credentials.json"

# Sweeper batch settings
BATCH_SIZE = 50
BATCH_PAUSE_SECONDS = 0.5

# API KEYs (Loaded from environment variables)
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")