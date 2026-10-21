import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from utils import open_file

EXPORT_DIR = "exports"
SUMMARY_CSV = os.path.join(EXPORT_DIR, "first_filter_summary.csv")
FALLBACK_SUMMARY_CSV = os.path.join(EXPORT_DIR, "screener_summary_leaderboard.csv")
OUTPUT_PLOT = os.path.join(EXPORT_DIR, "summary_returns_distribution.png")


def plot_returns_distribution():
    csv_path = SUMMARY_CSV if os.path.exists(SUMMARY_CSV) else FALLBACK_SUMMARY_CSV
    if not os.path.exists(csv_path):
        print(f"Error: Summary file not found at {SUMMARY_CSV}. Run generate_summary.py first.")
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print("Warning: Summary dataset is empty; skipping plot generation.")
        return

    os.makedirs(EXPORT_DIR, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    fig.suptitle(
        f"Quantitative Stock Screener — Projected Return & Valuation Distributions (N={len(df)})",
        fontsize=15,
        fontweight="bold",
    )

    # 1. 5Y Total Profit (%) Distribution
    ax1 = axes[0, 0]
    s_profit = pd.to_numeric(df["5Y Total Profit (%)"], errors="coerce").dropna()
    if not s_profit.empty:
        clipped_profit = np.clip(s_profit, -100, 500)
        ax1.hist(clipped_profit, bins=min(25, max(8, len(clipped_profit))), color="steelblue", edgecolor="black", alpha=0.85)
        ax1.axvline(s_profit.median(), color="crimson", linestyle="dashed", linewidth=2, label=f"Median: {s_profit.median():.1f}%")
        ax1.axvline(s_profit.mean(), color="darkorange", linestyle="dotted", linewidth=2, label=f"Mean: {s_profit.mean():.1f}%")
        ax1.set_title("5Y Total Profit (%) Distribution", fontsize=12, fontweight="bold")
        ax1.set_xlabel("5Y Total Return (%)")
        ax1.set_ylabel("Company Count")
        ax1.legend()
        ax1.grid(axis="y", alpha=0.3)

    # 2. 5Y Annualized Return (CAGR %) Distribution
    ax2 = axes[0, 1]
    s_cagr = pd.to_numeric(df["5Y CAGR (%)"], errors="coerce").dropna()
    if not s_cagr.empty:
        clipped_cagr = np.clip(s_cagr, -30, 60)
        ax2.hist(clipped_cagr, bins=min(25, max(8, len(clipped_cagr))), color="mediumseagreen", edgecolor="black", alpha=0.85)
        ax2.axvline(s_cagr.median(), color="crimson", linestyle="dashed", linewidth=2, label=f"Median: {s_cagr.median():.1f}%")
        ax2.set_title("5Y Annualized Return (CAGR %) Distribution", fontsize=12, fontweight="bold")
        ax2.set_xlabel("5Y CAGR (%)")
        ax2.set_ylabel("Company Count")
        ax2.legend()
        ax2.grid(axis="y", alpha=0.3)

    # 3. Top 15 Candidates by 5Y Total Profit (%)
    ax3 = axes[1, 0]
    top_df = df.dropna(subset=["5Y Total Profit (%)"]).sort_values(by="5Y Total Profit (%)", ascending=False).head(15)
    if not top_df.empty:
        top_df_sorted = top_df.iloc[::-1]
        bars = ax3.barh(top_df_sorted["Ticker"], top_df_sorted["5Y Total Profit (%)"], color="darkslateblue", edgecolor="black", alpha=0.85)
        ax3.set_title("Top Shortlisted Stocks by 5Y Projected Profit (%)", fontsize=12, fontweight="bold")
        ax3.set_xlabel("5Y Total Profit (%)")
        ax3.grid(axis="x", alpha=0.3)
        for bar in bars:
            w = bar.get_width()
            ax3.text(w + max(1.0, 0.01 * abs(w)), bar.get_y() + bar.get_height() / 2, f"{w:.1f}%", va="center", fontsize=8)

    # 4. 3Y Return (%) vs. 5Y Blended Growth (%)
    ax4 = axes[1, 1]
    sub_scatter = df.dropna(subset=["5Y Blended Growth (%)", "5Y CAGR (%)"]).copy()
    if not sub_scatter.empty:
        ax4.scatter(
            sub_scatter["5Y Blended Growth (%)"],
            sub_scatter["5Y CAGR (%)"],
            color="darkorchid",
            edgecolor="black",
            alpha=0.8,
            s=60,
        )
        for _, r in sub_scatter.head(10).iterrows():
            ax4.annotate(
                r["Ticker"],
                (r["5Y Blended Growth (%)"], r["5Y CAGR (%)"]),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=8,
            )
        ax4.set_title("5Y Blended Growth (%) vs. 5Y Price CAGR (%)", fontsize=12, fontweight="bold")
        ax4.set_xlabel("Model 5Y Blended Growth (%)")
        ax4.set_ylabel("Projected 5Y Price CAGR (%)")
        ax4.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0.02, 1, 0.95])
    plt.savefig(OUTPUT_PLOT, dpi=150)
    plt.close(fig)

    print(f"\nSuccessfully saved return distribution plots to:")
    print(f"  └─ {OUTPUT_PLOT}")
    open_file(OUTPUT_PLOT)


if __name__ == "__main__":
    plot_returns_distribution()
