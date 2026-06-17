# Investment Policy Statement (IPS)

This is our governing document. We (the humans) set the objectives and the limits
here; everything downstream, the optimizer, the method ensemble, the risk
report, has to operate inside these bounds. It's the same idea institutions use
to constrain a portfolio manager, and the same idea the Ang et al. (2026) paper
uses to govern an agentic pipeline: write the rules once, check every portfolio
against them. The machine-readable version lives in
`src/macro_portfolio/optimizer/ips.py` and is what the dashboard actually checks.

---

## 1. Objective
Build a globally diversified portfolio that earns a solid risk-adjusted return
and **beats a passive 60/40 benchmark** on Sharpe, without taking on more risk
than a balanced investor would tolerate.

- **Target volatility:** 10% annualized (acceptable band **8–12%**).
- **Risk-adjusted goal:** Sharpe at or above the 60/40 ACWI/IGOV benchmark.
- **Horizon:** long-term strategic allocation (pending final confirmation with Greg).

## 2. Investment universe
Nine liquid ETFs across four asset classes (top-down macro exposures, we don't
pick individual companies):

| Class | Holdings |
|---|---|
| US equity | SPY (large), VXF (mid/small) |
| Global equity | EFA (developed), VWO (emerging), EWC (Canada) |
| Bonds | AGG (US agg), INTL_BOND (ex-US, PFORX→BNDX splice), EMB (EM) |
| Commodities | DBC |

## 3. Constraints
- **Per-asset cap:** no single asset above **30%** (prevents over-concentration).
- **Total equity sleeve:** **≤ 60%** (SPY + VXF + EWC + EFA + VWO combined).
- **Fully invested:** weights sum to 100%, long-only (no shorting, no leverage).

## 4. Risk limits
- **Volatility:** keep realized vol inside the **8–12%** band.
- **Max drawdown:** peak-to-trough loss should not exceed **−25%**.
- **Benchmark:** **60% ACWI / 40% IGOV**, compared on the 2009+ overlap window.

## 5. Rebalancing
- Monthly cadence (matches our data frequency).
- Re-estimate inputs, re-optimize, and rebalance back inside the constraints.

## 6. Notes & open items
- Constraints (the 30% cap, 60% equity limit, 10% vol target) are our working
  assumptions, to be confirmed/tuned with the sponsor.
- Expected returns are still the historical-mean placeholder; the macro model
  swaps in next. Risk uses Ledoit-Wolf shrinkage by default.
- Returns are not yet excess-of-cash; once a 1-month cash series is added, Sharpe
  figures here tighten slightly.

> The dashboard's **Investment Policy** page checks the current portfolio against
> sections 3 and 4 live, and flags any breach.
