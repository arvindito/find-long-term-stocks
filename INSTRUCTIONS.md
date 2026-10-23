# Master AI Blueprint Prompt — Recreating the Stock Sweeper Engine From Scratch

> **Purpose of This File:** Copy and paste the prompt below into an agentic coding AI to recreate the entire **Stock Sweeper** multi-tier compounder & asymmetric moonshot system from a blank directory.

---

## Prompt

Act as a Principal Quantitative Software Architect and Equity Research Engineer. Build an autonomous, modular Python equity screening, 15-year valuation modeling, qualitative moat scoring, and asymmetric moonshot discovery engine inside a `stock-sweeper/` workspace using SQLite (`market_data.db`), `yfinance`, `edgartools` (SEC EDGAR XBRL API), `BeautifulSoup` (Finviz & OpenInsider), `pandas`, `numpy`, `matplotlib`, and `seaborn`.

### 1. Portfolio Strategy & Market Cap Tiers
The system serves a barbell portfolio strategy across four standardized market-cap tiers (`classify_market_cap_tier()` in `utils.py`):
- **Small-Cap (`$500M–$5B`)**
- **Mid-Cap (`$5B–$50B`)**
- **Large-Cap (`$50B–$1T`)**
- **Mega-Cap (`$1T+`)**
- **Micro-Cap (`<$500M`)**

It operates **3 parallel analytical routes** from a single unified SQLite database (`market_data.db`):
1. **Route 1 — Core Quality Compounders ($\ge \$500\text{M}$):** High-ROIC, free-cash-flow positive compounders modeled over a 10-year historical + 5-year forward timeline and filtered through a uniform 100-point **7-Pillar Qualitative Moat Scorer**.
2. **Route 2 — Asymmetric 5x Moonshots (`$300M–$10B`):** A dedicated 1% portfolio sleeve screener targeting high-torque inflection plays (6-month to 3-year horizon) that have fortress liquidity (`Current Ratio >= 1.5`, `Debt/Equity <= 1.0`), explosive growth (`Revenue Growth 25%–300%`), and are crossing into profitability (`Operating Margin >= -15%` with `Forward P/E > 0`).
3. **Route 3 — Dual-Survivor Overlap Tracker:** Automatically detects and logs rare companies that simultaneously survive **both** Route 1 and Route 2, maintaining a persistent, cumulative historical CSV ledger (`exports/dual_survivor_overlap_log.csv`) across runs.

---

### 2. Modular File Architecture to Implement

1. **`config.py`**:
   - Centralize `USER_EMAIL` (for SEC EDGAR User-Agent compliance), `DB_NAME = "market_data.db"`, `EXPORT_DIR = "exports"`, and the 6 standardized CSV output paths:
     - `TIMELINE_CSV = "exports/valuation_model_timeline.csv"`
     - `FUNDAMENTAL_LEADERBOARD_CSV = "exports/fundamental_screener_leaderboard.csv"`
     - `QUALITATIVE_MOAT_CSV = "exports/qualitative_moat_leaderboard.csv"`
     - `MEGA_CAP_WATCH_CSV = "exports/mega_cap_watch_leaderboard.csv"`
     - `MOONSHOT_LEADERBOARD_CSV = "exports/asymmetric_moonshot_leaderboard.csv"`
     - `DUAL_SURVIVOR_LOG_CSV = "exports/dual_survivor_overlap_log.csv"`
     - `RETURNS_PLOT_PNG = "exports/projected_returns_distribution.png"`

2. **`utils.py`**:
   - `ensure_file_limits(4096)`: Raise OS `RLIMIT_NOFILE` so multi-threaded HTTP/SQLite calls never hit `Errno 24: Too many open files`.
   - `is_valid_num(val)` & `clean_float(val, default=None)`: Guard against `None`, `NaN`, and `Inf`.
   - `classify_market_cap_tier(market_cap_usd)`: Return `Mega-Cap ($1T+)`, `Large-Cap ($50B-$1T)`, `Mid-Cap ($5B-$50B)`, `Small-Cap ($500M-$5B)`, or `Micro-Cap (<$500M)`.
   - `open_file(filepath)`: Cross-platform non-blocking file opener that respects `HEADLESS=1` / `CI=1`.

3. **`database.py`**:
   - Provide `get_db_connection(db_name)` that always sets `PRAGMA journal_mode = WAL;` and `PRAGMA synchronous = NORMAL;`.
   - Provide `init_db(reset=False)` with non-destructive `CREATE TABLE IF NOT EXISTS` and automatic `ALTER TABLE` column migrations for:
     - `company_overview`: `ticker (PK)`, `company_name`, `sector`, `industry`, `market_cap`, `current_price`, `beta`, `current_ratio`, `debt_to_equity`, `gross_margins`, `operating_margins`, `earnings_growth`, `revenue_growth`, `forward_pe`, `free_cash_flow`, `roic`, `target_mean_price`, `finviz_eps_5y`, `yahoo_lt_growth`, `is_active`, `source_provider`, `last_scraped`, `last_enriched`.
     - `financial_records`: `ticker`, `year`, `period_type ('Historical'|'Projected')`, `revenue`, `gross_profit`, `sga_expense`, `net_income`, `net_income_margin`, `eps_diluted`, `shares_outstanding`, `total_assets`, `total_liabilities`, `current_assets`, `current_liabilities`, `operating_cash_flow`, `capital_expenditures`, `free_cash_flow`, `pe_ratio`, `year_end_price`, `consensus_eps_growth`, `consensus_rev_growth`, `source_provider`, `updated_at`, with `UNIQUE(ticker, year, period_type)`.

4. **`sec_tickers.py`**:
   - Download `https://www.sec.gov/files/company_tickers.json` with a compliant `User-Agent` header.
   - Filter out SPACs (`ACQUISITION CORP`, `BLANK CHECK`) and 5-letter warrants/units/rights/preferreds ending in `W`, `U`, `R`, `P`, while preserving hyphenated dual-class tickers (`BRK-B`, `HEI-A`).

5. **`sweeper.py`**:
   - Implement a 2-stage concurrent market sweeper (`ThreadPoolExecutor(max_workers=8)`, `BATCH_SIZE = 50`).
   - **Tiered Cache TTL**:
     - Active companies with `market_cap >= $100M`: refresh every **24 hours**.
     - Inactive/delisted (`is_active = 0`) or deep micro-caps (`< $100M`): refresh every **7 days**.
   - **Stage 1 vs. Stage 2 Funnel**:
     - Pull `.info` for all pending tickers. Immediately mark 404/delisted symbols as `is_active = 0` without retrying.
     - For companies passing preliminary gates (`market_cap >= $450M`, `current_ratio >= 0.4`, `debt_to_equity <= 2.2`, `operating_margins >= 8%`, `revenue_growth >= 3%`, `earnings_growth >= 3%`, `forward_pe >= 4.0`), pull `.financials`, `.balance_sheet`, and `.cashflow` to compute `free_cash_flow = OCF - CapEx`, `roic = (Operating Income * (1 - 0.21)) / (Total Assets - Current Liabilities - Cash)`, `gross_profit`, and `sga_expense`.
   - Include automatic `curl_cffi` session/crumb reset (`reset_yfinance_session()`) if a batch returns `< 40%` active companies.

6. **`screener.py` (Main Compounder SQL Screener)**:
   - Filter `company_overview` where `is_active = 1` and:
     - `market_cap >= 500_000_000` (`$500M+`, no upper cap)
     - `current_ratio >= 0.5`
     - `debt_to_equity <= 2.0`
     - `beta >= 0.7`
     - `operating_margins >= 0.10`
     - `earnings_growth >= 0.05`
     - `revenue_growth >= 0.05`
     - `forward_pe >= 5.0`
     - `free_cash_flow > 0`
     - `roic >= 0.10`

7. **`enricher.py` (10-Year SEC 10-K XBRL, Finviz 5Y & Consensus Enricher)**:
   - Enrich the union of the Compounder Shortlist (`run_screener()`) and Moonshot Shortlist (`run_moonshot_screener()`), skipping tickers enriched within the last 24 hours (`last_enriched >= datetime('now', '-24 hours')`).
   - Batch-download 10-year historical year-end prices via `yf.download` (chunks of 50).
   - Pull 10-year historical 10-K XBRL facts via `edgartools` (`Company(ticker).get_facts()`), mapping US-GAAP and IFRS tags for `revenue`, `gross_profit`, `sga_expense`, `net_income`, `eps_diluted`, `shares_outstanding`, `total_assets`, `total_liabilities`, `current_assets`, `current_liabilities`, `operating_cash_flow`, and `capital_expenditures`.
   - Pull `0y` and `+1y` Wall Street consensus EPS & Revenue estimates from `yfinance` and 5Y EPS growth from Finviz (`fetch_finviz_eps_next_5y()`).
   - **Critical Data Normalizations**:
     - Use `max(sharesOutstanding, impliedSharesOutstanding)` so dual-class stocks (`GOOGL`, `META`) reflect total economic share count.
     - Detect foreign financial reporting currencies (`info['financialCurrency'] != info['currency']` or consensus EPS vs. `current_price / forwardPE` mismatch $> 2.2\text{x}$ or $< 0.35\text{x}$) and scale foreign-currency consensus estimates to USD.
     - Never fall back `yahoo_lt_growth` to single-quarter YoY `earningsGrowth`.

8. **`exporter.py` (15-Year Timeline & 4-Method Valuation Model)**:
   - For each shortlisted compounder, build a 15-year ledger (10 historical years + 5 projected years) in `exports/valuation_model_timeline.csv`:
     - **Stock-Split & Share-Class Continuity**: Walk backward through historical `Shares Outstanding (M)`; if any single YoY jump is $> 1.75\text{x}$ or $< 0.55\text{x}$ (e.g., 10-for-1 stock split or ADR ratio change), normalize prior share counts and pre-split historical EPS so `eps_cagr` and `3Y Share Dilution CAGR (%)` (`share_cagr`, clipped to `[-10%, +15%]`) are 100% split-adjusted.
     - **Bounded Growth & Mean-Reverting Decay**: Bound historical/analyst 5Y growth rates (`eps_cagr`, `rev_cagr`, `yahoo_g`, `finviz_g`) to `[-25%, +30%]`, and decay excess growth above `18%/yr` by `12%/yr` across forecast steps $k = 1 \dots 4$.
     - **Smooth Year 1 $\rightarrow$ Year 5 P/E Transition**: Anchor Year 1 `robust_pe` to the current forward P/E regime and interpolate linearly from `robust_pe` in Year 1 to `terminal_pe_target` (`max(sector_pe_floor, min(hist_median_pe, robust_pe, peg_terminal_ceiling))`) in Year 5.
     - Compute 4 price projection methods (`M1: EPS CAGR`, `M2: Rev CAGR × Robust Net Margin`, `M3: Yahoo LT Growth`, `M4: Finviz 5Y Growth`) scaling projected share counts by `shares_m * ((1 + share_cagr) ** k)`.

9. **`generate_summary.py` (`exports/fundamental_screener_leaderboard.csv`)**:
   - Summarize all shortlisted compounders with `Market Cap ($B)`, `Market Cap Tier`, 6 historical price checkpoints (`10Y-6Y Max/Min`, `5Y`, `4Y`, `3Y`, `1Y Ago`), `Current Price ($)`, `3Y Target Price ($)`, `5Y Target Price ($)`, `3Y/5Y Projected Return (%)`, `5Y Projected CAGR (%)`, `3Y Share Dilution CAGR (%)`, `Beta`, `Current Ratio`, `Solvency Ratio (Assets/Liabilities)`, `Terminal Target P/E Multiple`, and `5Y Blended Growth Rate (%)`.

10. **`qualitative_scorer.py` (7-Pillar Qualitative Moat Scorer — 100 Pts)**:
    - Score every compounder across 7 pillars:
      - **Pillar 1 (15 pts) — Form 4 Insider Alignment**: Scrape OpenInsider + `yfinance` insider transactions (`15 pts` for net open-market buying, `10 pts` for zero/neutral activity, `5 pts` for minor routine sales, `2 pts` for heavy selling).
      - **Pillar 2 (10 pts) — CEO & Insider Ownership**: Full points if insider ownership $\ge 0.5\%$ or $\ge \$10\text{M}$.
      - **Pillar 3 (15 pts) — Capital Allocation & ROIC**: Full points for $\text{ROIC} \ge 12\%$ with flat/expanding multi-year capital efficiency.
      - **Pillar 4 (10 pts) — Culture & Governance**: Implied governance/stability score from board, audit, and compensation risk metrics.
      - **Pillar 5 (20 pts) — Pricing Power**: True 5Y GAAP Gross Margin (`gross_profit / revenue`); full points for 5Y Gross Margin $\ge 35\%$ with std dev $\le 2.5\%$.
      - **Pillar 6 (15 pts) — SG&A Operating Leverage**: True 3–5Y GAAP `sga_expense / revenue` linear trend slope; full points when overhead ratio is flat or declining as revenue scales.
      - **Pillar 7 (15 pts) — Brand Recognition & Self-Funding Discipline**: Applied uniformly across all market caps—`15 pts` if in the Top 500 Global Brands set, otherwise up to `8 pts` for self-funding revenue growth (`10%–28%` + $\text{FCF} > 0$) and up to `7 pts` for share count discipline (`3Y Share CAGR <= +1.2%`).
    - Apply **100% uniform filtering** across all market-cap tiers (`Total Moat Score >= 70.0`, `3Y Share Dilution CAGR <= 3.5%/yr`, and `5Y Projected CAGR >= 8.0%/yr`) and export to `exports/qualitative_moat_leaderboard.csv`.
    - Also export all `Mega-Cap ($1T+)` companies separately to `exports/mega_cap_watch_leaderboard.csv`.

11. **`moonshot_screener.py` (Asymmetric 5x Moonshot Screener & Dual-Survivor Tracker)**:
    - Filter `company_overview` for active operating companies (`$300M–$10B`, excluding `Real Estate`, `Financial Services`, `Utilities`) with:
      - `0.25 <= revenue_growth <= 3.00` and `(revenue_growth >= 0.30 OR earnings_growth >= 0.30)`
      - `current_ratio >= 1.5` and `(debt_to_equity IS NULL OR debt_to_equity <= 1.0)`
      - `operating_margins >= -0.15` and `forward_pe > 0` (inflection proof)
      - `beta >= 1.15`
    - Score candidates on a **100-Point Asymmetric Inflection Framework**:
      1. `Survival Runway (20 pts)`: Current Ratio + low Debt/Equity.
      2. `Growth Velocity (25 pts)`: Revenue growth + EPS/FCF acceleration.
      3. `Operating Torque (20 pts)`: Gross margin unit economics + operating margin inflection bonus.
      4. `3Y Re-Rating Upside (20 pts)`: 3Y Inflection Target Price modeling 3-year decayed growth + multiple re-rating.
      5. `Insider & Size Torque (15 pts)`: Form 4 alignment + insider ownership + sweet-spot size torque (`$300M–$3.5B`).
    - Export to `exports/asymmetric_moonshot_leaderboard.csv`.
    - Compare against `fundamental_screener_leaderboard.csv`, print a console highlight table of companies surviving **both** pipelines on the current run, and update the cumulative historical log in `exports/dual_survivor_overlap_log.csv` (`First Seen Date`, `Last Seen Date`, `Times Appeared`, `Active on Latest Run`).

12. **`run_pipeline.py` & Daily macOS Automation (`run_daily_job.sh`)**:
    - Orchestrate Steps 1–9 end-to-end via `run_pipeline.py`.
    - Create `run_daily_job.sh` (with a daily date lock `logs/.last_daily_run_date` and DNS readiness check) and a macOS LaunchAgent `~/Library/LaunchAgents/com.stocksweeper.daily.plist` (`RunAtLoad = true`, `StartInterval = 3600`) so the system runs automatically once per calendar day whenever the computer turns on or wakes up.
