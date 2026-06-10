"""
Covariance estimators for the optimizer.

The sample covariance is noisy and near-singular when assets are highly
correlated (our equity sleeves correlate 0.85-0.92). Ledoit-Wolf shrinkage
pulls the sample matrix toward a structured target, which stabilizes the
optimizer and prevents the knife-edge weights Greg warned about.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS = 12  # months per year


def sample_cov(returns: pd.DataFrame, annualize: bool = True) -> pd.DataFrame:
    cov = returns.cov()
    if annualize:
        cov = cov * PERIODS
    return cov


def ledoit_wolf_cov(returns: pd.DataFrame, annualize: bool = True
                    ) -> tuple[pd.DataFrame, float]:
    """
    Ledoit-Wolf shrinkage covariance.

    Returns (cov, shrinkage_intensity) where shrinkage_intensity in [0, 1]
    is how far the estimate was pulled toward the structured target
    (0 = pure sample, 1 = pure target).
    """
    try:
        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf().fit(returns.values)
        cov = pd.DataFrame(lw.covariance_, index=returns.columns,
                           columns=returns.columns)
        shrink = float(lw.shrinkage_)
    except Exception:  # pragma: no cover - fallback if sklearn unavailable
        cov, shrink = _shrink_to_diagonal(returns)
    if annualize:
        cov = cov * PERIODS
    return cov, shrink


def _shrink_to_diagonal(returns: pd.DataFrame, intensity: float = 0.3
                        ) -> tuple[pd.DataFrame, float]:
    """Simple fallback: blend sample cov with its diagonal."""
    s = returns.cov()
    target = pd.DataFrame(np.diag(np.diag(s.values)),
                          index=s.index, columns=s.columns)
    cov = (1 - intensity) * s + intensity * target
    return cov, intensity


def condition_number(cov: pd.DataFrame) -> float:
    """Ratio of largest to smallest eigenvalue — high = unstable/near-singular."""
    eig = np.linalg.eigvalsh(cov.values)
    eig = eig[eig > 0]
    return float(eig.max() / eig.min()) if len(eig) else np.inf
