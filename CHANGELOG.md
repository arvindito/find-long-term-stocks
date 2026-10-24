# 📋 Stock Sweeper Changelog

All notable changes, features, bug fixes, and performance optimizations across the **Find Long-Term Stocks (`stock-sweeper`)** repository are documented in this file.

**Legend:**
- ✨ **Features**: New pipeline stages, screening gates, valuation models, or visualizations
- ⚡ **Optimizations**: Rate-limit pacing, concurrency tuning, caching, and network call reductions
- 🐛 **Bug Fixes**: Data cleaning, session/crumb recovery, schema migrations, and edge-case handling
- 🗄️ **Database & Schema**: SQLite table structures, columns, and persistence updates
- 🛠️ **Tooling & Docs**: CLI orchestration, dependencies, and documentation

---

## [Unreleased] — 2026-10-23 (Architecture Refactor, Valuation Distortion Fixes, Asymmetric Moonshot Track & Dual-Survivor Log)

### ✨ Features
- **Decoupled Interactive Localhost Dashboard (`dashboard/app.py`, `dashboard/static/index.html`, `dashboard/static/app.js`, `dashboard/run_dashboard.sh`)**: Built a standalone 7-tab FastAPI + Plotly.js + Tailwind CSS financial terminal at `http://localhost:8050` reading `../stock-sweeper/market_data.db` in read-only mode (`?mode=ro`). Includes a live "What-If" Screener Sandbox across all 7,300 active stocks with step-by-step gate attrition waterfall charts, a customizable 7-Pillar Moat Weighter, a 15-Year 4-Method Valuation Time-Machine (`2016–2031`) with share-drift toggles, an Asymmetric 5x Moonshot Lab, a Mega-Cap Swing-Trade Desk, and a Head-to-Head Stock Comparator & Barbell Portfolio Builder.
- **Four-Tier Portfolio Categorization & `$500M` Floor (`utils.py`, `screener.py`, `sweeper.py`)**: Lowered the main compounder screener floor from `$1B` to `$500M` (`204` shortlisted compounders) and standardized portfolio tiers across the entire codebase:
  - `Small-Cap ($500M-$5B)`
  - `Mid-Cap ($5B-$50B)`
  - `Large-Cap ($50B-$1T)`
  - `Mega-Cap ($1T+)`
  - `Micro-Cap (<$500M)`
- **Uniform Main Compounder Pipeline + Separate Mega-Cap Watchlist (`qualitative_scorer.py`)**: Applied identical post-enrichment compounder hurdles across all market-cap tiers (`Total Moat Score >= 70.0`, `3Y Share Dilution CAGR <= 3.5%/yr`, and `5Y Projected CAGR >= 8.0%/yr`) with zero special exemptions in `exports/qualitative_moat_leaderboard.csv`, while publishing all `$1T+` Mega-Caps separately to `exports/mega_cap_watch_leaderboard.csv` for swing-trading and valuation anchoring.
- **Asymmetric 5x Moonshot / Inflection Screener & Scorer (`moonshot_screener.py`)**: Added Step 9 to screen `$300M–$10B` high-torque inflection plays (`Revenue Growth 25%–300%` with `>= 30%` top/bottom-line acceleration, `Current Ratio >= 1.5`, `Debt/Equity <= 1.0`, `Operating Margin >= -15%`, `Forward P/E > 0`, `Beta >= 1.15`) and score them on a **100-Point Asymmetric Inflection Framework** (Survival Runway, Growth Velocity, Operating Torque, 3Y Re-Rating Upside, Insider & Size Torque), exporting to `exports/asymmetric_moonshot_leaderboard.csv`.
- **Persistent Dual-Survivor Overlap Tracker (`moonshot_screener.py`)**: Automatically detects companies that survive **both** the Main Compounder Screener and the Asymmetric Moonshot Screener on any run, highlights them in the console, and maintains a cumulative historical ledger in `exports/dual_survivor_overlap_log.csv` (`First Seen Date`, `Last Seen Date`, `Times Appeared`, `Active on Latest Run`).
- **Upgraded 7-Pillar Qualitative Moat Scorer (`qualitative_scorer.py`)**:
  - **Pillar 1 (15 pts)**: Separated Net Open-Market Insider Buying (`15 pts`) from Zero Activity / Neutral (`10 pts`).
  - **Pillar 5 (20 pts) & Pillar 6 (15 pts)**: Upgraded to use true GAAP `Gross Profit` and `SG&A Expense` extracted from SEC EDGAR 10-K XBRL tags and `yfinance` financials.
  - **Pillar 7 (15 pts — Option B)**: Applied uniformly across all tiers—awards `15 pts` for Top 500 Global Brand recognition, or scores up to `15 pts` on Self-Funding Revenue Growth (`10%–28%` + `FCF > 0`, up to `8 pts`) and Share Dilution Discipline (`3Y Share CAGR <= +1.2%`, up to `7 pts`).

### 🐛 Bug Fixes
- **Foreign Currency / ADR Consensus Normalization (`exporter.py`, `enricher.py`)**: Added currency ratio detection and FX scaling so foreign-currency consensus EPS/Revenue estimates (e.g., `KARO` in `ZAR`, `TSM` in `TWD`, `SONY` in `JPY`) are normalized to USD before computing forward P/E and 5-year price targets.
- **Smooth Year 1 $\rightarrow$ Year 5 P/E Multiple Transition (`exporter.py`)**: Anchored Year 1 `robust_pe` to the current forward P/E regime and interpolated smoothly from Year 1 to Year 5 `terminal_pe_target`, eliminating artificial 2027 $\rightarrow$ 2028 single-year step-function jumps (e.g., `CRM`, `RAMP`, `CARG`).
- **Realistic 5Y Growth Bounds & Mean-Reverting Decay (`exporter.py`, `enricher.py`)**: Removed the single-quarter YoY `earningsGrowth` fallback from `yahoo_lt_growth`, bounded 5Y growth inputs to `[-25%, +30%]`, and added `_compounded_growth_factor()` to gently decay excess growth above `18%/yr`.
- **Stock-Split, ADR Ratio & Dual-Class Share Count Normalization (`exporter.py`, `enricher.py`)**: Used `max(sharesOutstanding, impliedSharesOutstanding)` in `enricher.py` and normalized historical YoY share-count discontinuities (`>1.75x` or `<0.55x`) in `exporter.py` so split stocks (`NVDA`, `AVGO`), ADRs (`TSM`), and dual-class shares (`GOOGL`) compute accurate split-adjusted EPS and `3Y Share Dilution CAGR (%)`.

### 🛠️ Tooling, Architecture & Database
- **Codebase Consolidation (`config.py`, `utils.py`, `database.py`)**: Centralized all export paths, numeric helpers (`is_valid_num()`, `clean_float()`), file descriptor limits (`ensure_file_limits()`), tier classification (`classify_market_cap_tier()`), and WAL-enabled SQLite connections (`get_db_connection()`).
- **Tighter Tiered Sweep Cache TTL (`sweeper.py`)**: Lowered the 24-hour refresh threshold from `$300M` to `$100M` (`market_cap >= $100M`) and shortened the inactive / deep micro-cap (`< $100M`) refresh TTL from 30 days to **7 days** so rising small-caps are caught weekly.
- **macOS Daily LaunchAgent Automation (`run_daily_job.sh`, `~/Library/LaunchAgents/com.stocksweeper.daily.plist`)**: Added a date-stamped daily runner (`run_daily_job.sh`) and registered a macOS `launchd` agent (`com.stocksweeper.daily`) with `RunAtLoad` and hourly wake checks so the pipeline runs automatically once per calendar day whenever the Mac is turned on or woken up.
- **Schema Migrations (`database.py`)**: Added non-destructive `ALTER TABLE` migrations for `company_overview.gross_margins`, `financial_records.gross_profit`, and `financial_records.sga_expense`.

---

## [2026-10-22] — Valuation Realism, Standardized Leaderboards & 7-Pillar Qualitative Moat Scorer

### ✨ Features
- **3-Year Share Count Drift (`exporter.py`, `generate_summary.py`)**: Added trailing 3-year historical share count CAGR (`share_cagr`, clipped to `[-10%, +15%]`) so projected share counts scale dynamically across forecast years `k = 1..4` (`proj_shares = shares_m * ((1 + share_cagr) ** k)`), and exposed `3Y Share Dilution CAGR (%)` in the leaderboards.
- **Standardized Export Filenames & Historical Price Checkpoints (`exporter.py`, `generate_summary.py`)**:
  - Renamed `exports/15y_export.csv` $\rightarrow$ `exports/valuation_model_timeline.csv` and `exports/screener_summary_leaderboard.csv` $\rightarrow$ `exports/fundamental_screener_leaderboard.csv`.
  - Added `10Y-6Y Historical Max/Min Price ($)`, `5Y Ago`, `4Y Ago`, `3Y Ago`, and `1Y Ago Price ($)` checkpoints.
- **7-Pillar Qualitative Moat Scorer (`qualitative_scorer.py`)**: Added standalone 100-point qualitative moat evaluation across Insider Alignment, CEO Ownership, ROIC Trajectory, Culture/Governance, Gross Margin Pricing Power, SG&A Operating Leverage, and Brand Recognition.

### 🗄️ Database & Schema
- Enabled SQLite Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and `PRAGMA synchronous = NORMAL;` across all connections in `database.py`.

---

## [2026-10-21] — Rate-Limit Pacing, SQLite Caching & Full Dataset Backfill

### ⚡ Optimizations
- **Tiered 30-Day / 24-Hour Sweep Cache TTL (`sweeper.py`)**: Active mid/large-cap companies (`market_cap >= $300M`) refresh every 24 hours, while inactive/delisted/404 tickers (`is_active = 0`) and deep micro-caps (`< $300M`) are cached for 30 days, reducing future full-market sweeps from ~8,763 tickers to ~3,000 tickers (~12 minutes).
- **24-Hour Enrichment Cache (`enricher.py`, `database.py`)**: Added `last_enriched` timestamp tracking on `company_overview` and non-destructive `ON CONFLICT DO UPDATE` upserts in `sweeper.py` so same-day re-runs skip already-enriched tickers and complete the entire pipeline in ~3 seconds.
- **Eliminated Duplicate Network Calls in `exporter.py`**: Cached `target_mean_price`, `finviz_eps_5y`, `yahoo_lt_growth`, `year_end_price`, `consensus_eps_growth`, and `consensus_rev_growth` directly in SQLite (`market_data.db`) during `enricher.py` so `exporter.py` runs directly from the local database without repeating per-ticker Yahoo/Finviz HTTP requests.
- **Batched Historical Price Downloads**: Added `fetch_batch_historical_year_end_prices()` in `enricher.py` to download 10-year historical prices in multi-ticker chunks (`50` tickers per `yf.download` call) instead of making individual single-ticker requests.
- **Zero-Retry on 404/Delisted Symbols**: Updated `extract_ticker_data()` in `sweeper.py` to immediately record delisted/missing tickers with `is_active = 0` (`_inactive_overview()`) instead of retrying 404 responses 4 times, cutting wasted Yahoo Finance requests by 75% and preventing re-scraping on future runs.
- **Token-Bucket Pacing for Finviz & SEC EDGAR**: Added strict request pacing in `enricher.py` (`>= 0.45s` interval / ~2.2 req/s for Finviz and `>= 0.12s` interval / ~8.3 req/s for SEC EDGAR) to stay safely below Cloudflare and SEC 10 req/s rate limits.

### 🐛 Bug Fixes
- **Dynamic Sector + PEG-Anchored P/E Ceiling (`exporter.py`)**: Replaced unbounded historical median P/E multiples with a dynamic sector-peer and growth-adjusted P/E ceiling (`peg_terminal_ceiling = min(45.0, max(sec_pe * 1.15, sec_pe + expected_g * 85))`) and starting P/E normalization (`starting_pe_ceiling = min(60.0, max(fwd_pe * 1.35, peg_terminal_ceiling * 1.25))`), preventing turnaround stocks with near-zero historical EPS (e.g., 500x trailing P/E) from extrapolating hyper-inflated multiples into 2031.
- **Environment Variable API Key Security (`config.py`)**: Moved `FINNHUB_API_KEY` from plaintext in `config.py` to `os.environ.get("FINNHUB_API_KEY", "")`.
- **Mid-Batch Crumb Expiration Recovery**: Updated `run_sweeper()` in `sweeper.py` to detect partial batch failures (`< 40%` active companies returned in a batch of 50), automatically reset the `yfinance` `curl_cffi` session/crumb (`reset_yfinance_session()`), and retry only the unscraped tickers from that batch.
- **Full 15-Year Timeline & Projection Backfill**: Expanded XBRL/IFRS concept mappings in `enricher.py`, added fallback `0y`/`+1y` consensus projection rows when analyst estimate tables are sparse, and populated base financial columns (`Revenue ($M)`, `Net Income ($M)`, `Net Profit Margin (%)`, `Diluted EPS ($)`, `P/E Ratio`, `Forward P/E`, `Current Ratio`, `Debt to Equity`, `Beta`) across all forecast rows (2028–2031).

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
