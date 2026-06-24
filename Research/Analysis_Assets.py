"""
Multi-Asset Splice Candidate Analysis — Extending the Window to 2003
=====================================================================
Tests candidate proxies for EMB, VWO, and DBC — three ETFs whose
inception dates currently cap the optimizer's aligned window.

For each TARGET asset, computes for each candidate:
  - Correlation of monthly returns (in overlap window)
  - R²
  - Beta
  - Tracking error (annualized)
  - Vol ratio (candidate vol / target vol)
  - Available start date (how far back the splice could extend)

Run:
    python splice_candidates.py

Outputs:
    splice_candidates_results.csv  — full metrics table
    splice_candidates_chart.png    — cumulative returns per group
    (also prints ranked summaries per target to the terminal)
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


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

# Each target has a list of candidate proxies.
# Mix of ETFs (same / similar index) and mutual funds (longer history, active).
SPLICE_GROUPS = {
    "EMB": {
        "label":     "Emerging Market Bonds (USD-denominated)",
        "current":   "Dec 2007",
        "candidates": {
            "EMB":   "iShares JPM EM USD Bond ETF — current baseline",
            "PCY":   "Invesco EM Sovereign Debt ETF (Oct 2007, ~same era)",
            "PREMX": "T. Rowe Price EM Bond (mutual fund, Dec 1994)",
            "GMCDX": "GMO EM Country Debt (mutual fund, longer history)",
            "PYEMX": "Payden EM Bond (mutual fund)",
        },
    },
    "VWO": {
        "label":     "Emerging Market Equities",
        "current":   "Mar 2005",
        "candidates": {
            "VWO":   "Vanguard FTSE EM ETF — current baseline",
            "EEM":   "iShares MSCI EM ETF (Apr 2003, ~same index family)",
            "VEIEX": "Vanguard EM Stock Index fund (May 1994, same family as VWO)",
            "DFEMX": "DFA EM Portfolio (mutual fund, long history)",
        },
    },
    "DBC": {
        "label":     "Broad Commodities",
        "current":   "Feb 2006",
        "candidates": {
            "DBC":    "Invesco DB Commodity Index ETF — current baseline",
            "GSG":    "iShares GSCI Commodity ETF (Jul 2006, marginal improvement)",
            "PCRIX":  "PIMCO CommodityRealReturn (mutual fund, Jun 2002, active)",
            "QRAAX":  "Oppenheimer Commodity Strategy (mutual fund, Mar 1997)",
            "PCRAX":  "PIMCO CommodityRealReturn A-class (mutual fund)",
        },
    },
}

START   = "2002-01-01"
END     = _dt.date.today().isoformat()
PERIODS = 12

OUT_CSV   = "splice_candidates_results.csv"
OUT_CHART = "splice_candidates_chart.png"

# Correlation interpretation thresholds (only matter for the printed cheatsheet)
THRESH_EXCELLENT = 0.95
THRESH_GOOD      = 0.85
THRESH_PROBLEM   = 0.70


# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────

def fetch_monthly_returns(tickers: list[str]) -> pd.DataFrame:
    """Single yfinance call → month-end prices → monthly returns."""
    print(f"  Fetching {len(tickers)} series from yfinance "
          f"({len(set(tickers))} unique)...")
    raw = yf.download(list(set(tickers)), start=START, end=END,
                      auto_adjust=True, progress=False)

    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(prices, pd.DataFrame):
        prices = prices.to_frame()
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = prices.columns.get_level_values(-1)

    prices  = prices.resample("ME").last()
    returns = prices.pct_change().dropna(how="all")

    print(f"\n  Coverage:")
    for c in sorted(returns.columns):
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

def compare(candidate: pd.Series, target: pd.Series) -> dict:
    """All comparison metrics for one candidate vs target in their overlap."""
    df = pd.concat([candidate, target], axis=1, keys=["c", "t"]).dropna()
    n  = len(df)
    if n < 12:
        return {"overlap_months": n}

    c, t = df["c"], df["t"]
    corr = c.corr(t)
    beta = np.cov(c, t, ddof=1)[0, 1] / np.var(t, ddof=1)
    te   = (c - t).std() * np.sqrt(PERIODS)
    vol_ratio = (c.std() / t.std()) if t.std() > 0 else np.nan

    return {
        "overlap_months":      n,
        "correlation":         corr,
        "r_squared":           corr ** 2,
        "beta":                beta,
        "tracking_error_ann":  te,
        "vol_ratio":           vol_ratio,
    }


# ─────────────────────────────────────────────
# REPORTING
# ─────────────────────────────────────────────

def rank_correlation(c):
    if pd.isna(c):                  return "   n/a"
    if c >= THRESH_EXCELLENT:       return " EXCELLENT"
    if c >= THRESH_GOOD:            return "      good"
    if c >= THRESH_PROBLEM:         return "   marginal"
    return "      poor"


def analyze_group(returns: pd.DataFrame, target: str, group: dict) -> pd.DataFrame:
    """Build the per-candidate ranking table for one target asset."""
    if target not in returns.columns:
        print(f"\n  ✗ Target {target} not in fetched data — skipping.")
        return pd.DataFrame()

    target_ret = returns[target]
    rows = []
    for ticker, desc in group["candidates"].items():
        if ticker not in returns.columns:
            rows.append({"Ticker": ticker, "Description": desc, "Note": "no data"})
            continue
        m = compare(returns[ticker], target_ret)
        s = returns[ticker].dropna()
        start = s.index[0] if len(s) else None
        rows.append({
            "Ticker":             ticker,
            "Description":        desc,
            "Start":              start.date() if start is not None else None,
            "Overlap (mo)":       m.get("overlap_months", 0),
            "Correlation":        m.get("correlation"),
            "Rating":             rank_correlation(m.get("correlation")),
            "R²":                 m.get("r_squared"),
            "Beta":               m.get("beta"),
            "Tracking Err (ann)": m.get("tracking_error_ann"),
            "Vol Ratio":          m.get("vol_ratio"),
        })
    df = pd.DataFrame(rows).set_index("Ticker")
    return df.sort_values("Correlation", ascending=False, na_position="last")


def print_group(target: str, group: dict, df: pd.DataFrame):
    print("\n" + "═" * 86)
    print(f"  TARGET: {target}  —  {group['label']}")
    print(f"  Current inception: {group['current']}")
    print("═" * 86)
    if df.empty:
        print("  (no data)")
        return
    cols = ["Description", "Start", "Overlap (mo)", "Correlation",
            "Rating", "R²", "Beta", "Tracking Err (ann)", "Vol Ratio"]
    print(df[cols].to_string(
        formatters={
            "Correlation":        lambda v: f"{v:>6.3f}" if pd.notna(v) else "  n/a",
            "R²":                 lambda v: f"{v:>5.3f}" if pd.notna(v) else "  n/a",
            "Beta":               lambda v: f"{v:>5.2f}" if pd.notna(v) else "  n/a",
            "Tracking Err (ann)": lambda v: f"{v:>7.2%}" if pd.notna(v) else "    n/a",
            "Vol Ratio":          lambda v: f"{v:>5.2f}" if pd.notna(v) else "  n/a",
        },
    ))


def recommend(target: str, df: pd.DataFrame):
    """Print a one-line recommendation per target."""
    if df.empty or df["Correlation"].isna().all():
        return
    # Best candidate that's NOT the target itself and that pre-dates the target
    candidates = df[(df.index != target) & df["Correlation"].notna()].copy()
    target_start = pd.Timestamp(df.loc[target, "Start"]) if target in df.index else None
    earlier = candidates[candidates["Start"].apply(
        lambda d: pd.Timestamp(d) < target_start if d and target_start else False
    )]
    print(f"\n  ── Recommendation for {target} ──")
    if earlier.empty:
        print(f"    No candidate goes back further than {target} itself "
              f"with sufficient correlation. Keep the current inception.")
        return
    best = earlier.iloc[0]
    print(f"    {best.name}: {best['Description']}")
    print(f"    Correlation {best['Correlation']:.3f}, "
          f"tracking error {best['Tracking Err (ann)']:.2%}, "
          f"covers back to {best['Start']}")
    if best["Correlation"] >= THRESH_GOOD:
        print(f"    ✓ Strong enough for splice.")
    elif best["Correlation"] >= THRESH_PROBLEM:
        print(f"    ⚠ Marginal — defensible but worth flagging in methodology.")
    else:
        print(f"    ✗ Too weak to justify a splice.")


def plot_groups(returns: pd.DataFrame, out_path: str):
    """One subplot per target — cumulative returns of target + candidates."""
    n_groups = len(SPLICE_GROUPS)
    fig, axes = plt.subplots(n_groups, 1, figsize=(11, 4.5 * n_groups),
                             dpi=140, sharex=False)
    if n_groups == 1:
        axes = [axes]

    for ax, (target, group) in zip(axes, SPLICE_GROUPS.items()):
        if target not in returns.columns:
            ax.set_title(f"{target} — no data")
            continue
        t = returns[target].dropna()
        if not len(t):
            continue

        # Cumulative target
        cum = (1 + t).cumprod()
        ax.plot(cum.index, cum, color="black", lw=2.5, label=f"{target} (target)", zorder=5)

        palette = plt.cm.tab10.colors
        for i, ticker in enumerate(group["candidates"]):
            if ticker == target or ticker not in returns.columns:
                continue
            s = returns[ticker].dropna()
            if len(s) < 12:
                continue
            cum_c = (1 + s).cumprod()
            ax.plot(cum_c.index, cum_c, color=palette[i % 10], lw=1.4,
                    alpha=0.85, label=ticker)

        ax.set_title(f"{target} — {group['label']}", fontsize=12, fontweight="bold")
        ax.set_ylabel("Growth of $1")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", fontsize=8.5, framealpha=0.95)
        ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    print(f"\n  Chart saved → {out_path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("\n" + "═" * 86)
    print("  MULTI-ASSET SPLICE CANDIDATES — EMB, VWO, DBC")
    print("  Goal: extend optimizer window from 2008 back toward 2003")
    print("═" * 86)

    all_tickers = []
    for target, group in SPLICE_GROUPS.items():
        all_tickers.extend(group["candidates"].keys())

    returns = fetch_monthly_returns(all_tickers)

    # Per-target tables and recommendations
    all_results = {}
    for target, group in SPLICE_GROUPS.items():
        df = analyze_group(returns, target, group)
        print_group(target, group, df)
        recommend(target, df)
        df.insert(0, "Target", target)
        all_results[target] = df

    # Combined CSV
    combined = pd.concat(all_results.values())
    combined.to_csv(OUT_CSV)
    print(f"\n  Full results saved → {OUT_CSV}")

    plot_groups(returns, OUT_CHART)

    # Summary: what's the binding asset after splicing with best candidates?
    print("\n" + "═" * 86)
    print("  WINDOW IMPACT — earliest start date if we use the best candidate")
    print("  for each target (caveat: only counts if correlation ≥ good threshold)")
    print("═" * 86)
    earliest_dates = []
    for target, df in all_results.items():
        good = df[(df.index != target) &
                  (df["Correlation"] >= THRESH_GOOD)]
        if not good.empty:
            best = good.iloc[0]
            print(f"  {target:<6} → splice with {best.name:<8} starts {best['Start']}")
            earliest_dates.append(pd.Timestamp(best["Start"]))
        else:
            cur = df.loc[target, "Start"] if target in df.index else None
            print(f"  {target:<6} → no good splice; stays at {cur}")
            if cur:
                earliest_dates.append(pd.Timestamp(cur))
    if earliest_dates:
        binding = max(earliest_dates)
        print(f"\n  Effective binding date for this group: {binding.date()}")
        print(f"  (Your overall window will be limited by this OR another non-spliced asset.)")


if __name__ == "__main__":
    main()