import math
import os
import resource
import subprocess
import sys
import pandas as pd


def ensure_file_limits(target_soft_limit: int = 4096):
    """
    Raises the macOS/POSIX soft file descriptor limit so multi-threaded
    HTTP/SQLite operations never hit 'Errno 24: Too many open files'.
    """
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft < target_soft_limit:
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(target_soft_limit, hard), hard))
    except Exception:
        pass


def is_valid_num(val) -> bool:
    """Returns True if val is a finite, non-NaN numeric value."""
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
        f = float(val)
        return not (math.isnan(f) or math.isinf(f))
    except (ValueError, TypeError):
        return False


def clean_float(val, default=None):
    """Safely converts val to float, returning default if None, NaN, or Inf."""
    return float(val) if is_valid_num(val) else default


def classify_market_cap_tier(market_cap_usd: float | None) -> str:
    """
    Classifies a company's market cap (in USD) into one of the portfolio's
    standard size tiers:
      - Mega-Cap ($1T+)
      - Large-Cap ($50B-$1T)
      - Mid-Cap ($5B-$50B)
      - Small-Cap ($500M-$5B)
      - Micro-Cap (<$500M)
    """
    mc = clean_float(market_cap_usd)
    if mc is None or mc <= 0:
        return "Unknown"
    if mc >= 1_000_000_000_000:
        return "Mega-Cap ($1T+)"
    if mc >= 50_000_000_000:
        return "Large-Cap ($50B-$1T)"
    if mc >= 5_000_000_000:
        return "Mid-Cap ($5B-$50B)"
    if mc >= 500_000_000:
        return "Small-Cap ($500M-$5B)"
    return "Micro-Cap (<$500M)"


def open_file(filepath: str):
    """
    Safely attempts to open an exported file on macOS if running interactively,
    never raising an exception or blocking automated pipelines.
    """
    if not filepath or not os.path.exists(filepath):
        return
    if os.environ.get("CI") or os.environ.get("HEADLESS", "1") == "1":
        return
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ["open", filepath],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass
