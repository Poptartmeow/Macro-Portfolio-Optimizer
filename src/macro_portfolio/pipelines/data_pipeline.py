"""
Global Macro Portfolio — Data Pipeline
=======================================
Pulls all ETF price history from yfinance, builds the PFORX→BNDX
splice, computes monthly returns, and saves clean output files.

Run:
    python -m macro_portfolio.pipelines.data_pipeline

Outputs:
    market_data/raw/prices_raw.csv             — raw monthly adjusted close prices
    market_data/processed/returns_aligned.csv  — ★ clean monthly returns, common window, no NaNs (main input to optimizer)
    market_data/processed/summary_stats.csv    — annualized return / vol / sharpe per asset

(A coverage/gap report is still printed to the console each run, but no longer
saved as a CSV — nothing downstream consumed it.)

Asset Universe:
    SPY   — US Large Cap (S&P 500)                 [from 1993]
    VXF   — US Mid + Small Cap                     [from 2001]
    EWC   — Canadian Equities                      [from 1996]
    EFA   — Intl Developed Equities (ex-US)        [from 2001]
    VWO   — Emerging Market Equities               [spliced back to 2002]
    AGG   — US Aggregate Bonds                     [from 2003] ← binds aligned window
    EMB   — Emerging Market Bonds                  [spliced back to 2002]
    DBC   — Broad Commodities                      [spliced back to 2002]

    Splices (chain-linked proxy → primary, joined at the return level):
    PFORX — PIMCO Intl Bond USD-Hedged (active fund) [2002–2013] ─┐
    BNDX  — Intl Aggregate ex-US USD-hedged (index)  [2013+]      ─┘ → INTL_BOND
    PYEMX — PIMCO EM Bond (active fund)              [2002–2008] ─┐
    EMB   — iShares EM USD Bond (index)             [2008+]       ─┘ → EMB
    PCRIX — PIMCO CommodityRealReturn (active fund)  [2002–2006] ─┐
    DBC   — Invesco DB Commodity Index              [2006+]       ─┘ → DBC
    VEIEX — Vanguard EM Stock Index (mutual fund)    [2002–2005] ─┐
    VWO   — Vanguard FTSE EM ETF                    [2005+]       ─┘ → VWO
"""

import os
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

from macro_portfolio.paths import MARKET_RAW, MARKET_PROCESSED

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

import datetime as _dt

START_DATE  = "2002-01-01"   # pull max available history; the common/aligned window is
                             # still bounded by the latest ETF inception (EMB, Jan 2008)
# End at the first day of the current month so the in-progress (incomplete) month is
# excluded — yfinance's `end` is exclusive, so this yields data through last month-end.
END_DATE    = _dt.date.today().replace(day=1).isoformat()
FREQUENCY   = "ME"           # Month-end
PERIODS     = 12             # Months per year
RAW_DIR     = str(MARKET_RAW)        # raw price pulls
OUTPUT_DIR  = str(MARKET_PROCESSED)  # returns, stats, benchmark (optimizer inputs)

# Core universe — each ETF and a human-readable label
UNIVERSE = {
    "SPY":  "US Large Cap (S&P 500)",
    "VXF":  "US Mid + Small Cap",
    "EWC":  "Canadian Equities",
    "EFA":  "Intl Developed Equities (ex-US)",
    "VWO":  "Emerging Market Equities",
    "AGG":  "US Aggregate Bonds",
    "EMB":  "Emerging Market Bonds",
    "DBC":  "Broad Commodities",
}

# Splice configs: each chain-links a longer-history proxy fund into a primary
# ETF at the return level. `output_name` is the resulting series; when it equals
# a UNIVERSE ticker (EMB/DBC/VWO) the spliced series replaces that column, when
# it does not (INTL_BOND) it is added as a new column. `splice_date` is the first
# month the primary's own returns are used; the proxy fills everything before.
SPLICES = [
    {
        "output_name": "INTL_BOND",
        "label":       "Intl Bonds ex-US (spliced: PFORX→BNDX)",
        "proxy":       "PFORX",       # PIMCO Intl Bond USD-Hedged (active)
        "primary":     "BNDX",        # Intl Aggregate ex-US USD-hedged (index)
        "splice_date": "2013-04-01",  # BNDX inception (Apr 2013)
    },
    {
        "output_name": "EMB",
        "label":       "EM Bonds (spliced: PYEMX→EMB)",
        "proxy":       "PYEMX",       # PIMCO Emerging Markets Bond (active)
        "primary":     "EMB",         # iShares J.P. Morgan EM USD Bond
        "splice_date": "2008-01-01",  # EMB inception (Dec 2007 → first return Jan 2008)
    },
    {
        "output_name": "DBC",
        "label":       "Broad Commodities (spliced: PCRIX→DBC)",
        "proxy":       "PCRIX",       # PIMCO CommodityRealReturn (active)
        "primary":     "DBC",         # Invesco DB Commodity Index
        "splice_date": "2006-03-01",  # DBC inception (Feb 2006)
    },
    {
        "output_name": "VWO",
        "label":       "EM Equities (spliced: VEIEX→VWO)",
        "proxy":       "VEIEX",       # Vanguard Emerging Markets Stock Index
        "primary":     "VWO",         # Vanguard FTSE Emerging Markets ETF
        "splice_date": "2005-04-01",  # VWO inception (Mar 2005)
    },
]


# ─────────────────────────────────────────────
# STEP 1 — FETCH RAW PRICES
# ─────────────────────────────────────────────

def fetch_prices(tickers: list, start: str, end: str, max_retries: int = 4) -> pd.DataFrame:
    """
    Download adjusted close prices from yfinance.
    Resamples to month-end. Returns a DataFrame indexed by date.

    Includes retry-with-backoff for yfinance rate limiting (HTTP 429).
    """
    import time

    print(f"  Downloading {len(tickers)} tickers: {', '.join(tickers)}")

    raw = None
    for attempt in range(1, max_retries + 1):
        raw = yf.download(
            tickers,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
        )
        # If we got something usable, stop retrying
        if raw is not None and not raw.empty:
            break
        wait = 2 ** attempt  # 2, 4, 8, 16 seconds
        print(f"  Empty response (attempt {attempt}/{max_retries}) — "
              f"likely rate limited. Waiting {wait}s before retry...")
        time.sleep(wait)

    if raw is None or raw.empty:
        raise RuntimeError(
            "\n  ✗ yfinance returned no data after retries.\n"
            "  Most likely cause: rate limiting (HTTP 429 'Too Many Requests').\n"
            "  Fixes:\n"
            "    1. Wait 5–10 minutes before re-running (the limit resets).\n"
            "    2. Run the pipeline LESS often — fetch once, then work off the saved CSVs.\n"
            "    3. Upgrade yfinance: pip install --upgrade yfinance\n"
        )

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        # Single ticker edge case
        prices = raw[["Close"]]
        prices.columns = tickers

    # Resample to month-end (last price of each month)
    prices = prices.resample(FREQUENCY).last()

    # Report what we got
    print(f"\n  Raw price coverage:")
    for col in prices.columns:
        valid = prices[col].dropna()
        if len(valid) > 0:
            print(f"    {col:<8} {valid.index[0].date()} → {valid.index[-1].date()}  "
                  f"({len(valid)} months)")
        else:
            print(f"    {col:<8} *** NO DATA ***")

    # Guard: if every ticker came back empty, fail clearly here rather than
    # letting a cryptic slice error surface downstream in trim_and_align.
    non_empty = [c for c in prices.columns if prices[c].notna().any()]
    if not non_empty:
        raise RuntimeError(
            "\n  ✗ All tickers returned empty (no usable prices).\n"
            "  This is almost always yfinance rate limiting.\n"
            "  Wait 5–10 minutes and re-run. Do not re-run repeatedly —\n"
            "  each failed attempt extends the rate-limit window.\n"
        )

    return prices


# ─────────────────────────────────────────────
# STEP 2 — BUILD PFORX→BNDX SPLICE
# ─────────────────────────────────────────────

def build_splice(prices: pd.DataFrame, splice: dict) -> tuple[pd.Series, dict]:
    """
    Chain-links a proxy fund and a primary ETF into a single return series.

    Method:
      - Compute monthly returns on each series independently
      - Use the proxy's returns before splice_date, the primary's on/after
      - Concatenate at the return level (NOT price level)
        → avoids artificial jump at the join date

    Returns:
      spliced_ret  : the chain-linked return series (named splice["output_name"])
      splice_info  : dict with metadata for the data quality report
    """
    proxy       = splice["proxy"]
    primary     = splice["primary"]
    splice_dt   = pd.Timestamp(splice["splice_date"])
    out_name    = splice["output_name"]

    if proxy not in prices.columns or primary not in prices.columns:
        raise ValueError(
            f"Splice tickers {proxy} and/or {primary} not found in prices. "
            f"Available: {list(prices.columns)}"
        )

    # Monthly returns on each leg
    proxy_ret   = prices[proxy].pct_change()
    primary_ret = prices[primary].pct_change()

    # Pre-splice: PFORX (proxy) | Post-splice: BNDX (primary)
    pre  = proxy_ret[proxy_ret.index   <  splice_dt]
    post = primary_ret[primary_ret.index >= splice_dt]

    spliced = pd.concat([pre, post]).sort_index()
    spliced.name = out_name

    # Overlap window for QA: last 12 months of PFORX, first 12 of BNDX
    overlap_start  = splice_dt - pd.DateOffset(months=12)
    overlap_end    = splice_dt + pd.DateOffset(months=12)
    proxy_overlap   = proxy_ret[overlap_start:overlap_end].dropna()
    primary_overlap = primary_ret[overlap_start:overlap_end].dropna()
    common_ol       = proxy_overlap.index.intersection(primary_overlap.index)

    splice_info = {
        "output_name":       out_name,
        "proxy":             proxy,
        "primary":           primary,
        "splice_date":       splice_dt.date(),
        "proxy_start":       proxy_ret.dropna().index[0].date() if proxy_ret.dropna().size > 0 else None,
        "primary_start":     primary_ret.dropna().index[0].date() if primary_ret.dropna().size > 0 else None,
        "spliced_months":    len(spliced.dropna()),
        "proxy_months_used": len(pre.dropna()),
        "primary_months_used": len(post.dropna()),
        "overlap_corr":      float(proxy_overlap.loc[common_ol].corr(primary_overlap.loc[common_ol]))
                             if len(common_ol) > 2 else None,
        "note": f"{proxy} (active fund) chain-linked into {primary} (passive index) "
                f"at {splice_dt.date()}; active/passive switch flagged in methodology."
    }

    print(f"\n  Splice: {proxy} → {primary} @ {splice_dt.date()}")
    print(f"    {proxy}  months used: {splice_info['proxy_months_used']}")
    print(f"    {primary} months used: {splice_info['primary_months_used']}")
    if splice_info["overlap_corr"] is not None:
        print(f"    Overlap correlation (QA): {splice_info['overlap_corr']:.3f}")
    print(f"    ⚠  {splice_info['note']}")

    return spliced, splice_info


# ─────────────────────────────────────────────
# STEP 3 — COMPUTE RETURNS
# ─────────────────────────────────────────────

def compute_returns(prices: pd.DataFrame, spliced_rets: list[pd.Series]) -> pd.DataFrame:
    """
    Compute monthly returns for all core assets, then apply each spliced series.

    For a splice whose output_name matches a UNIVERSE ticker (EMB/DBC/VWO) the
    spliced series replaces that column; otherwise (INTL_BOND) it is added as a
    new column. Proxy-only legs (PFORX, PYEMX, PCRIX, VEIEX) never appear here —
    they live in prices_raw for audit but are folded into their spliced output.
    """
    core_tickers = list(UNIVERSE.keys())

    # Returns on core universe (excludes proxy legs, which aren't in UNIVERSE)
    rets = prices[core_tickers].pct_change()

    # Apply each spliced series (replaces or adds its column)
    for s in spliced_rets:
        rets[s.name] = s

    return rets


# ─────────────────────────────────────────────
# STEP 4 — TRIM & ALIGN
# ─────────────────────────────────────────────

def trim_and_align(returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Produces two DataFrames:
      full_returns   : all available history per asset (unaligned, NaNs kept)
      aligned_returns: trimmed to the common window where ALL assets have data
                       — this is what feeds the optimizer
    """
    full = returns.copy()

    # Common window: first date where every column has data
    first_valid = returns.apply(lambda c: c.first_valid_index()).max()
    aligned     = returns.loc[first_valid:].dropna()

    print(f"\n  Full returns  : {full.index[0].date()} → {full.index[-1].date()} "
          f"({len(full)} months, some NaNs)")
    print(f"  Aligned window: {aligned.index[0].date()} → {aligned.index[-1].date()} "
          f"({len(aligned)} months, {len(aligned.columns)} assets, no NaNs)")
    print(f"  Binding asset (shortest history): "
          f"{returns.apply(lambda c: c.first_valid_index()).idxmax()}")

    return full, aligned


# ─────────────────────────────────────────────
# STEP 5 — SUMMARY STATISTICS
# ─────────────────────────────────────────────

def compute_summary_stats(returns: pd.DataFrame) -> pd.DataFrame:
    """Annualized return, vol, Sharpe, and data coverage per asset."""
    ann_ret = returns.mean() * PERIODS
    ann_vol = returns.std()  * np.sqrt(PERIODS)
    sharpe  = ann_ret / ann_vol

    labels = {**UNIVERSE, **{s["output_name"]: s["label"] for s in SPLICES}}

    stats = pd.DataFrame({
        "Label":        [labels.get(c, c) for c in returns.columns],
        "Ann. Return":  ann_ret.values,
        "Ann. Vol":     ann_vol.values,
        "Sharpe":       sharpe.values,
        "Observations": returns.count().values,
        "Start":        returns.apply(lambda c: c.first_valid_index()).dt.date.values,
        "End":          returns.apply(lambda c: c.last_valid_index()).dt.date.values,
    }, index=returns.columns)

    return stats.sort_values("Ann. Return", ascending=False)


# ─────────────────────────────────────────────
# STEP 6 — DATA QUALITY REPORT
# ─────────────────────────────────────────────

def data_quality_report(
    prices:       pd.DataFrame,
    full_returns: pd.DataFrame,
    splice_infos: list[dict],
) -> pd.DataFrame:
    """
    Checks each series for:
      - First / last valid date
      - Total missing months
      - Any gaps (non-contiguous NaN runs) mid-series
    """
    rows = []
    all_cols = full_returns.columns.tolist()

    for col in all_cols:
        s         = full_returns[col].dropna()
        all_dates = full_returns.index
        missing   = full_returns[col].isna().sum()

        # Detect interior gaps (NaN after first valid, before last valid)
        first = full_returns[col].first_valid_index()
        last  = full_returns[col].last_valid_index()
        if first and last:
            interior = full_returns.loc[first:last, col]
            gaps     = int(interior.isna().sum())
        else:
            gaps = 0

        rows.append({
            "Asset":           col,
            "First Month":     s.index[0].date() if len(s) else None,
            "Last Month":      s.index[-1].date() if len(s) else None,
            "Total Months":    len(s),
            "Missing Months":  int(missing),
            "Interior Gaps":   gaps,
            "OK":              "✓" if gaps == 0 and missing <= 5 else "⚠ CHECK",
        })

    dq = pd.DataFrame(rows).set_index("Asset")

    # Append one splice metadata note row per splice
    notes = pd.DataFrame([{
        "Asset":          f"SPLICE: {si['output_name']}",
        "First Month":    si["proxy_start"],
        "Last Month":     si["primary_start"],
        "Total Months":   si["spliced_months"],
        "Missing Months": 0,
        "Interior Gaps":  0,
        "OK":             si["note"],
    } for si in splice_infos]).set_index("Asset")

    dq = pd.concat([dq, notes])
    return dq


# ─────────────────────────────────────────────
# STEP 7 — SAVE OUTPUTS
# ─────────────────────────────────────────────

def save_outputs(
    prices_raw:      pd.DataFrame,
    full_returns:    pd.DataFrame,
    aligned_returns: pd.DataFrame,
    summary_stats:   pd.DataFrame,
    dq_report:       pd.DataFrame,
):
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # full_returns and dq_report are still computed (full_returns is needed to
    # derive the aligned set, and the coverage report is printed to the console),
    # but we no longer persist them — nothing consumes those CSVs.
    prices_raw.to_csv(f"{RAW_DIR}/prices_raw.csv")
    aligned_returns.to_csv(f"{OUTPUT_DIR}/returns_aligned.csv")
    summary_stats.to_csv(f"{OUTPUT_DIR}/summary_stats.csv")

    print(f"\n  Saved raw prices to {RAW_DIR}/prices_raw.csv")
    print(f"  Saved to {OUTPUT_DIR}/")
    print(f"    returns_aligned.csv     — ★ use this for optimizer (no NaNs)")
    print(f"    summary_stats.csv       — annualized stats per asset")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def run_pipeline():
    sep = "═" * 58

    print(f"\n{sep}")
    print("  GLOBAL MACRO DATA PIPELINE")
    print(f"  {START_DATE}  →  {END_DATE}  |  Monthly frequency")
    print(sep)

    # All tickers to fetch = core universe + every splice leg (proxy + primary).
    # dict.fromkeys de-dupes while preserving order (primaries like EMB/DBC/VWO
    # are already in UNIVERSE).
    splice_legs = [t for s in SPLICES for t in (s["proxy"], s["primary"])]
    all_tickers = list(dict.fromkeys(list(UNIVERSE.keys()) + splice_legs))

    # 1. Fetch
    print("\n[1/6] Fetching prices from yfinance...")
    prices = fetch_prices(all_tickers, START_DATE, END_DATE)

    # 2. Splice
    print(f"\n[2/6] Building {len(SPLICES)} splices...")
    spliced_rets, splice_infos = [], []
    for s in SPLICES:
        spliced_ret, splice_info = build_splice(prices, s)
        spliced_rets.append(spliced_ret)
        splice_infos.append(splice_info)

    # 3. Returns
    print("\n[3/6] Computing monthly returns...")
    full_rets = compute_returns(prices, spliced_rets)

    # 4. Trim & align
    print("\n[4/6] Trimming to aligned window...")
    full_rets, aligned_rets = trim_and_align(full_rets)

    # 5. Summary stats (on aligned window)
    print("\n[5/6] Computing summary statistics...")
    stats = compute_summary_stats(aligned_rets)
    print(f"\n  {'Asset':<14} {'Ann Ret':>8} {'Ann Vol':>8} {'Sharpe':>8}  Label")
    print("  " + "─" * 70)
    for idx, row in stats.iterrows():
        print(f"  {idx:<14} {row['Ann. Return']:>7.2%}  {row['Ann. Vol']:>7.2%}  "
              f"{row['Sharpe']:>7.3f}  {row['Label']}")

    # 6. Data quality
    print("\n[6/6] Running data quality checks...")
    dq = data_quality_report(prices, full_rets, splice_infos)
    print(dq[["First Month","Last Month","Total Months","Interior Gaps","OK"]].to_string())

    # Save
    print(f"\n{sep}")
    print("  SAVING OUTPUTS")
    print(sep)
    save_outputs(prices, full_rets, aligned_rets, stats, dq)

    print(f"\n{sep}")
    print("  PIPELINE COMPLETE")
    print(f"  Feed  data/market_data/processed/returns_aligned.csv  into the optimizer.")
    print(sep)

    return aligned_rets, stats


if __name__ == "__main__":
    returns, stats = run_pipeline()