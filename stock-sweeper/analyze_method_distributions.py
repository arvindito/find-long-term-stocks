import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yfinance as yf

from config import DB_NAME, EXPORT_DIR, METHOD_GROWTH_CSV, METHOD_GROWTH_PNG
from database import get_db_connection
from screener import run_screener
from enricher import fetch_finviz_eps_next_5y
from utils import clean_float, open_file


def extract_and_plot_growth_distributions():
    print("Running SQL Screener to identify population...")
    shortlist_df = run_screener()
    if shortlist_df.empty:
        print("No stocks passed screening.")
        return

    tickers = shortlist_df["ticker"].tolist()
    conn = get_db_connection(DB_NAME)

    growth_data = []
    print(f"\nExtracting raw Method Growth Rates across {len(tickers)} companies...")

    for idx, t in enumerate(tickers, start=1):
        print(f"[{idx}/{len(tickers)}] Querying {t}...", end="\r")

        # 1. Historical EPS CAGR (Method 1)
        query_eps = """
        SELECT year, eps_diluted 
        FROM financial_records 
        WHERE ticker = ? AND period_type = 'Historical' AND eps_diluted IS NOT NULL AND eps_diluted > 0
        ORDER BY year ASC;
        """
        eps_df = pd.read_sql_query(query_eps, conn, params=(t,))

        m1_hist_cagr = None
        if len(eps_df) >= 5:
            oldest_eps = eps_df.iloc[0]["eps_diluted"]
            latest_eps = eps_df.iloc[-1]["eps_diluted"]
            n_years = eps_df.iloc[-1]["year"] - eps_df.iloc[0]["year"]
            if oldest_eps > 0 and latest_eps > 0 and n_years > 0:
                m1_hist_cagr = ((latest_eps / oldest_eps) ** (1 / n_years) - 1.0) * 100.0

        # 2. Historical Revenue CAGR (Method 2)
        query_rev = """
        SELECT year, revenue 
        FROM financial_records 
        WHERE ticker = ? AND period_type = 'Historical' AND revenue IS NOT NULL AND revenue > 0
        ORDER BY year ASC;
        """
        rev_df = pd.read_sql_query(query_rev, conn, params=(t,))
        m2_rev_cagr = None
        if len(rev_df) >= 5:
            old_rev = rev_df.iloc[0]["revenue"]
            new_rev = rev_df.iloc[-1]["revenue"]
            n_yrs = rev_df.iloc[-1]["year"] - rev_df.iloc[0]["year"]
            if old_rev > 0 and new_rev > 0 and n_yrs > 0:
                m2_rev_cagr = ((new_rev / old_rev) ** (1 / n_yrs) - 1.0) * 100.0

        # 3. Yahoo Long-Term Consensus Growth (Method 3)
        m3_yahoo_g = None
        try:
            yt = yf.Ticker(t)
            info = yt.info or {}
            raw_yg = clean_float(info.get("longTermPotentialGrowth"))
            if raw_yg is None:
                eps_est = yt.earnings_estimate
                if isinstance(eps_est, pd.DataFrame) and "+1y" in eps_est.index and "growth" in eps_est.columns:
                    raw_yg = clean_float(eps_est.loc["+1y", "growth"])
            if raw_yg is not None:
                m3_yahoo_g = float(raw_yg) * 100.0
        except Exception:
            pass

        # 4. Finviz 5Y Consensus EPS Rate (Method 4)
        m4_finviz_g = fetch_finviz_eps_next_5y(t)
        if m4_finviz_g is not None:
            m4_finviz_g = m4_finviz_g * 100.0

        growth_data.append({
            "Ticker": t,
            "M1: Hist EPS CAGR (%)": m1_hist_cagr,
            "M2: Hist Rev CAGR (%)": m2_rev_cagr,
            "M3: Yahoo Analyst Growth (%)": m3_yahoo_g,
            "M4: Finviz 5Y Consensus (%)": m4_finviz_g,
        })

    conn.close()

    df_growth = pd.DataFrame(growth_data)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    df_growth.to_csv(METHOD_GROWTH_CSV, index=False)

    print(f"\n\nSaved raw growth rate table to: {METHOD_GROWTH_CSV}\n")
    print("=" * 90)
    print("                      METHOD 5-YEAR GROWTH RATE POPULATION SUMMARY                       ")
    print("=" * 90)
    stats_df = df_growth.drop(columns=["Ticker"]).describe(percentiles=[0.05, 0.25, 0.50, 0.75, 0.95]).T
    print(stats_df[["count", "mean", "std", "min", "50%", "95%", "max"]].to_string())
    print("=" * 90)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"5Y Annual Growth Rate Distribution Across {len(tickers)} Screened Stocks", fontsize=16, fontweight="bold")

    methods = [
        ("M1: Hist EPS CAGR (%)", axes[0, 0], "lightcoral"),
        ("M2: Hist Rev CAGR (%)", axes[0, 1], "skyblue"),
        ("M3: Yahoo Analyst Growth (%)", axes[1, 0], "mediumseagreen"),
        ("M4: Finviz 5Y Consensus (%)", axes[1, 1], "orchid"),
    ]

    for col_name, ax, color in methods:
        series = df_growth[col_name].dropna()
        if not series.empty:
            clipped_series = np.clip(series, -50, 150)
            ax.hist(clipped_series, bins=30, color=color, edgecolor="black", alpha=0.8)
            ax.axvline(series.median(), color="red", linestyle="dashed", linewidth=2, label=f"Median: {series.median():.1f}%")
            ax.set_title(col_name, fontsize=12, fontweight="bold")
            ax.set_xlabel("Annual Growth (%)")
            ax.set_ylabel("Stock Count")
            ax.legend()
            ax.grid(axis="y", alpha=0.3)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(METHOD_GROWTH_PNG)
    plt.close(fig)
    print(f"\nSaved distribution histograms plot to: {METHOD_GROWTH_PNG}")
    open_file(METHOD_GROWTH_PNG)


if __name__ == "__main__":
    extract_and_plot_growth_distributions()
