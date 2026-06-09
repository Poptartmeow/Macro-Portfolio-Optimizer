"""
International Bond Splice — Proxy Selection Study
=================================================
Tests candidate ETFs/funds for the pre-2013 leg of the international bond
splice (extending BNDX backward to 2007). BWX was the original baseline,
but its BWX→BNDX overlap correlation is only ~0.48 — driven mostly by BWX
being unhedged vs BNDX USD-hedged.

RESULT: this study is why the data pipeline now uses PFORX (PIMCO Intl Bond
USD-Hedged) as the proxy instead of BWX — PFORX is USD-hedged like BNDX and
tracks it far more closely. See data_pipeline.py SPLICE config. The BWX
references below are kept because BWX is still the baseline this study
measures everything against.

This script measures, for each candidate vs BNDX in their overlap window:
  - Correlation of monthly returns          (★ headline number)
  - R²                                       (variance explained)
  - Beta                                     (slope of candidate on BNDX)
  - Tracking error                           (annualized std of difference)
  - Mean return difference                   (does the level match?)
  - Volatility ratio                         (does the risk match?)
  - Available history (start date)           (how far back can we splice?)

Run:
    python -m macro_portfolio.analysis.intl_bond_splice

Outputs (written to outputs/):
    splice_analysis_results.csv  — full metrics table
    splice_analysis_chart.png    — cumulative return comparison
    (also prints a ranked summary to the terminal)
"""

import warnings
warnings.filterwarnings("ignore")

import datetime as _dt
import numpy as np
import pandas as pd
import yfinance as yf

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from macro_portfolio.paths import OUTPUTS_DIR


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

TARGET   = "BNDX"   # the series we're trying to extend backward

# Candidates to test. Mix of:
#   - Unhedged ETFs (likely worse, but we want data not theory)
#   - USD-hedged PIMCO mutual funds (the real shots on goal)
CANDIDATES = {
    "BWX":   "SPDR Intl Treasury (unhedged) — current baseline",
    "IGOV":  "iShares Intl Treasury (unhedged)",
    "PICB":  "Invesco Intl Corporate (unhedged)",
    "IBND":  "SPDR Intl Corporate (unhedged)",
    "WIP":   "SPDR Intl Inflation-Linked Treasury (unhedged)",
    "PFORX": "PIMCO Intl Bond USD-Hedged (mutual fund, active)",
    "PFUIX": "PIMCO Foreign Bond USD-Hedged (mutual fund, active)",
}

START   = "2007-01-01"
END     = _dt.date.today().isoformat()
PERIODS = 12

OUT_CSV   = str(OUTPUTS_DIR / "splice_analysis_results.csv")
OUT_CHART = str(OUTPUTS_DIR / "splice_analysis_chart.png")


# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────

def fetch_monthly_returns(tickers: list[str]) -> pd.DataFrame:
    """Single yfinance call → month-end prices → monthly returns."""
    print(f"  Fetching {len(tickers)} series from yfinance...")
    raw = yf.download(tickers, start=START, end=END,
                      auto_adjust=True, progress=False)

    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(prices, pd.DataFrame):
        prices = prices.to_frame()
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = prices.columns.get_level_values(-1)

    prices = prices.resample("ME").last()
    returns = prices.pct_change().dropna(how="all")

    print(f"  Coverage:")
    for c in returns.columns:
        s = returns[c].dropna()
        if len(s):
            print(f"    {c:<8} {s.index[0].date()} → {s.index[-1].date()} "
                  f"({len(s):>4} months)")
        else:
            print(f"    {c:<8} *** NO DATA ***")
    return returns


# ─────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────

def compare_to_target(candidate: pd.Series, target: pd.Series) -> dict:
    """Compute all comparison metrics for one candidate vs the target."""
    # Align to the overlap window only
    df = pd.concat([candidate, target], axis=1, keys=["cand", "tgt"]).dropna()
    n  = len(df)
    if n < 12:
        return {"overlap_months": n}

    c, t = df["cand"], df["tgt"]

    corr = c.corr(t)
    # Beta = cov(c, t) / var(t)
    beta = np.cov(c, t, ddof=1)[0, 1] / np.var(t, ddof=1)
    r2   = corr ** 2

    diff = c - t
    tracking_error = diff.std() * np.sqrt(PERIODS)
    mean_diff_ann  = diff.mean() * PERIODS

    vol_ratio = (c.std() / t.std()) if t.std() > 0 else np.nan

    return {
        "overlap_months":      n,
        "correlation":         corr,
        "r_squared":           r2,
        "beta":                beta,
        "tracking_error_ann":  tracking_error,
        "mean_diff_ann":       mean_diff_ann,
        "vol_ratio":           vol_ratio,
    }


def coverage_start(returns: pd.DataFrame, ticker: str) -> pd.Timestamp | None:
    s = returns[ticker].dropna() if ticker in returns.columns else pd.Series(dtype=float)
    return s.index[0] if len(s) else None


# ─────────────────────────────────────────────
# REPORTING
# ─────────────────────────────────────────────

def build_results(returns: pd.DataFrame) -> pd.DataFrame:
    """Build the full results table — one row per candidate."""
    target = returns[TARGET]
    rows = []
    for ticker, desc in CANDIDATES.items():
        if ticker not in returns.columns:
            rows.append({"Ticker": ticker, "Description": desc,
                         "Start": None, "overlap_months": 0,
                         "Note": "no data returned"})
            continue
        m = compare_to_target(returns[ticker], target)
        start = coverage_start(returns, ticker)
        rows.append({
            "Ticker":             ticker,
            "Description":        desc,
            "Start":              start.date() if start is not None else None,
            "Overlap (mo)":       m.get("overlap_months", 0),
            "Correlation":        m.get("correlation"),
            "R²":                 m.get("r_squared"),
            "Beta":               m.get("beta"),
            "Tracking Err (ann)": m.get("tracking_error_ann"),
            "Mean Diff (ann)":    m.get("mean_diff_ann"),
            "Vol Ratio":          m.get("vol_ratio"),
        })
    df = pd.DataFrame(rows).set_index("Ticker")
    # Sort by correlation (best at top), NaN to bottom
    df = df.sort_values("Correlation", ascending=False, na_position="last")
    return df


def print_results(df: pd.DataFrame):
    print("\n" + "─" * 78)
    print(f"  CORRELATION TO {TARGET} (ranked best → worst)")
    print("─" * 78)
    cols = ["Description", "Start", "Overlap (mo)", "Correlation",
            "R²", "Beta", "Tracking Err (ann)", "Vol Ratio"]
    print(df[cols].to_string(
        formatters={
            "Correlation":         lambda v: f"{v:>6.3f}" if pd.notna(v) else "  n/a",
            "R²":                  lambda v: f"{v:>5.3f}" if pd.notna(v) else "  n/a",
            "Beta":                lambda v: f"{v:>5.2f}" if pd.notna(v) else "  n/a",
            "Tracking Err (ann)":  lambda v: f"{v:>7.2%}" if pd.notna(v) else "    n/a",
            "Vol Ratio":           lambda v: f"{v:>5.2f}" if pd.notna(v) else "  n/a",
        },
    ))
    print("─" * 78)

    # Interpretation cheatsheet
    print("\n  How to read this:")
    print("    Correlation        > 0.85 is good, > 0.95 is excellent, < 0.7 is a real problem")
    print("    R²                 fraction of BNDX variance the candidate explains (corr²)")
    print("    Beta               1.0 means moves 1:1 with BNDX in magnitude")
    print("    Tracking Err (ann) annualized std of the difference — lower is closer match")
    print("    Vol Ratio          candidate vol / BNDX vol — 1.0 means same risk level")


def plot_cumulative(returns: pd.DataFrame, out_path: str):
    """Cumulative-return comparison chart for visual sanity check."""
    target = returns[TARGET].dropna()
    if not len(target):
        print("  ⚠ No BNDX data — skipping chart.")
        return

    start = target.index[0]
    fig, ax = plt.subplots(figsize=(11, 6), dpi=150)

    # Target line first (bold black)
    cum_target = (1 + target).cumprod()
    ax.plot(cum_target.index, cum_target, color="black", lw=2.5,
            label=f"{TARGET} (target)", zorder=5)

    palette = plt.cm.tab10.colors
    for i, ticker in enumerate(CANDIDATES):
        if ticker == TARGET or ticker not in returns.columns:
            continue
        s = returns[ticker].dropna()
        s = s[s.index >= start]
        if len(s) < 12:
            continue
        cum = (1 + s).cumprod()
        ax.plot(cum.index, cum, color=palette[i % 10], lw=1.4, alpha=0.85, label=ticker)

    ax.set_title(f"Cumulative Returns — {TARGET} vs Splice Candidates (since {start.date()})",
                 fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("Cumulative Return (growth of $1)")
    ax.set_xlabel("")
    ax.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax.grid(True, alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    print(f"\n  Chart saved → {out_path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("\n" + "═" * 78)
    print("  BWX → BNDX SPLICE — ALTERNATIVE PROXY ANALYSIS")
    print("═" * 78 + "\n")

    tickers = [TARGET] + [t for t in CANDIDATES if t != TARGET]
    returns = fetch_monthly_returns(tickers)

    if TARGET not in returns.columns or returns[TARGET].dropna().empty:
        raise RuntimeError(f"\n✗ Could not fetch {TARGET} — analysis can't proceed.")

    df = build_results(returns)
    print_results(df)
    df.to_csv(OUT_CSV)
    print(f"\n  Full results saved → {OUT_CSV}")

    plot_cumulative(returns, OUT_CHART)

    # Recommendation
    best = df["Correlation"].dropna().idxmax() if df["Correlation"].notna().any() else None
    current = "BWX"
    if best and best != current:
        improvement = df.loc[best, "Correlation"] - df.loc[current, "Correlation"]
        print(f"\n  ── Top candidate ──")
        print(f"    {best}: {df.loc[best, 'Description']}")
        print(f"    Correlation {df.loc[best, 'Correlation']:.3f} "
              f"vs {current}'s {df.loc[current, 'Correlation']:.3f} "
              f"(improvement: {improvement:+.3f})")
        print(f"    Coverage starts: {df.loc[best, 'Start']}")
        if df.loc[best, "Start"] and pd.Timestamp(df.loc[best, "Start"]) > pd.Timestamp("2007-12-31"):
            print(f"    ⚠ Starts AFTER Jan 2008 — would lose part of GFC window.")


if __name__ == "__main__":
    main()