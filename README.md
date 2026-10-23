# Stock Sweeper — Fundamental Compounder & Asymmetric Moonshot Engine

A modular Python equity research, valuation, and ranking engine designed to scan the entire US stock market (`8,700+` SEC tickers) and surface high-conviction opportunities across two distinct portfolio strategies:

1. **Core Quality Compounders ($\ge \$500\text{M}$ Market Cap):** Small-Cap (`$500M–$5B`), Mid-Cap (`$5B–$50B`), Large-Cap (`$50B–$1T`), and Mega-Cap (`$1T+`) compounders evaluated through a 9-gate SQL fundamental screener, a 15-year SEC EDGAR 10-K + 4-method valuation engine, and a 100-point **7-Pillar Qualitative Moat Scorer**.
2. **Asymmetric 5x Moonshots (`$300M–$10B` Market Cap):** High-torque inflection plays for a 1% portfolio sleeve (6-month to 3-year horizon), targeting companies with fortress liquidity (`Current Ratio >= 1.5`, `Debt/Equity <= 1.0`), explosive demand (`Revenue Growth 25%–300%`), and imminent profitability inflection (`Operating Margin >= -15%` with positive forward EPS).

---

## Architecture & Module Map (`stock-sweeper/`)

| File | Responsibility |
| :--- | :--- |
| [`config.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/config.py) | Central configuration for SQLite database path (`market_data.db`), all 6 export CSV filenames (`exports/`), and batch settings. |
| [`utils.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/utils.py) | Shared utility functions: `is_valid_num()`, `clean_float()`, `classify_market_cap_tier()`, `ensure_file_limits()`, and cross-platform `open_file()`. |
| [`database.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/database.py) | SQLite schema definition (`company_overview`, `financial_records`, `consensus_estimates`), non-destructive schema migrations, and WAL-enabled `get_db_connection()`. |
| [`sec_tickers.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/sec_tickers.py) | Downloads active equity symbols from official SEC EDGAR (`company_tickers.json`), excluding SPACs, warrants, units, and rights. |
| [`sweeper.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/sweeper.py) | Multi-threaded Stage 1 & Stage 2 market sweeper via `yfinance` with tiered cache TTL (`24h` for active tickers $\ge \$100\text{M}$, `7d` for inactive or $< \$100\text{M}$ micro-caps). |
| [`screener.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/screener.py) | Runs the unified SQL compounder filter (`Market Cap >= $500M`, `ROIC >= 10%`, `FCF > 0`, `Operating Margin >= 10%`, `Revenue & EPS Growth >= 5%`, `Current Ratio >= 0.5`, `Debt/Equity <= 2.0`, `Forward P/E >= 5.0`, `Beta >= 0.7`) and tags tiers. |
| [`enricher.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/enricher.py) | Enriches both Compounder and Moonshot shortlists with 10 years of SEC EDGAR 10-K XBRL history (`Revenue`, `Gross Profit`, `SG&A Expense`, `Net Income`, `FCF`, `Shares`), Finviz 5Y growth rates, historical year-end prices, and FX-normalized consensus estimates. |
| [`exporter.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/exporter.py) | Builds the 15-year historical + 5-year forward valuation model (`exports/valuation_model_timeline.csv`) using 4 blended growth methods, stock-split/ADR share normalization, 3Y share dilution drift, and smooth Year 1 $\rightarrow$ Year 5 P/E transitions. |
| [`generate_summary.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/generate_summary.py) | Generates the ranked fundamental leaderboard (`exports/fundamental_screener_leaderboard.csv`) with market-cap tiers, 3Y share dilution CAGR, historical price checkpoints, and 3Y/5Y projected returns. |
| [`qualitative_scorer.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/qualitative_scorer.py) | Evaluates shortlisted candidates across the **7-Pillar Qualitative Moat Framework (100 pts)** with uniform rules across all tiers (`Moat >= 70`, `Dilution <= 3.5%/yr`, `5Y CAGR >= 8%`) into `exports/qualitative_moat_leaderboard.csv`, plus `exports/mega_cap_watch_leaderboard.csv`. |
| [`moonshot_screener.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/moonshot_screener.py) | Screens and ranks `$300M–$10B` high-torque inflection candidates (`exports/asymmetric_moonshot_leaderboard.csv`) and updates the cumulative Dual-Survivor overlap log (`exports/dual_survivor_overlap_log.csv`). |
| [`plot_summary_returns.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/plot_summary_returns.py) | Generates return distribution histograms and leaderboards (`exports/projected_returns_distribution.png`). |
| [`run_pipeline.py`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/run_pipeline.py) | Master 9-step CLI orchestrator supporting `--skip-sweep`, `--limit`, and `--init-only`. |
| [`run_daily_job.sh`](file:///Users/arvindadvani/Git/find-long-term-stocks/stock-sweeper/run_daily_job.sh) | Automated daily wrapper invoked by macOS `launchd` (`~/Library/LaunchAgents/com.stocksweeper.daily.plist`) to run the pipeline once per calendar day whenever the Mac turns on or wakes up. |

---

## All 6 Exported CSVs (`stock-sweeper/exports/`)

1. **`valuation_model_timeline.csv`**: 15-year year-by-year financial & 4-method valuation ledger (`2016–2031`) for all compounder shortlist stocks.
2. **`fundamental_screener_leaderboard.csv`**: All companies ($\ge \$500\text{M}$) passing the 9 quantitative SQL compounder gates, ranked by 5Y Projected Return.
3. **`qualitative_moat_leaderboard.csv`**: Elite compounders passing uniform post-enrichment quality gates (`Moat Score >= 70`, `3Y Share Dilution <= 3.5%/yr`, `5Y Projected CAGR >= 8.0%/yr`).
4. **`mega_cap_watch_leaderboard.csv`**: Dedicated watchlist of all `$1T+` Mega-Cap anchors for swing-trading and valuation reference.
5. **`asymmetric_moonshot_leaderboard.csv`**: Ranked `$300M–$10B` high-torque inflection candidates scored on the 100-point Asymmetric Inflection Framework.
6. **`dual_survivor_overlap_log.csv`**: Persistent, cumulative historical log of rare companies surviving **both** the Compounder and Moonshot pipelines across runs.

---

## Quick Start

```bash
cd stock-sweeper

# Run using existing swept market data (fast re-score & export)
.venv/bin/python run_pipeline.py --skip-sweep

# Run full daily market sweep + enrichment + valuation + moat & moonshot scoring
.venv/bin/python run_pipeline.py
```
