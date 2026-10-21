#!/usr/bin/env python3
"""
Stock Sweeper Master Pipeline Runner
Orchestrates: Database Init -> Ingestion -> Screening -> Enrichment -> Projections -> Summary -> Plotting
"""

import os
import sys
import argparse
import sqlite3
import traceback
from datetime import datetime
from config import DB_NAME

def check_db_health():
    if not os.path.exists(DB_NAME):
        return 0, 0
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        c = cur.execute("SELECT COUNT(*) FROM company_overview").fetchone()[0]
        f = cur.execute("SELECT COUNT(*) FROM financial_records").fetchone()[0]
        conn.close()
        return c, f
    except Exception:
        return 0, 0

def step_init_db():
    print("\n" + "="*60)
    print("STEP 1: DATABASE INITIALIZATION")
    print("="*60)
    from database import init_db
    init_db()

def step_sweep(limit=None):
    print("\n" + "="*60)
    print(f"STEP 2: RUNNING SWEEPER (Limit: {limit if limit else 'Full Market'})")
    print("="*60)
    from sweeper import run_sweeper
    run_sweeper(limit=limit)

def step_screen():
    print("\n" + "="*60)
    print("STEP 3: RUNNING SCREENER (Fundamental & Quality Gates)")
    print("="*60)
    from screener import run_screener
    shortlist = run_screener()
    if shortlist.empty:
        print("\n[!] No stocks passed screening criteria.")
        return None
    print(f"\n[+] {len(shortlist)} stocks shortlisted:")
    print(shortlist[['ticker', 'company_name', 'current_price', 'forward_pe', 'operating_margins']].to_string(index=False))
    return shortlist

def step_enrich():
    print("\n" + "="*60)
    print("STEP 4: ENRICHING WITH SEC EDGAR 10-K & CONSENSUS")
    print("="*60)
    from enricher import enrich_shortlist_history
    enrich_shortlist_history(current_year=datetime.now().year)

def step_export():
    print("\n" + "="*60)
    print("STEP 5: GENERATING 15-YEAR TIMELINE & 5-YEAR PROJECTIONS")
    print("="*60)
    from exporter import export_clean_dataset
    export_clean_dataset(max_history_years=10)

def step_summary():
    print("\n" + "="*60)
    print("STEP 6: GENERATING RANKED SUMMARY LEADERBOARD")
    print("="*60)
    try:
        import generate_summary
        if hasattr(generate_summary, 'generate_leaderboard'):
            generate_summary.generate_leaderboard()
        elif hasattr(generate_summary, 'generate_summary'):
            generate_summary.generate_summary()
        elif hasattr(generate_summary, 'main'):
            generate_summary.main()
    except Exception as e:
        print(f"[!] Summary generation note: {e}")

def step_plot():
    print("\n" + "="*60)
    print("STEP 7: RENDERING RETURN DISTRIBUTION PLOTS")
    print("="*60)
    try:
        from plot_summary_returns import plot_returns_distribution
        plot_returns_distribution()
    except Exception as e:
        print(f"[!] Plot generation note: {e}")

def main():
    parser = argparse.ArgumentParser(description="Run the Stock Sweeper pipeline.")
    parser.add_argument("--skip-sweep", action="store_true", help="Skip web scraping and run on current database.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of tickers to scrape during sweep.")
    parser.add_argument("--init-only", action="store_true", help="Only initialize database and exit.")
    args = parser.parse_args()

    # Step 1: Init DB
    step_init_db()
    if args.init_only:
        return

    # Step 2: Sweep
    if not args.skip_sweep:
        step_sweep(limit=args.limit)
    else:
        c, f = check_db_health()
        print(f"\n[i] Skipping sweep. Using existing data ({c} companies, {f} financial rows).")

    # Step 3: Screen
    shortlist = step_screen()
    if shortlist is None:
        print("\nPipeline stopped at screening stage.")
        return

    # Step 4: Enrich
    try:
        step_enrich()
    except Exception as e:
        print(f"\n[!] Warning in SEC/Consensus enrichment: {e}")
        traceback.print_exc()

    # Step 5: Export Projections
    step_export()

    # Step 6: Summary Leaderboard
    step_summary()

    # Step 7: Plotting
    step_plot()

    print("\n" + "="*60)
    print(f"PIPELINE COMPLETE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

if __name__ == "__main__":
    main()
