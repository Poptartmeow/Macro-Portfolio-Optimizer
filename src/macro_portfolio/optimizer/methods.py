"""
Portfolio-construction method library + ensemble.

Each method maps (mu, cov, min_w, max_w) -> weights (pd.Series, long-only,
summing to 1). Heuristics ignore `mu`; the optimization-based methods respect
the [min_w, max_w] box. This mirrors the portfolio-construction agents in
Ang, Azimbayev & Kim (2026, "The Self-Driving Portfolio"), Exhibit 5 — but
implemented as pure-quant methods, so there is NO lookahead / backtest
contamination (no LLM is in this loop).

mu and cov are expected ANNUALIZED (as produced elsewhere in the package).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.optimize import minimize
from scipy.spatial.distance import squareform

# Display families (matches the paper's categories)
CATEGORY = {
    "Equal Weight": "Heuristic",
    "Inverse Volatility": "Heuristic",
    "Inverse Variance": "Heuristic",
    "Max Sharpe": "Return-optimized",
    "Min Variance": "Risk-structured",
    "Risk Parity": "Risk-structured",
    "Hierarchical Risk Parity": "Risk-structured",
    "Max Diversification": "Risk-structured",
}


# ─────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────

def _normalize(w: np.ndarray, assets) -> pd.Series:
    w = np.clip(np.asarray(w, dtype=float), 0.0, None)
    s = w.sum()
    w = w / s if s > 0 else np.ones(len(w)) / len(w)
    return pd.Series(w, index=assets)


def _solve(obj, n, min_w, max_w, x0=None) -> np.ndarray:
    bounds = [(min_w, max_w)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    x0 = np.ones(n) / n if x0 is None else x0
    res = minimize(obj, x0, method="SLSQP", bounds=bounds, constraints=cons,
                   options={"ftol": 1e-12, "maxiter": 1000})
    return res.x


def _corr_from_cov(cov: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.diag(cov))
    return cov / np.outer(d, d)


# ─────────────────────────────────────────────
# A. Heuristics (ignore mu)
# ─────────────────────────────────────────────

def equal_weight(mu, cov, min_w=0.0, max_w=1.0) -> pd.Series:
    n = len(mu)
    return pd.Series(np.ones(n) / n, index=mu.index)


def inverse_volatility(mu, cov, min_w=0.0, max_w=1.0) -> pd.Series:
    vol = np.sqrt(np.diag(cov.values))
    return _normalize(1.0 / vol, mu.index)


def inverse_variance(mu, cov, min_w=0.0, max_w=1.0) -> pd.Series:
    var = np.diag(cov.values)
    return _normalize(1.0 / var, mu.index)


# ─────────────────────────────────────────────
# B. Return-optimized
# ─────────────────────────────────────────────

def max_sharpe(mu, cov, min_w=0.0, max_w=1.0) -> pd.Series:
    C, m, n = cov.values, mu.values, len(mu)

    def neg(w):
        v = np.sqrt(w @ C @ w)
        return -(w @ m) / v if v > 0 else 0.0

    return _normalize(_solve(neg, n, min_w, max_w), mu.index)


# ─────────────────────────────────────────────
# C. Risk-structured (ignore mu)
# ─────────────────────────────────────────────

def min_variance(mu, cov, min_w=0.0, max_w=1.0) -> pd.Series:
    C, n = cov.values, len(mu)
    return _normalize(_solve(lambda w: w @ C @ w, n, min_w, max_w), mu.index)


def max_diversification(mu, cov, min_w=0.0, max_w=1.0) -> pd.Series:
    C = cov.values
    s = np.sqrt(np.diag(C))
    n = len(mu)

    def neg(w):
        den = np.sqrt(w @ C @ w)
        return -(w @ s) / den if den > 0 else 0.0

    return _normalize(_solve(neg, n, min_w, max_w), mu.index)


def risk_parity(mu, cov, min_w=0.0, max_w=1.0) -> pd.Series:
    """Equal risk contribution: each asset contributes equally to portfolio variance."""
    C, n = cov.values, len(mu)

    def obj(w):
        port_var = w @ C @ w
        rc = w * (C @ w)                 # risk contribution per asset
        target = port_var / n
        return np.sum((rc - target) ** 2)

    lo = max(min_w, 1e-6)               # ERC needs strictly positive weights
    return _normalize(_solve(obj, n, lo, max_w), mu.index)


def hierarchical_risk_parity(mu, cov, min_w=0.0, max_w=1.0) -> pd.Series:
    """López de Prado (2016) HRP: cluster, quasi-diagonalize, recursive bisection."""
    C = cov.values
    n = len(mu)
    if n < 2:
        return pd.Series(np.ones(n), index=mu.index)

    corr = _corr_from_cov(C)
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, None))
    link = linkage(squareform(dist, checks=False), method="single")
    order = [int(i) for i in to_tree(link).pre_order()]   # quasi-diagonal leaf order

    def cluster_var(idx: list[int]) -> float:
        sub = C[np.ix_(idx, idx)]
        iv = 1.0 / np.diag(sub)
        iv = iv / iv.sum()
        return float(iv @ sub @ iv)

    w = np.ones(n)
    clusters = [order]
    while clusters:
        # split every cluster with >1 item into two contiguous halves
        clusters = [c[j:k] for c in clusters
                    for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]
            v0, v1 = cluster_var(c0), cluster_var(c1)
            alpha = 1.0 - v0 / (v0 + v1)
            for j in c0:
                w[j] *= alpha
            for j in c1:
                w[j] *= (1.0 - alpha)
    return _normalize(w, mu.index)


# ─────────────────────────────────────────────
# registry + scoring + ensemble
# ─────────────────────────────────────────────

METHODS = {
    "Equal Weight": equal_weight,
    "Inverse Volatility": inverse_volatility,
    "Inverse Variance": inverse_variance,
    "Max Sharpe": max_sharpe,
    "Min Variance": min_variance,
    "Risk Parity": risk_parity,
    "Hierarchical Risk Parity": hierarchical_risk_parity,
    "Max Diversification": max_diversification,
}


def build_all(mu: pd.Series, cov: pd.DataFrame,
              min_w: float = 0.0, max_w: float = 1.0) -> dict[str, pd.Series]:
    """Run every method; skip any that fail rather than crashing the page."""
    out = {}
    for name, fn in METHODS.items():
        try:
            out[name] = fn(mu, cov, min_w, max_w)
        except Exception:
            continue
    return out


def score(weights: pd.Series, mu: pd.Series, cov: pd.DataFrame) -> dict:
    w = weights.reindex(mu.index).fillna(0.0).values
    vol = float(np.sqrt(w @ cov.values @ w))
    ret = float(w @ mu.values)
    return {
        "Ann. Return": ret,
        "Ann. Vol": vol,
        "Sharpe": ret / vol if vol > 0 else np.nan,
        "Max Weight": float(np.max(w)),
        "Effective N": float(1.0 / np.sum(w ** 2)) if np.sum(w ** 2) > 0 else np.nan,
    }


def ensemble(weights: dict[str, pd.Series], scheme: str = "inverse_te") -> pd.Series:
    """
    Combine method portfolios into one (the paper's CIO step).
      equal       — simple average of the method weight vectors
      inverse_te  — weight each method inversely to its distance from the
                    consensus centroid (closer to consensus -> higher weight)
    """
    W = pd.DataFrame(weights).fillna(0.0)            # assets x methods
    if scheme == "equal":
        combined = W.mean(axis=1)
    else:
        centroid = W.mean(axis=1)
        te = ((W.sub(centroid, axis=0)) ** 2).sum(axis=0).pow(0.5)  # per method
        wt = 1.0 / (te + 1e-6)
        wt = wt / wt.sum()
        combined = W.mul(wt, axis=1).sum(axis=1)
    return _normalize(combined.values, W.index)
