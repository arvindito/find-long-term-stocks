Act as an autonomous lead quantitative software engineer. In this repository, we are running an end-to-end quantitative stock screener and valuation pipeline from scratch.

Your task is to orchestrate the entire process end-to-end, fix bugs in code as they arise, and ensure valid data populates market_data.db and exports/.

Here is the operational workflow to execute:

1. System & Architecture Audit:
   - Check config.py, database.py, sweeper.py, screener.py, enricher.py, exporter.py, and run_pipeline.py.
   - Ensure database schema supports Free Cash Flow (FCF) and ROIC.
   - Verify sweeper.py extracts Operating Cash Flow, CapEx, FCF, and ROIC into SQLite.
   - Verify screener.py enforces market_cap >= $1B, solvency (debt-to-equity <= 2.0), liquidity (current_ratio >= 0.5), profitability (operating_margin >= 10%), growth (earnings_growth >= 5%, revenue_growth >= 5%), forward P/E >= 5.0, FCF > 0, and ROIC >= 10%.
   - Verify exporter.py implements Linear P/E Multiple Decay (Option A) toward the company's historical median P/E and uses dedicated Revenue CAGR for Method 2.

2. Database Reset & Fresh Ingestion:
   - Run python database.py to initialize/reset the SQLite tables.
   - Run a test sweep of 30-50 tickers first (e.g. python -c "from sweeper import run_sweeper; run_sweeper(limit=50)") to verify that rate limits, data types, and batch commits into market_data.db execute without schema mismatches.
   - If errors occur, inspect the tracebacks, patch the code, and retry.
   - Once the test batch succeeds, kick off the full market sweep.

3. Downstream Execution & Self-Healing:
   - Run screener.py and confirm non-empty candidate shortlists.
   - Run enricher.py to pull SEC 10-K multi-year facts and consensus estimates. If SEC EDGAR headers or rate-limits throw errors, handle them gracefully with exponential backoff.
   - Run exporter.py to generate exports/15y_export.csv. Ensure no division by zero or NaN values break the 4-method convergence.
   - Run generate_summary.py to create the ranked leaderboard exports/first_filter_summary.csv.
   - Run plot_summary_returns.py to generate visualization artifacts.

4. Deliverable:
   - Once all stages complete cleanly, verify that run_pipeline.py runs end-to-end with zero manual interventions so that in future sessions, running `python run_pipeline.py` executes the entire pipeline autonomously.
   - Provide a final summary of any bugs patched and the top 5 shortlisted stocks.