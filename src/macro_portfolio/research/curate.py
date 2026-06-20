"""
Curate the macro factor panel (2002→present) and build Greg's derived factors.

Source: data/macro_data/raw/us_macro_2002_2026.csv  (monthly, 2002-01 → 2026-04)
  Raw columns (renamed to the project's canonical *_USA convention here):
    HEADLINE_CPI_USA      headline CPI, year-on-year %
    CREDIT_SPRD_Baa_Aaa   → SPREAD_BAA_AAA_USA   (Baa−Aaa credit spread)
    IRSTCI_USA            short-term policy/interbank rate %
    SPREAD_10Y3M_USA      term spread, 10y − 3m
    SPREAD_10Y2Y_USA      term spread, 10y − 2y
    Div_Yield             → DIV_YIELD_USA         (S&P 500 dividend yield %, parsed from "x.xx%")

Derived factors added here (from the meeting with Greg):
  INFLATION_ACCEL   month-over-month change in headline CPI (T − T-1) — "use changes, not levels"
  EXCESS_DIV_YIELD  DIV_YIELD_USA − 10y yield, income from stocks vs bonds.
                    The 10y yield is reconstructed internally as IRSTCI + SPREAD_10Y3M
                    (verified ≈ the realized 10y: ~5.0% in 2002, ~4.2% in 2026), so the
                    factor stays sourced from the same FRED panel.
  LOG_VIX           log of month-end VIX (^VIX via yfinance); VIX is right-skewed → log
  PMI_CHANGE        month-over-month change in composite PMI (per Greg: "MoM change = PMI")

Still TODO — need external sourcing, not present in any file yet:
  HY_SPREAD_USA              high-yield credit spread (to replace Baa−Aaa once sourced)
  EARNINGS_YIELD_PREMIUM     S&P 500 earnings/price ratio

Gap-filling philosophy (unchanged): only carry information FORWARD or interpolate
between known points — never use future values to fill the past (no look-ahead).
First-period NaNs in the change factors are inherent (no prior month), not gaps.

Outputs (data/macro_data/processed/):
  macro_monthly.csv   — clean monthly factor panel (month-end index)
  macro_fill_log.csv  — one row per factor: source/derivation, missing %, fill action

Run:
    python -m macro_portfolio.research.curate
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from macro_portfolio import paths

warnings.filterwarnings("ignore")

RAW = paths.MACRO_RAW / "us_macro_2002_2026.csv"
PMI = paths.MACRO_PMI / "PMI_Composite_US.csv"
CURATED = paths.MACRO_PROCESSED

# raw → canonical column names
RENAME = {
    "CREDIT_SPRD_Baa_Aaa": "SPREAD_BAA_AAA_USA",
    "Div_Yield": "DIV_YIELD_USA",
}

# Factors we know we want but can't build yet (logged so the panel is honest).
PENDING = {
    "HY_SPREAD_USA": "high-yield credit spread (to replace Baa−Aaa)",
    "EARNINGS_YIELD_PREMIUM": "S&P 500 earnings/price ratio",
}

FINAL_ORDER = [
    "HEADLINE_CPI_USA", "INFLATION_ACCEL",
    "DIV_YIELD_USA", "EXCESS_DIV_YIELD",
    "SPREAD_10Y2Y_USA", "SPREAD_10Y3M_USA", "SPREAD_BAA_AAA_USA",
    "IRSTCI_USA", "LOG_VIX", "PMI_CHANGE",
]


def _load_base() -> pd.DataFrame:
    """Read the 2002 panel, parse the % dividend yield, month-end index, rename."""
    raw = pd.read_csv(RAW, index_col=0)
    raw.index = pd.PeriodIndex(raw.index, freq="M").to_timestamp(how="end").normalize()
    raw.index.name = "Month"
    if raw["Div_Yield"].dtype == object:
        raw["Div_Yield"] = raw["Div_Yield"].str.rstrip("%").astype(float)
    return raw.rename(columns=RENAME)


def _gap_fill(s: pd.Series) -> tuple[pd.Series, str, int]:
    """Time-interpolate interior gaps, then ffill/bfill the edges. Returns (series, action, n)."""
    if not s.isna().any():
        return s, "clean", 0
    interior = s.interpolate(method="time", limit_area="inside")
    n_interp = int((interior.notna() & s.isna()).sum())
    filled = interior.ffill().bfill()
    n_edge = int((filled.notna() & interior.isna()).sum())
    action = "time-interpolated interior" + (", ffill/bfill edges" if n_edge else "")
    return filled, action, n_interp + n_edge


def _fetch_log_vix(index: pd.DatetimeIndex) -> tuple[pd.Series | None, str]:
    """Month-end log(VIX) aligned to `index`. Network; degrades gracefully on failure."""
    try:
        import yfinance as yf
        raw = yf.download("^VIX", start="2001-12-01",
                          end=(index.max() + pd.offsets.MonthEnd(1)).date().isoformat(),
                          auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            return None, "PENDING — ^VIX fetch returned empty"
        close = raw["Close"]
        close = close.iloc[:, 0] if isinstance(close, pd.DataFrame) else close
        vix_me = close.resample("ME").last()
        vix_me.index = vix_me.index.normalize()
        log_vix = np.log(vix_me).reindex(index)
        return log_vix, "log(month-end ^VIX) via yfinance"
    except Exception as e:  # noqa: BLE001 — keep curation runnable offline
        return None, f"PENDING — ^VIX fetch failed ({type(e).__name__})"


def _pmi_change(index: pd.DatetimeIndex) -> tuple[pd.Series | None, str]:
    """Month-over-month change in composite PMI, aligned to `index`."""
    if not PMI.exists():
        return None, "PENDING — PMI_Composite_US.csv not found (run pipelines.pmi)"
    pmi = pd.read_csv(PMI, parse_dates=["date"]).set_index("date")["PMI_Composite_US"]
    pmi.index = pmi.index.to_period("M").to_timestamp(how="end").normalize()
    return pmi.diff().reindex(index), "month-over-month change in composite PMI"


def curate_macro() -> tuple[pd.DataFrame, pd.DataFrame]:
    base = _load_base()
    out = pd.DataFrame(index=base.index)
    log_rows: list[dict] = []

    def record(col, source, miss_frac=0.0, action="clean", n=0):
        log_rows.append({"column": col, "source": source,
                         "missing_pct": round(miss_frac * 100, 1),
                         "action": action, "n_filled": n})

    # 1. cleaned base levels
    for col in base.columns:
        miss = float(base[col].isna().mean())
        filled, action, n = _gap_fill(base[col])
        out[col] = filled
        record(col, "raw panel (FRED/OECD, 2002)", miss, action, n)

    # 2. derived from the cleaned base
    out["INFLATION_ACCEL"] = out["HEADLINE_CPI_USA"].diff()
    record("INFLATION_ACCEL", "derived: ΔHEADLINE_CPI (T − T-1)",
           action="derived; first month NaN (no prior period)")

    tenyr = out["IRSTCI_USA"] + out["SPREAD_10Y3M_USA"]   # ≈ realized 10y yield
    out["EXCESS_DIV_YIELD"] = out["DIV_YIELD_USA"] - tenyr
    record("EXCESS_DIV_YIELD", "derived: DIV_YIELD − (IRSTCI + SPREAD_10Y3M)")

    # 3. fetched / external-but-derivable
    log_vix, vix_action = _fetch_log_vix(out.index)
    if log_vix is not None:
        out["LOG_VIX"] = log_vix
    record("LOG_VIX", "yfinance ^VIX",
           miss_frac=float(log_vix.isna().mean()) if log_vix is not None else 1.0,
           action=vix_action)

    pmi_chg, pmi_action = _pmi_change(out.index)
    if pmi_chg is not None:
        out["PMI_CHANGE"] = pmi_chg
    record("PMI_CHANGE", "macro_data/processed/pmi/PMI_Composite_US.csv",
           miss_frac=float(pmi_chg.isna().mean()) if pmi_chg is not None else 1.0,
           action=pmi_action)

    # 4. honest TODO rows for the factors we still owe Greg
    for col, desc in PENDING.items():
        record(col, desc, miss_frac=1.0, action="PENDING — external source required")

    out = out[[c for c in FINAL_ORDER if c in out.columns]]
    fill_log = pd.DataFrame(log_rows)
    return out, fill_log


def main() -> None:
    CURATED.mkdir(parents=True, exist_ok=True)
    macro, log = curate_macro()
    macro.to_csv(CURATED / "macro_monthly.csv")
    log.to_csv(CURATED / "macro_fill_log.csv", index=False)
    print(f"  Wrote {CURATED/'macro_monthly.csv'}  "
          f"({macro.shape[0]} months × {macro.shape[1]} factors, "
          f"{macro.index.min().date()} → {macro.index.max().date()})")
    print(f"  Wrote {CURATED/'macro_fill_log.csv'}")
    print("\n  Fill log:")
    print(log.to_string(index=False))


if __name__ == "__main__":
    main()
