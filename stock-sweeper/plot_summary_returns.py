import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import EXPORT_DIR, FUNDAMENTAL_LEADERBOARD_CSV, RETURNS_PLOT_PNG
from utils import open_file

FALLBACK_SUMMARY_CSV = os.path.join(EXPORT_DIR, "first_filter_summary.csv")


def plot_returns_distribution():
    csv_path = FUNDAMENTAL_LEADERBOARD_CSV if os.path.exists(FUNDAMENTAL_LEADERBOARD_CSV) else FALLBACK_SUMMARY_CSV
    if not os.path.exists(csv_path):
        print(f"Error: Summary file not found at {FUNDAMENTAL_LEADERBOARD_CSV}. Run generate_summary.py first.")
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print("Warning: Summary dataset is empty; skipping plot generation.")
        return

    os.makedirs(EXPORT_DIR, exist_ok=True)

    profit_col = "5Y Projected Total Return (%)" if "5Y Projected Total Return (%)" in df.columns else "5Y Total Profit (%)"
    cagr_col = "5Y Projected CAGR (%)" if "5Y Projected CAGR (%)" in df.columns else "5Y CAGR (%)"
    growth_col = "5Y Blended Growth Rate (%)" if "5Y Blended Growth Rate (%)" in df.columns else "5Y Blended Growth (%)"

    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    fig.suptitle(
        f"Quantitative Stock Screener — Projected Return & Valuation Distributions (N={len(df)})",
        fontsize=15,
        fontweight="bold",
    )

    # 1. 5Y Projected Total Return (%) Distribution
    ax1 = axes[0, 0]
    s_profit = pd.to_numeric(df[profit_col], errors="coerce").dropna()
    if not s_profit.empty:
        clipped_profit = np.clip(s_profit, -100, 500)
        ax1.hist(clipped_profit, bins=min(25, max(8, len(clipped_profit))), color="steelblue", edgecolor="black", alpha=0.85)
        ax1.axvline(s_profit.median(), color="crimson", linestyle="dashed", linewidth=2, label=f"Median: {s_profit.median():.1f}%")
        ax1.axvline(s_profit.mean(), color="darkorange", linestyle="dotted", linewidth=2, label=f"Mean: {s_profit.mean():.1f}%")
        ax1.set_title("5Y Projected Total Return (%) Distribution", fontsize=12, fontweight="bold")
        ax1.set_xlabel("5Y Projected Total Return (%)")
        ax1.set_ylabel("Company Count")
        ax1.legend()
        ax1.grid(axis="y", alpha=0.3)

    # 2. 5Y Projected CAGR (%) Distribution
    ax2 = axes[0, 1]
    s_cagr = pd.to_numeric(df[cagr_col], errors="coerce").dropna()
    if not s_cagr.empty:
        clipped_cagr = np.clip(s_cagr, -30, 60)
        ax2.hist(clipped_cagr, bins=min(25, max(8, len(clipped_cagr))), color="mediumseagreen", edgecolor="black", alpha=0.85)
        ax2.axvline(s_cagr.median(), color="crimson", linestyle="dashed", linewidth=2, label=f"Median: {s_cagr.median():.1f}%")
        ax2.set_title("5Y Projected CAGR (%) Distribution", fontsize=12, fontweight="bold")
        ax2.set_xlabel("5Y Projected CAGR (%)")
        ax2.set_ylabel("Company Count")
        ax2.legend()
        ax2.grid(axis="y", alpha=0.3)

    # 3. Top 15 Candidates by 5Y Projected Total Return (%)
    ax3 = axes[1, 0]
    top_df = df.dropna(subset=[profit_col]).sort_values(by=profit_col, ascending=False).head(15)
    if not top_df.empty:
        top_df_sorted = top_df.iloc[::-1]
        bars = ax3.barh(top_df_sorted["Ticker"], top_df_sorted[profit_col], color="darkslateblue", edgecolor="black", alpha=0.85)
        ax3.set_title("Top Shortlisted Stocks by 5Y Projected Total Return (%)", fontsize=12, fontweight="bold")
        ax3.set_xlabel("5Y Projected Total Return (%)")
        ax3.grid(axis="x", alpha=0.3)
        for bar in bars:
            w = bar.get_width()
            ax3.text(w + max(1.0, 0.01 * abs(w)), bar.get_y() + bar.get_height() / 2, f"{w:.1f}%", va="center", fontsize=8)

    # 4. 5Y Blended Growth Rate (%) vs. 5Y Projected CAGR (%)
    ax4 = axes[1, 1]
    sub_scatter = df.dropna(subset=[growth_col, cagr_col]).copy()
    if not sub_scatter.empty:
        ax4.scatter(
            sub_scatter[growth_col],
            sub_scatter[cagr_col],
            color="darkorchid",
            edgecolor="black",
            alpha=0.8,
            s=60,
        )
        for _, r in sub_scatter.head(10).iterrows():
            ax4.annotate(
                r["Ticker"],
                (r[growth_col], r[cagr_col]),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=8,
            )
        ax4.set_title("5Y Blended Growth Rate (%) vs. 5Y Projected CAGR (%)", fontsize=12, fontweight="bold")
        ax4.set_xlabel("5Y Blended Growth Rate (%)")
        ax4.set_ylabel("5Y Projected CAGR (%)")
        ax4.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0.02, 1, 0.95])
    plt.savefig(RETURNS_PLOT_PNG, dpi=150)
    plt.close(fig)

    print(f"\nSuccessfully saved return distribution plots to:")
    print(f"  └─ {RETURNS_PLOT_PNG}")
    open_file(RETURNS_PLOT_PNG)


if __name__ == "__main__":
    plot_returns_distribution()
