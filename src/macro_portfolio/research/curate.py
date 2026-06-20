"""
Curate the raw macro panel into a clean monthly factor table.

Problems in data/macro_data/raw/us_macro_2007_2026.csv this fixes (all documented in the
fill-log it writes):
  1. ~23 duplicate rows per month  -> collapse to one monthly observation (mean).
  2. DIV_YIELD_USA ~28% missing     -> time-interpolate interior gaps, then
                                       forward/back fill the edges. Flagged.
  3. HY_SPREAD_USA ~85% missing     -> too sparse to reconstruct -> DROPPED.
  4. Small interior gaps elsewhere  -> forward-filled (last known value, which
                                       is what an investor actually had).

Gap-filling philosophy: only ever carry information FORWARD or interpolate
between known points. Never use future values to fill the past (look-ahead).

Outputs (to data/macro_data/processed/):
  macro_monthly.csv   — clean, deduped, gap-filled monthly factors (month-end)
  macro_fill_log.csv  — one row per column: what was done and how many filled

Run:
    python -m macro_portfolio.research.curate
"""

from __future__ import annotations

import pandas as pd

from macro_portfolio import paths

RAW = paths.MACRO_RAW / "us_macro_2007_2026.csv"
CURATED = paths.MACRO_PROCESSED
DROP_THRESHOLD = 0.60  # drop a column if more than this fraction is missing


def curate_macro() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(RAW)

    # 1. collapse intramonth duplicate rows to one monthly mean
    raw["Month"] = pd.PeriodIndex(raw["Month"], freq="M")
    monthly = raw.groupby("Month").mean(numeric_only=True)
    monthly.index = monthly.index.to_timestamp(how="end").normalize()

    log_rows = []
    out = monthly.copy()
    for col in monthly.columns:
        miss = monthly[col].isna()
        miss_frac = float(miss.mean())

        if miss_frac > DROP_THRESHOLD:
            out = out.drop(columns=col)
            log_rows.append({"column": col, "missing_pct": round(miss_frac * 100, 1),
                             "action": "DROPPED (too sparse to reconstruct)",
                             "n_filled": 0})
            continue

        if miss_frac > 0:
            s = monthly[col]
            interior = s.interpolate(method="time", limit_area="inside")
            n_interp = int((interior.notna() & s.isna()).sum())
            filled = interior.ffill().bfill()
            n_edge = int((filled.notna() & interior.isna()).sum())
            out[col] = filled
            action = (f"time-interpolated interior, ffill/bfill edges"
                      if n_edge else "time-interpolated interior")
            log_rows.append({"column": col, "missing_pct": round(miss_frac * 100, 1),
                             "action": action, "n_filled": n_interp + n_edge})
        else:
            log_rows.append({"column": col, "missing_pct": 0.0,
                             "action": "clean (deduped only)", "n_filled": 0})

    fill_log = pd.DataFrame(log_rows).sort_values("missing_pct", ascending=False)
    return out, fill_log


def main() -> None:
    CURATED.mkdir(parents=True, exist_ok=True)
    macro, log = curate_macro()
    macro.to_csv(CURATED / "macro_monthly.csv")
    log.to_csv(CURATED / "macro_fill_log.csv", index=False)
    print(f"  Wrote {CURATED/'macro_monthly.csv'}  "
          f"({macro.shape[0]} months x {macro.shape[1]} factors, "
          f"{macro.index.min().date()} -> {macro.index.max().date()})")
    print(f"  Wrote {CURATED/'macro_fill_log.csv'}")
    print("\n  Fill log:")
    print(log.to_string(index=False))


if __name__ == "__main__":
    main()
