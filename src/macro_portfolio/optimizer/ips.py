"""
Investment Policy Statement (IPS) — machine-readable constraints + compliance check.

The IPS is the governing document for the whole pipeline (the role it plays in
Ang et al. 2026): the human sets the objectives and limits, and every portfolio
is checked against them. docs/IPS.md is the human-readable version; this module
is the single source of truth the dashboard checks portfolios against.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Equity sleeves (for the group cap)
EQUITY_ASSETS = ("SPY", "VXF", "EWC", "EFA", "VWO")


@dataclass(frozen=True)
class IPS:
    target_vol: float = 0.10
    vol_band: tuple[float, float] = (0.08, 0.12)
    max_weight: float = 0.30          # per-asset cap
    min_weight: float = 0.0
    equity_cap: float = 0.60          # total equity sleeve
    max_drawdown_limit: float = -0.25  # peak-to-trough floor
    benchmark: str = "60/40 ACWI/IGOV"
    equity_assets: tuple[str, ...] = EQUITY_ASSETS


DEFAULT_IPS = IPS()


def check_compliance(weights: pd.Series, *, vol: float | None = None,
                     max_drawdown: float | None = None,
                     ips: IPS = DEFAULT_IPS) -> list[dict]:
    """
    Returns a list of {rule, ok, detail} checks. vol / max_drawdown are optional —
    pass them in to also check the volatility band and drawdown limit.
    """
    w = weights.fillna(0.0)
    checks: list[dict] = []

    maxw = float(w.max())
    checks.append({"rule": f"Per-asset weight ≤ {ips.max_weight:.0%}",
                   "ok": maxw <= ips.max_weight + 1e-6,
                   "detail": f"largest holding = {maxw:.1%}"})

    eq = float(w.reindex(ips.equity_assets).fillna(0.0).sum())
    checks.append({"rule": f"Total equity ≤ {ips.equity_cap:.0%}",
                   "ok": eq <= ips.equity_cap + 1e-6,
                   "detail": f"equity sleeve = {eq:.1%}"})

    checks.append({"rule": "Fully invested (weights sum to 100%)",
                   "ok": abs(float(w.sum()) - 1.0) < 1e-4,
                   "detail": f"sum = {w.sum():.1%}"})

    if vol is not None:
        lo, hi = ips.vol_band
        checks.append({"rule": f"Volatility within {lo:.0%}–{hi:.0%} band",
                       "ok": lo - 1e-9 <= vol <= hi + 1e-9,
                       "detail": f"realized vol = {vol:.1%}"})

    if max_drawdown is not None:
        checks.append({"rule": f"Max drawdown ≥ {ips.max_drawdown_limit:.0%}",
                       "ok": max_drawdown >= ips.max_drawdown_limit - 1e-9,
                       "detail": f"in-sample max DD = {max_drawdown:.1%}"})

    return checks


def is_compliant(checks: list[dict]) -> bool:
    return all(c["ok"] for c in checks)
