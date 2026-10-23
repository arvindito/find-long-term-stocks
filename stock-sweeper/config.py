import os

# Contact email for SEC EDGAR API compliance (User-Agent header)
USER_EMAIL = os.environ.get("SEC_USER_EMAIL", "sup.101@hotmail.com")

# Local SQLite database file path
DB_NAME = "market_data.db"

# Export directory and standardized artifact paths
EXPORT_DIR = "exports"
TIMELINE_CSV = os.path.join(EXPORT_DIR, "valuation_model_timeline.csv")
FUNDAMENTAL_LEADERBOARD_CSV = os.path.join(EXPORT_DIR, "fundamental_screener_leaderboard.csv")
QUALITATIVE_MOAT_CSV = os.path.join(EXPORT_DIR, "qualitative_moat_leaderboard.csv")
MEGA_CAP_WATCH_CSV = os.path.join(EXPORT_DIR, "mega_cap_watch_leaderboard.csv")
MOONSHOT_LEADERBOARD_CSV = os.path.join(EXPORT_DIR, "asymmetric_moonshot_leaderboard.csv")
DUAL_SURVIVOR_LOG_CSV = os.path.join(EXPORT_DIR, "dual_survivor_overlap_log.csv")
RETURNS_PLOT_PNG = os.path.join(EXPORT_DIR, "projected_returns_distribution.png")
METHOD_GROWTH_CSV = os.path.join(EXPORT_DIR, "method_growth_rates.csv")
METHOD_GROWTH_PNG = os.path.join(EXPORT_DIR, "method_growth_histograms.png")

# Sweeper batch settings
BATCH_SIZE = 50
BATCH_PAUSE_SECONDS = 0.5

# Optional external integrations
GOOGLE_SHEET_NAME = "Long Term Stocks"
GOOGLE_CREDS_FILE = "google_credentials.json"
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
