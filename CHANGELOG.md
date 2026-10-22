# 📋 Stock Sweeper Changelog

All notable changes, features, bug fixes, and performance optimizations across the **Find Long-Term Stocks (`stock-sweeper`)** repository are documented in this file.

**Legend:**
- ✨ **Features**: New pipeline stages, screening gates, valuation models, or visualizations
- ⚡ **Optimizations**: Rate-limit pacing, concurrency tuning, caching, and network call reductions
- 🐛 **Bug Fixes**: Data cleaning, session/crumb recovery, schema migrations, and edge-case handling
- 🗄️ **Database & Schema**: SQLite table structures, columns, and persistence updates
- 🛠️ **Tooling & Docs**: CLI orchestration, dependencies, and documentation

---

## [Unreleased] — 2026-10-21 (Rate-Limit Pacing, SQLite Caching & Full Dataset Backfill)

### ⚡ Optimizations
- **Tiered 30-Day / 24-Hour Sweep Cache TTL (`sweeper.py`)**: Active mid/large-cap companies (`market_cap >= $300M`) refresh every 24 hours, while inactive/delisted/404 tickers (`is_active = 0`) and deep micro-caps (`< $300M`) are cached for 30 days, reducing future full-market sweeps from ~8,763 tickers to ~3,000 tickers (~12 minutes).
- **24-Hour Enrichment Cache (`enricher.py`, `database.py`)**: Added `last_enriched` timestamp tracking on `company_overview` and non-destructive `ON CONFLICT DO UPDATE` upserts in `sweeper.py` so same-day re-runs skip already-enriched tickers and complete the entire pipeline in ~3 seconds.
- **Eliminated Duplicate Network Calls in `exporter.py`**: Cached `target_mean_price`, `finviz_eps_5y`, `yahoo_lt_growth`, `year_end_price`, `consensus_eps_growth`, and `consensus_rev_growth` directly in SQLite (`market_data.db`) during `enricher.py` so `exporter.py` runs directly from the local database without repeating per-ticker Yahoo/Finviz HTTP requests.
- **Batched Historical Price Downloads**: Added `fetch_batch_historical_year_end_prices()` in `enricher.py` to download 10-year historical prices in multi-ticker chunks (`50` tickers per `yf.download` call) instead of making individual single-ticker requests.
- **Zero-Retry on 404/Delisted Symbols**: Updated `extract_ticker_data()` in `sweeper.py` to immediately record delisted/missing tickers with `is_active = 0` (`_inactive_overview()`) instead of retrying 404 responses 4 times, cutting wasted Yahoo Finance requests by 75% and preventing re-scraping on future runs.
- **Token-Bucket Pacing for Finviz & SEC EDGAR**: Added strict request pacing in `enricher.py` (`>= 0.45s` interval / ~2.2 req/s for Finviz and `>= 0.12s` interval / ~8.3 req/s for SEC EDGAR) to stay safely below Cloudflare and SEC 10 req/s rate limits.

### 🐛 Bug Fixes
- **Dynamic Sector + PEG-Anchored P/E Ceiling (`exporter.py`)**: Replaced unbounded historical median P/E multiples with a dynamic sector-peer and growth-adjusted P/E ceiling (`peg_terminal_ceiling = min(45.0, max(sec_pe * 1.15, sec_pe + expected_g * 85))`) and starting P/E normalization (`starting_pe_ceiling = min(60.0, max(fwd_pe * 1.35, peg_terminal_ceiling * 1.25))`), preventing turnaround stocks with near-zero historical EPS (e.g., 500x trailing P/E) from extrapolating hyper-inflated multiples into 2031.
- **Environment Variable API Key Security (`config.py`, `test_finnhub.py`)**: Moved `FINNHUB_API_KEY` from plaintext in `config.py` to `os.environ.get("FINNHUB_API_KEY", "")` and masked key output in `test_finnhub.py`.
- **Mid-Batch Crumb Expiration Recovery**: Updated `run_sweeper()` in `sweeper.py` to detect partial batch failures (`< 40%` active companies returned in a batch of 50), automatically reset the `yfinance` `curl_cffi` session/crumb (`reset_yfinance_session()`), and retry only the unscraped tickers from that batch.
- **Full 15-Year Timeline & Projection Backfill**: Expanded XBRL/IFRS concept mappings in `enricher.py`, added fallback `0y`/`+1y` consensus projection rows when analyst estimate tables are sparse, and populated base financial columns (`Revenue ($M)`, `Net Income ($M)`, `Net Profit Margin (%)`, `Diluted EPS ($)`, `P/E Ratio`, `Forward P/E`, `Current Ratio`, `Debt to Equity`, `Beta`) across all forecast rows (2028–2031) in `exports/15y_export.csv`.

### 🗄️ Database & Schema
- Added non-destructive `ALTER TABLE` column migrations in `database.py` for `target_mean_price`, `finviz_eps_5y`, and `yahoo_lt_growth` on `company_overview`, and `year_end_price`, `consensus_eps_growth`, and `consensus_rev_growth` on `financial_records`.

---

## [0bba40b] — 2026-10-21
**`feat(pipeline): add FCF/ROIC quality gates, linear P/E decay projections, resilient sweeper, and end-to-end automation`**

### ✨ Features
- **FCF & ROIC Quality Hurdles (`screener.py`, `sweeper.py`)**: Extracted Operating Cash Flow, Capital Expenditures, Free Cash Flow (`OCF - CapEx`), and Return on Invested Capital (`NOPAT / Invested Capital` at a 21% baseline tax rate, with ROE/ROA fallbacks). Added `free_cash_flow > 0` and `roic >= 10%` gates to `run_screener()`.
- **Linear P/E Multiple Decay (`exporter.py`)**: Implemented Option A multiple compression across forecast years 2–5, decaying each company's trend-weighted P/E linearly toward its historical median P/E (`terminal_pe_target`).
- **4-Method Blended Valuation Engine (`exporter.py`)**: Decoupled Method 1 (historical EPS CAGR) and Method 2 (independent historical Revenue CAGR × trend-weighted Net Profit Margin) alongside Method 3 (Yahoo LT growth) and Method 4 (Finviz 5Y EPS growth), exporting to `exports/15y_export.csv`.
- **Return Distribution Visualizations (`plot_summary_returns.py`)**: Added 4-panel distribution and leaderboard plotting (`exports/summary_returns_distribution.png`).
- **Master Pipeline Runner (`run_pipeline.py`, `utils.py`, `INSTRUCTIONS.md`)**: Added end-to-end CLI orchestration (`--skip-sweep`, `--limit`, `--init-only`) and cross-platform file opener (`utils.open_file()`).

### ⚡ Optimizations
- **Multi-Threaded Market Sweep (`sweeper.py`)**: Parallelized ticker ingestion with `ThreadPoolExecutor` and reduced `BATCH_PAUSE_SECONDS` to `0.5s`.

### 🐛 Bug Fixes
- **24-Hour Checkpoint Resumption (`sweeper.py`)**: Replaced strict `DATE(last_scraped) = today` check with a rolling 24-hour window (`last_scraped >= datetime('now', '-24 hours')`) and `MAX(ticker)` index resumption so overnight runs do not restart from ticker `A` at midnight.
- **Ticker Symbol Hygiene (`sec_tickers.py`)**: Excluded SPACs (`ACQUISITION CORP`, `BLANK CHECK`) and 5-letter warrants/units/rights/preferreds ending in `W`/`U`/`R`/`P`, while preserving hyphenated dual-class shares (`BRK-B`, `BF-B`).

### 🗄️ Database & Schema
- Replaced `create_tables()` with `init_db(reset=False)` in `database.py` and added `free_cash_flow`, `roic`, `operating_cash_flow`, and `capital_expenditures` columns.

---

## [2f8084c] — 2026-07-23
**`feat: bound multi-year projection growth rates and add method distribution analysis script`**

### ✨ Features
- **Ranked Summary Leaderboard (`generate_summary.py`)**: Created summary generator to calculate 3Y/5Y projected prices, total profit `%`, and 5Y annualized CAGR `%` into `exports/screener_summary_leaderboard.csv`.
- **Growth Method Distribution Analysis (`analyze_method_distributions.py`)**: Added diagnostic script and histogram visualization (`exports/method_growth_histograms.png`) comparing raw growth rate distributions across M1–M4.
- **Finnhub Sandbox (`test_finnhub.py`, `config.py`)**: Added Finnhub API key configuration and connectivity test script.

### 🐛 Bug Fixes
- **Bounded Growth Outliers (`exporter.py`)**: Clamped historical and analyst growth inputs (`[-35%, +45%]`) and added winsorized trend-weighted averaging (`calculate_trend_weighted_metric` & `calculate_robust_metric_unweighted`) to prevent extreme single-year EPS spikes from distorting 5-year price targets.

---

## [8a0f5f8] — 2026-07-23
**`Refine SEC fact extraction, ratio calculations, and CSV export formatting`**

### ✨ Features
- **Finviz 5Y EPS Growth Scraper (`enricher.py`)**: Added `fetch_finviz_eps_next_5y()` using `BeautifulSoup` to extract 5-year analyst EPS growth rates.
- **Historical Year-End Price & P/E Backfill (`enricher.py`)**: Added `fetch_historical_year_end_prices()` via `yfinance` to compute historical annual P/E ratios (`year_end_price / eps_diluted`) across 10-K records.
- **Multi-Method Forecast Columns (`exporter.py`)**: Expanded CSV export with balance sheet health ratios (`Total Assets / Total Liabilities`, `Current Ratio`, `Debt to Equity`) and explicit M1–M4 projection columns.

### 🐛 Bug Fixes
- **SEC XBRL Concept Normalization (`enricher.py`)**: Improved XBRL taxonomy parsing (`us-gaap` concept stripping and `FY` fiscal period filtering) in `fetch_sec_historical_years_5_to_10()`.

---

## [dfcaccb] — 2026-07-22
**`feat: implement 10-year SEC EDGAR enrichment with smart caching and 2-stage market funnel`**

### ✨ Features
- **10-Year SEC EDGAR Enrichment (`enricher.py`)**: Integrated `edgartools` (`Company(ticker).get_facts()`) to pull 10-year historical 10-K fundamentals (`Revenue`, `Net Income`, `Diluted EPS`, `Shares`, `Assets`, `Liabilities`) and Wall Street `0y`/`+1y` consensus estimates.
- **Clean Dataset Exporter (`exporter.py`)**: Added initial exporter to join `company_overview` and `financial_records` into a formatted CSV timeline.

### ⚡ Optimizations
- **Two-Stage Basic Gate Funnel (`sweeper.py`)**: Added `passes_basic_gates` pre-check in `extract_ticker_data()` so expensive `.financials` and `.balance_sheet` API calls are only executed for companies passing preliminary Market Cap, D/E, Current Ratio, Margin, and Growth thresholds.

---

## [7b312d3] — 2026-07-22
**`Implement updated schema, batch sweeper, and custom 8-rule SQL screener`**

### ✨ Features
- **8-Rule Quantitative SQL Screener (`screener.py`)**: Implemented `run_screener()` filtering on Market Cap ($\ge \$1\text{B}$), Current Ratio ($\ge 0.5$), Debt-to-Equity ($\le 2.0$), Beta ($\ge 0.7$), Operating Margins ($\ge 10\%$), Earnings Growth ($\ge 5\%$), Revenue Growth ($\ge 5\%$), and Forward P/E ($\ge 5.0$).
- **Batch Market Sweeper (`sweeper.py`)**: Added `run_sweeper()` with `BATCH_SIZE = 50` checkpoint commits and daily `last_scraped` caching.
- **Google Sheets Sync (`sheets_sync.py`)**: Added `gspread` integration to sync database tables with Google Sheets.

### 🗄️ Database & Schema
- Added `is_active`, `source_provider`, and `last_scraped` tracking columns to `company_overview` in `database.py`.

---

## [9078aba] — 2026-07-22
**`Implement core foundation, SEC EDGAR ticker fetcher, and yfinance extraction engine`**

### ✨ Features
- **SEC EDGAR Ticker Directory Fetcher (`sec_tickers.py`)**: Added SEC-compliant `fetch_sec_tickers()` to ingest active equity symbols from `https://www.sec.gov/files/company_tickers.json`.
- **Yahoo Finance Extraction Engine (`sweeper.py`)**: Created `extract_ticker_data()` to pull company overview metrics, historical income statements/balance sheets, and `0y`/`+1y` analyst estimates via `yfinance`.

### 🗄️ Database & Schema
- Initialized SQLite database (`market_data.db`) in `database.py` with `company_overview` and `financial_records` tables.

### 🛠️ Tooling & Docs
- Added `config.py`, `requirements.txt`, and `.gitignore`.

---

## [4fef49d] — 2026-07-22
**`Initial commit`**

### 🛠️ Tooling & Docs
- Initialized repository with `README.md`.
