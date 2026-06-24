"""
Macro-regression expected returns for the optimizer.

For each asset, fits a multivariate OLS of monthly return on the chosen macro
factors (optionally lagged / month-over-month changes), then evaluates the
fitted model at the latest observed factor values to get a forward monthly
expected return (annualized). Pure: pass in the returns and factor panels.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from macro_portfolio.data import PERIODS, to_month

# A robust default factor set: one series per economic dimension
# (growth / inflation / rates / credit), kept small to avoid the collinearity
# that wrecks a kitchen-sink regression.
DEFAULT_ER_FACTORS = (
    "PMI_Composite_US",       # growth
    "INFLATION_ACCEL",        # inflation
    "IRSTCI_USA",             # rates / policy
    "SPREAD_BAA_AAA_USA",     # credit
)


def regression_expected_returns(
    rets: pd.DataFrame,
    facs: pd.DataFrame,
    factors: tuple[str, ...],
    *,
    lag: int = 1,
    transform: str = "level",
    hac_lags: int = 6,
    min_obs: int = 36,
    train_end: str | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """
    `train_end` (e.g. "2020-12-31") restricts the regression fit to data on or
    before that date — the train/test split — while μ is still evaluated at the
    most recent factor values (current macro state). When None, full history.

    Falls back to the asset's historical mean when the regression can't be fit.

    Returns:
      mu_ann : annualized expected return per asset (pd.Series)
      detail : per-asset diagnostics (R², n, source) for display
    """
    rets = rets.copy()
    facs = facs.copy()
    facs = facs[[c for c in factors if c in facs.columns]]

    rets.index = to_month(rets.index)
    facs.index = to_month(facs.index)

    if transform == "change":
        facs = facs.diff()

    X_all = facs.shift(lag)
    # Latest factor row that is fully populated for the chosen set
    latest = X_all.dropna(how="any")
    x_latest = latest.iloc[-1] if len(latest) else None

    train_cut = pd.Period(train_end, freq="M") if train_end else None

    hist = rets.mean() * PERIODS
    mu, rows = {}, []
    for a in rets.columns:
        df = pd.concat([rets[a], X_all], axis=1).dropna()
        if train_cut is not None:
            df = df[df.index <= train_cut]
        ok = (len(df) >= min_obs and x_latest is not None
              and not facs.empty and df.iloc[:, 1:].shape[1] > 0)
        if ok:
            try:
                X = sm.add_constant(df.iloc[:, 1:].values)
                res = sm.OLS(df[a].values, X).fit(
                    cov_type="HAC", cov_kwds={"maxlags": hac_lags})
                pred_monthly = float(res.params @ np.r_[1.0, x_latest.values])
                mu[a] = pred_monthly * PERIODS
                rows.append({"Asset": a, "Source": "macro model",
                             "R²": res.rsquared, "n": int(res.nobs)})
                continue
            except Exception:
                pass
        mu[a] = hist[a]
        rows.append({"Asset": a, "Source": "historical (fallback)",
                     "R²": np.nan, "n": np.nan})

    mu_ann = pd.Series(mu).reindex(rets.columns)
    detail = pd.DataFrame(rows).set_index("Asset")
    return mu_ann, detail
