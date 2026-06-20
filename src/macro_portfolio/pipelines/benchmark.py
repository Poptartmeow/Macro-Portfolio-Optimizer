"""
Benchmark pipeline — 60/40 ACWI / IGOV.

Fetches the two benchmark ETFs from yfinance and builds the monthly-rebalanced
60% global equity (ACWI) / 40% intl government bond (IGOV) blended return series,
so the optimized portfolio can be compared against a passive global 60/40
(per sponsor guidance).

This is intentionally SEPARATE from data_pipeline.py so the core asset pipeline
is untouched.

Run:
    python -m macro_portfolio.pipelines.benchmark

Output (to data/market_data/processed/):
    benchmark_returns.csv  — columns: ACWI, IGOV, BENCH_60_40 (monthly returns)

Note: IGOV inception is 2009, so the blended series effectively starts 2009 —
the overlap window, which matches the benchmark window in our notes.
"""

import datetime as _dt
import time
import warnings

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

from macro_portfolio.paths import MARKET_PROCESSED

WEIGHTS = {"ACWI": 0.60, "IGOV": 0.40}  # global equity / intl govt bonds
START_DATE = "2008-01-01"
# First day of the current month so the in-progress month is excluded (yfinance
# `end` is exclusive) — keeps the benchmark aligned with the asset returns' last month-end.
END_DATE = _dt.date.today().replace(day=1).isoformat()
FREQUENCY = "ME"  # month-end


def fetch_monthly_prices(tickers: list[str], max_retries: int = 4) -> pd.DataFrame:
    """Download month-end adjusted-close prices, with retry/backoff for 429s."""
    raw = None
    for attempt in range(1, max_retries + 1):
        raw = yf.download(tickers, start=START_DATE, end=END_DATE,
                          auto_adjust=True, progress=False)
        if raw is not None and not raw.empty:
            break
        wait = 2 ** attempt
        print(f"  Empty response (attempt {attempt}/{max_retries}) — "
              f"likely rate limited. Waiting {wait}s...")
        time.sleep(wait)
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned no data after retries (rate limit?).")

    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(prices, pd.DataFrame):
        prices = prices.to_frame()
    return prices.resample(FREQUENCY).last()


def build_benchmark() -> pd.DataFrame:
    tickers = list(WEIGHTS.keys())
    prices = fetch_monthly_prices(tickers)
    rets = prices[tickers].pct_change()

    # Monthly-rebalanced blend: weights reset each month
    blended = sum(rets[t] * w for t, w in WEIGHTS.items())
    out = rets.copy()
    out["BENCH_60_40"] = blended
    out = out.dropna(how="all")
    # Trim to the common window (where both legs exist) for the blended series
    out = out.loc[out["BENCH_60_40"].first_valid_index():]
    return out


def main() -> None:
    print("Fetching ACWI + IGOV from yfinance...")
    bench = build_benchmark()
    path = MARKET_PROCESSED / "benchmark_returns.csv"
    bench.to_csv(path)
    span = f"{bench.index.min().date()} -> {bench.index.max().date()}"
    print(f"  Saved {path}")
    print(f"  60/40 benchmark: {len(bench)} months ({span})")
    ann = bench["BENCH_60_40"].mean() * 12
    vol = bench["BENCH_60_40"].std() * (12 ** 0.5)
    print(f"  Benchmark ann. return {ann*100:.2f}% | vol {vol*100:.2f}% | "
          f"Sharpe {ann/vol:.2f}")


if __name__ == "__main__":
    main()
