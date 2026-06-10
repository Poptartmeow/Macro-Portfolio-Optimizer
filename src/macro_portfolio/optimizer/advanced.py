"""
Alternative optimizer objectives that let expected returns actually move the
portfolio (the baseline max-return-at-target-vol pins assets to the box bounds,
so the macro expected-return model has almost no effect on the weights).

max_sharpe_l2:
    Maximize the Sharpe ratio minus an L2 (ridge) penalty on the weights.
    The L2 term rewards diversification, so the solution sits inside the box
    rather than collapsing onto 2-3 assets — and it responds to changes in the
    expected-return vector, which is the whole point of the macro model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def max_sharpe_l2(
    mu: pd.Series,
    cov: pd.DataFrame,
    min_weight: float = 0.0,
    max_weight: float = 0.30,
    l2: float = 0.0,
    group_bounds: list[tuple[list[str], float, float]] | None = None,
) -> dict:
    """
    Maximize  (wᵀμ)/sqrt(wᵀΣw)  −  l2·‖w‖²   subject to:
      - weights sum to 1
      - min_weight ≤ wᵢ ≤ max_weight
      - optional group bounds: each (assets, lo, hi) constrains the group's
        total weight to [lo, hi] (e.g. cap total equity at 60%).
    """
    assets = mu.index.tolist()
    n = len(assets)
    mu_arr = mu.values
    cov_arr = cov.loc[assets, assets].values
    bounds = [(min_weight, max_weight)] * n

    def neg_obj(w):
        vol = np.sqrt(w @ cov_arr @ w)
        sharpe = (w @ mu_arr) / vol if vol > 0 else -1e9
        return -(sharpe - l2 * np.sum(w ** 2))

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if group_bounds:
        idx = {a: i for i, a in enumerate(assets)}
        for members, lo, hi in group_bounds:
            cols = [idx[m] for m in members if m in idx]
            constraints.append({"type": "ineq",
                                "fun": (lambda w, c=cols, lo=lo: np.sum(w[c]) - lo)})
            constraints.append({"type": "ineq",
                                "fun": (lambda w, c=cols, hi=hi: hi - np.sum(w[c]))})

    w0 = np.clip(np.ones(n) / n, min_weight, max_weight)
    w0 = w0 / w0.sum()
    res = minimize(neg_obj, w0, method="SLSQP", bounds=bounds,
                   constraints=constraints,
                   options={"ftol": 1e-12, "maxiter": 1000})

    w = res.x
    vol = float(np.sqrt(w @ cov_arr @ w))
    ret = float(w @ mu_arr)
    return {
        "weights": pd.Series(w, index=assets).sort_values(ascending=False),
        "expected_return": ret,
        "volatility": vol,
        "sharpe_ratio": ret / vol if vol > 0 else np.nan,
        "converged": bool(res.success),
        "n_at_bound": int(np.sum((w <= min_weight + 1e-4) |
                                 (w >= max_weight - 1e-4))),
        "effective_n": float(1.0 / np.sum(w ** 2)),  # diversification (1..n)
    }
