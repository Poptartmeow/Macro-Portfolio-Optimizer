"""
Univariate macro regression sweep.

Runs asset_ret(t) ~ factor(t-lag) for every (asset, factor) pair with
HAC/Newey-West standard errors, returning beta / t-stat / n / R² tables. Pure:
pass in the returns and factor panels (e.g. from macro_portfolio.data).
"""

from __future__ import annotations

import pandas as pd
import statsmodels.api as sm

from macro_portfolio.data import to_month


def univariate_sweep(rets: pd.DataFrame, facs: pd.DataFrame, *,
                     lag: int = 0, transform: str = "level",
                     hac_lags: int = 6, min_obs: int = 24):
    """
    For each (asset, factor): OLS of asset return on the (optionally lagged,
    optionally month-over-month differenced) factor.

    transform: 'level' (raw factor) or 'change' (MoM diff).
    Returns (beta_df, tstat_df, n_df, r2_df) as assets × factors DataFrames.
    """
    rets = rets.copy()
    facs = facs.copy()
    rets.index = to_month(rets.index)
    facs.index = to_month(facs.index)

    if transform == "change":
        facs = facs.diff()

    assets = list(rets.columns)
    factors = list(facs.columns)
    beta = pd.DataFrame(index=assets, columns=factors, dtype=float)
    tstat = pd.DataFrame(index=assets, columns=factors, dtype=float)
    nobs = pd.DataFrame(index=assets, columns=factors, dtype=float)
    r2 = pd.DataFrame(index=assets, columns=factors, dtype=float)

    for f in factors:
        x = facs[f].shift(lag)
        for a in assets:
            df = pd.concat([rets[a], x], axis=1, keys=["y", "x"]).dropna()
            if len(df) < min_obs or df["x"].nunique() < 3:
                continue
            X = sm.add_constant(df["x"].values)
            try:
                res = sm.OLS(df["y"].values, X).fit(
                    cov_type="HAC", cov_kwds={"maxlags": hac_lags})
            except Exception:
                continue
            beta.loc[a, f] = res.params[1]
            tstat.loc[a, f] = res.tvalues[1]
            nobs.loc[a, f] = int(res.nobs)
            r2.loc[a, f] = res.rsquared
    return beta, tstat, nobs, r2
