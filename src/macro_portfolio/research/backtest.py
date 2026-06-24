"""
Walk-forward rolling re-optimization backtest.

For each out-of-sample month after `train_end`: refit each asset's macro
regression on all prior data (expanding window, lagged factors), build μ from
the latest knowable factors, estimate Σ from trailing returns, optimize, and
record realized next-month return + turnover. Pure: pass in the panels.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from macro_portfolio.data import PERIODS, to_month
from macro_portfolio.optimizer import optimizer as O
from macro_portfolio.optimizer.advanced import max_sharpe_l2
from macro_portfolio.risk.covariance import sample_cov, ledoit_wolf_cov


def rolling_backtest(
    rets: pd.DataFrame,
    facs: pd.DataFrame,
    bench: pd.DataFrame | None,
    factors: tuple[str, ...],
    lag: int,
    transform: str,
    train_end: str,
    objective: str,
    cov_choice: str,
    min_w: float,
    max_w: float,
    target_vol: float,
    l2: float,
    eq_cap: float,
    equity: tuple[str, ...],
    hac_lags: int = 6,
    min_obs: int = 36,
) -> dict:
    """
    Returns a dict of DataFrames/Series:
      perf, weights, turnover, trades, summary, oos_start, oos_end, avg_turnover
    (or {"empty": True} if no out-of-sample months could be optimized).
    """
    rets = rets.copy()
    facs = facs.copy()
    facs = facs[[c for c in factors if c in facs.columns]]
    rets.index = to_month(rets.index)
    facs.index = to_month(facs.index)
    if transform == "change":
        facs = facs.diff()
    X_all = facs.shift(lag)

    assets = list(rets.columns)
    equity = [e for e in equity if e in assets]
    train_cut = pd.Period(train_end, freq="M")
    oos_months = [t for t in rets.index if t > train_cut]

    def fit_mu(upto: pd.Period) -> pd.Series | None:
        """Expected returns using data through `upto`, evaluated at month upto's factors."""
        x_now = X_all.loc[upto] if upto in X_all.index else None
        if x_now is None or x_now.isna().any():
            return None
        hist = rets.loc[:upto].mean() * PERIODS
        out = {}
        for a in assets:
            df = pd.concat([rets[a], X_all], axis=1).dropna()
            df = df[df.index < upto]            # strictly past data
            if len(df) >= min_obs:
                try:
                    X = sm.add_constant(df.iloc[:, 1:].values)
                    res = sm.OLS(df[a].values, X).fit(
                        cov_type="HAC", cov_kwds={"maxlags": hac_lags})
                    out[a] = float(res.params @ np.r_[1.0, x_now.values]) * PERIODS
                    continue
                except Exception:
                    pass
            out[a] = hist[a]
        return pd.Series(out).reindex(assets)

    weights_rows, realized = {}, {}
    prev_w = None
    turnover = {}
    for t in oos_months:
        mu = fit_mu(t)
        if mu is None:
            continue
        train_rets = rets.loc[:t].iloc[:-1].dropna()   # returns strictly before t
        if len(train_rets) < min_obs:
            continue
        if cov_choice.startswith("Ledoit"):
            cov, _ = ledoit_wolf_cov(train_rets)
        else:
            cov = sample_cov(train_rets)
        try:
            if objective.startswith("Max return"):
                res = O.optimize(mu, cov, target_vol=target_vol,
                                 min_weight=min_w, max_weight=max_w)
            else:
                res = max_sharpe_l2(mu, cov, min_weight=min_w, max_weight=max_w,
                                    l2=l2, group_bounds=[(equity, 0.0, eq_cap)])
        except Exception:
            continue
        w = res["weights"].reindex(assets).fillna(0.0)
        weights_rows[t] = w
        realized[t] = float((w * rets.loc[t]).sum())
        turnover[t] = 0.5 * float((w - prev_w).abs().sum()) if prev_w is not None else np.nan
        prev_w = w

    if not weights_rows:
        return {"empty": True}

    weights = pd.DataFrame(weights_rows).T
    weights.index = weights.index.to_timestamp(how="end").normalize()
    port = pd.Series(realized).rename("Strategy")
    port.index = port.index.to_timestamp(how="end").normalize()
    turn = pd.Series(turnover).rename("Turnover")
    turn.index = turn.index.to_timestamp(how="end").normalize()

    perf = port.to_frame()
    if bench is not None and "BENCH_60_40" in bench.columns:
        b = bench["BENCH_60_40"].rename("Benchmark 60/40")
        perf = perf.join(b, how="left")

    ann = perf.mean() * PERIODS
    vol = perf.std() * np.sqrt(PERIODS)
    summary = pd.DataFrame({"Ann. Return": ann, "Ann. Vol": vol,
                            "Sharpe": ann / vol})

    last_w = weights.iloc[-1]
    prev = weights.iloc[-2] if len(weights) > 1 else pd.Series(0.0, index=assets)
    trades = pd.DataFrame({"Weight": last_w, "Prev weight": prev,
                           "Trade (Δw)": last_w - prev})

    return {
        "empty": False,
        "perf": perf,
        "weights": weights,
        "turnover": turn,
        "trades": trades,
        "summary": summary,
        "oos_start": port.index.min(),
        "oos_end": port.index.max(),
        "avg_turnover": float(turn.mean(skipna=True)),
    }
