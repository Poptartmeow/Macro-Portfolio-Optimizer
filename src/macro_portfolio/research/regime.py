"""
Macro regime classifier.

Labels each month into one of four business-cycle regimes from growth (PMI) and
its momentum, with inflation (CPI YoY) carried along as context. This mirrors the
macro agent in Ang et al. (2026) — expansion / late-cycle / recession / recovery —
but as a transparent rules-based classifier (no LLM).

Growth axis : composite PMI above/below 50 (the expansion/contraction line).
Momentum    : 3-month change in PMI (rising vs falling).

    PMI ≥ 50 & rising  → Expansion    (growth strong and accelerating)
    PMI ≥ 50 & falling → Slowdown     (late-cycle: strong but decelerating)
    PMI < 50 & falling → Contraction  (recession)
    PMI < 50 & rising  → Recovery     (turning up from a trough)
"""

from __future__ import annotations

import pandas as pd

REGIMES = ["Expansion", "Slowdown", "Contraction", "Recovery"]

PMI_COL = "PMI_Composite_US"
CPI_COL = "HEADLINE_CPI_USA"
EXPANSION_LINE = 50.0
MOMENTUM_LAG = 3   # months


def classify(factors: pd.DataFrame) -> pd.DataFrame:
    """
    factors: monthly DataFrame containing at least PMI_Composite_US and
             HEADLINE_CPI_USA (CPI year-on-year), indexed by month-end.
    Returns a DataFrame indexed by month with regime + supporting columns.
    """
    pmi = factors[PMI_COL].astype(float)
    mom = pmi - pmi.shift(MOMENTUM_LAG)
    above = pmi >= EXPANSION_LINE
    rising = mom > 0

    regime = pd.Series(index=pmi.index, dtype="object")
    regime[above & rising] = "Expansion"
    regime[above & ~rising] = "Slowdown"
    regime[~above & ~rising] = "Contraction"
    regime[~above & rising] = "Recovery"
    regime[mom.isna()] = None        # first few months have no momentum yet

    out = pd.DataFrame({
        "PMI": pmi,
        "PMI_mom3": mom,
        "regime": regime,
    })
    if CPI_COL in factors.columns:
        cpi = factors[CPI_COL].astype(float)
        out["CPI_YoY"] = cpi
        out["inflation_dir"] = (cpi - cpi.shift(MOMENTUM_LAG)).apply(
            lambda v: "rising" if v > 0 else ("falling" if v < 0 else "flat"))
    return out


def current(reg: pd.DataFrame) -> dict:
    """Latest regime, plus how many consecutive months it has held."""
    valid = reg["regime"].dropna()
    if valid.empty:
        return {"regime": None, "months_in_regime": 0, "as_of": None}
    last = valid.iloc[-1]
    n = 0
    for r in valid.iloc[::-1]:
        if r == last:
            n += 1
        else:
            break
    return {"regime": last, "months_in_regime": n, "as_of": valid.index[-1]}


def conditional_returns(returns: pd.DataFrame, reg: pd.DataFrame,
                        periods: int = 12) -> pd.DataFrame:
    """Annualized mean return per asset, conditioned on regime (assets × regimes)."""
    r = reg["regime"].reindex(returns.index)
    out = {}
    for name in REGIMES:
        mask = r == name
        if mask.any():
            out[name] = returns[mask].mean() * periods
    return pd.DataFrame(out).reindex(columns=[c for c in REGIMES if c in out])
