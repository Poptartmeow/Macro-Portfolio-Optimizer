"""
Global Macro Portfolio Optimizer
=================================
Reads clean returns from the data pipeline output, then runs
mean-variance optimization to find the efficient frontier portfolio
at a target volatility level.

Run the data pipeline first:
    python -m macro_portfolio.pipelines.data_pipeline   ← produces data/returns_aligned.csv

Then run this:
    python -m macro_portfolio.optimizer.optimizer

Asset Universe (from portfolio allocation doc):
  SPY  — US Large Cap (S&P 500)
  VXF  — US Mid + Small Cap
  EWC  — Canadian Equities
  EFA  — Developed Intl Equities (ex-US)
  VWO  — Emerging Market Equities
  AGG  — US Aggregate Bonds
  INTL_BOND — Intl Bonds ex-US (spliced: PFORX pre-2013 → BNDX from 2013)
  EMB  — Emerging Market Bonds
  DBC  — Broad Commodities

Expected Returns Interface:
  By default, historical mean returns are used as a placeholder.
  To plug in macro model outputs, call:
      optimizer.set_expected_returns(your_dict)
  where your_dict maps ticker → annualized expected return (decimal).
  Example: {"SPY": 0.08, "VXF": 0.09, ...}
"""

import os
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import Optional

from macro_portfolio.paths import DATA_DIR


# ─────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────

# Asset universe labels (for reporting only — actual assets are read from
# the CSV columns produced by data_pipeline.py). The international bond series
# arrives already spliced as the column "INTL_BOND".
ASSET_LABELS = {
    "SPY":       "US Large Cap (S&P 500)",
    "VXF":       "US Mid + Small Cap",
    "EWC":       "Canadian Equities",
    "EFA":       "Intl Developed Equities (ex-US)",
    "VWO":       "Emerging Market Equities",
    "AGG":       "US Aggregate Bonds",
    "INTL_BOND": "Intl Bonds ex-US (spliced PFORX→BNDX)",
    "EMB":       "Emerging Market Bonds",
    "DBC":       "Broad Commodities",
}

# ── Optimizer settings ──
TARGET_VOL      = 0.10     # 10% annualized volatility (Greg's spec)
TRADING_PERIODS = 12       # Months per year (for annualizing monthly data)

# ── Diversification box constraints (TUNABLE — confirm values with Greg) ──
# Each asset's weight is bounded to [MIN_WEIGHT, MAX_WEIGHT].
# MIN_WEIGHT guarantees every asset participates (no corner solutions).
# MAX_WEIGHT prevents any single asset from dominating the portfolio.
# Feasibility requires: MIN_WEIGHT * n_assets <= 1 <= MAX_WEIGHT * n_assets.
MIN_WEIGHT = 0.03          # 3% floor per asset
MAX_WEIGHT = 0.30          # 30% cap per asset


# ─────────────────────────────────────────────
# 2. DATA LAYER — reads from data_pipeline.py output
# ─────────────────────────────────────────────

RETURNS_PATH = str(DATA_DIR / "returns_aligned.csv")   # produced by data_pipeline.py

def load_returns(path: str = RETURNS_PATH) -> pd.DataFrame:
    """
    Load the aligned monthly returns CSV produced by data_pipeline.py.
    Expects:
      - First column = date index
      - Remaining columns = asset returns (decimal, e.g. 0.012 = 1.2%)
      - No NaNs (pipeline guarantees aligned window)
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"\n  ✗ Returns file not found: {path}\n"
            f"  Run the data pipeline first:\n"
            f"      python -m macro_portfolio.pipelines.data_pipeline\n"
        )

    returns = pd.read_csv(path, index_col=0, parse_dates=True)

    if returns.isnull().any().any():
        n_missing = returns.isnull().sum().sum()
        print(f"  WARNING: {n_missing} missing values found — dropping affected rows.")
        returns = returns.dropna()

    print(f"  Loaded: {len(returns)} months × {len(returns.columns)} assets")
    print(f"  Date range: {returns.index[0].date()} → {returns.index[-1].date()}")
    print(f"  Assets: {', '.join(returns.columns.tolist())}")
    return returns


# ─────────────────────────────────────────────
# 3. EXPECTED RETURNS INTERFACE
# ─────────────────────────────────────────────

class ExpectedReturns:
    """
    Manages expected returns for the optimizer.

    Default mode: historical mean (placeholder).
    Production mode: call set_macro_model_returns() with your team's output.
    """

    def __init__(self, returns: pd.DataFrame):
        self._historical = returns.mean() * TRADING_PERIODS  # annualize
        self._custom: Optional[pd.Series] = None
        self.source = "historical_mean"

    def set_macro_model_returns(self, forecasts: dict):
        """
        Plug in expected returns from your macro regression model.

        Args:
            forecasts: dict mapping asset name → annualized expected return.
                       Asset names must match column names in the returns DataFrame.
                       Example: {"SPY": 0.08, "VXF": 0.09, "INTL_BOND": 0.04, ...}
        """
        self._custom = pd.Series(forecasts)
        self.source  = "macro_model"
        print(f"  Expected returns updated from macro model ({len(forecasts)} assets).")

    def get(self, assets: list[str]) -> pd.Series:
        """Return expected returns aligned to the given asset list."""
        if self._custom is not None:
            mu = self._custom.reindex(assets)
            missing = mu[mu.isna()].index.tolist()
            if missing:
                print(f"  WARNING: No macro forecast for {missing}. Falling back to historical for these.")
                mu[missing] = self._historical.reindex(missing)
            return mu
        return self._historical.reindex(assets)


# ─────────────────────────────────────────────
# 4. COVARIANCE ESTIMATION
# ─────────────────────────────────────────────

def compute_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """
    Sample covariance matrix, annualized.
    Greg's spec: use the sample covariance (no shrinkage for now).
    Shape: (n_assets x n_assets)
    """
    cov = returns.cov() * TRADING_PERIODS
    return cov


# ─────────────────────────────────────────────
# 5. OPTIMIZER
# ─────────────────────────────────────────────

def portfolio_vol(weights: np.ndarray, cov: np.ndarray) -> float:
    return np.sqrt(weights @ cov @ weights)


def portfolio_return(weights: np.ndarray, mu: np.ndarray) -> float:
    return weights @ mu


def _solve_vol_extreme(cov_arr, bounds, n, minimize_vol=True):
    """
    Find the min or max achievable portfolio volatility under the given
    box bounds + fully-invested constraint. Used for the feasibility check.
    """
    sign = 1.0 if minimize_vol else -1.0
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    result = minimize(
        lambda w: sign * portfolio_vol(w, cov_arr),
        np.ones(n) / n,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 1000},
    )
    return portfolio_vol(result.x, cov_arr) if result.success else None


def check_feasibility(cov_arr, bounds, n, target_vol):
    """
    Confirm the target volatility is achievable given the box constraints.
    Returns (is_feasible: bool, message: str, vol_range: tuple).
    """
    # Box-constraint sanity: do the bounds even permit weights summing to 1?
    lo_sum = sum(b[0] for b in bounds)
    hi_sum = sum(b[1] for b in bounds)
    if lo_sum > 1.0 + 1e-9:
        return False, (f"Infeasible bounds: floors sum to {lo_sum:.0%} > 100%. "
                       f"Lower MIN_WEIGHT (currently {MIN_WEIGHT:.0%})."), (None, None)
    if hi_sum < 1.0 - 1e-9:
        return False, (f"Infeasible bounds: caps sum to {hi_sum:.0%} < 100%. "
                       f"Raise MAX_WEIGHT (currently {MAX_WEIGHT:.0%})."), (None, None)

    # Achievable volatility window under the bounds
    min_v = _solve_vol_extreme(cov_arr, bounds, n, minimize_vol=True)
    max_v = _solve_vol_extreme(cov_arr, bounds, n, minimize_vol=False)

    if min_v is None or max_v is None:
        return True, "Could not bound the volatility range — proceeding with caution.", (min_v, max_v)

    if target_vol < min_v - 1e-4:
        return False, (f"Target vol {target_vol:.1%} is BELOW the minimum achievable "
                       f"({min_v:.1%}) given the box constraints. The bonds aren't low-vol "
                       f"enough — or floors on risky assets force vol up. "
                       f"Raise target, or lower MIN_WEIGHT on equities."), (min_v, max_v)
    if target_vol > max_v + 1e-4:
        return False, (f"Target vol {target_vol:.1%} is ABOVE the maximum achievable "
                       f"({max_v:.1%}) given the box constraints. The cap prevents enough "
                       f"concentration in high-vol assets. Lower target, or raise MAX_WEIGHT."), (min_v, max_v)

    return True, f"Target {target_vol:.1%} is within achievable range [{min_v:.1%}, {max_v:.1%}].", (min_v, max_v)


def optimize(
    mu: pd.Series,
    cov: pd.DataFrame,
    target_vol: float = TARGET_VOL,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
) -> dict:
    """
    Mean-variance optimization:
      Maximize expected return subject to:
        - Portfolio volatility == target_vol
        - Weights sum to 1 (fully invested)
        - min_weight <= each weight <= max_weight (box / diversification)

    Runs a feasibility check first and FAILS LOUDLY if the target volatility
    is unachievable or the optimizer does not converge — rather than silently
    returning a wrong (non-optimal or off-target) portfolio.

    Returns a dict with weights, realized portfolio stats, and status.
    """
    assets  = mu.index.tolist()
    n       = len(assets)
    mu_arr  = mu.values
    cov_arr = cov.loc[assets, assets].values

    # Box bounds: every asset in [min_weight, max_weight]
    bounds = [(min_weight, max_weight)] * n

    # ── Feasibility check (Fix 3) ──
    feasible, msg, (min_v, max_v) = check_feasibility(cov_arr, bounds, n, target_vol)
    print(f"  Feasibility: {msg}")
    if not feasible:
        raise ValueError(
            f"\n  ✗ Optimization is infeasible as configured:\n    {msg}\n"
            f"  Adjust TARGET_VOL / MIN_WEIGHT / MAX_WEIGHT at the top of the file.\n"
        )

    # Initial guess: equal weight (always inside the box if bounds are feasible)
    w0 = np.clip(np.ones(n) / n, min_weight, max_weight)
    w0 = w0 / w0.sum()

    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},                      # fully invested
        {"type": "eq", "fun": lambda w: portfolio_vol(w, cov_arr) - target_vol},  # target vol
    ]

    result = minimize(
        lambda w: -portfolio_return(w, mu_arr),
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 1000},
    )

    w_opt = result.x

    # Verify the solution actually satisfies the constraints (Fix 3) —
    # SLSQP can report failure or drift; we check rather than trust blindly.
    realized_vol    = portfolio_vol(w_opt, cov_arr)
    realized_return = portfolio_return(w_opt, mu_arr)
    sum_ok          = abs(w_opt.sum() - 1.0) < 1e-4
    vol_ok          = abs(realized_vol - target_vol) < 1e-3
    box_ok          = (w_opt >= min_weight - 1e-4).all() and (w_opt <= max_weight + 1e-4).all()

    if not result.success or not (sum_ok and vol_ok and box_ok):
        violations = []
        if not result.success: violations.append(f"solver: {result.message}")
        if not sum_ok:  violations.append(f"weights sum to {w_opt.sum():.4f} (≠ 1)")
        if not vol_ok:  violations.append(f"realized vol {realized_vol:.2%} (≠ target {target_vol:.1%})")
        if not box_ok:  violations.append("weights breached box bounds")
        raise RuntimeError(
            "\n  ✗ Optimizer did not produce a valid solution:\n    "
            + "\n    ".join(violations)
            + "\n  Do NOT use these weights. Check the covariance matrix and target vol.\n"
        )

    sharpe = realized_return / realized_vol if realized_vol > 0 else np.nan
    weights_series = pd.Series(w_opt, index=assets).sort_values(ascending=False)

    return {
        "weights":           weights_series,
        "expected_return":   realized_return,
        "volatility":        realized_vol,
        "sharpe_ratio":      sharpe,
        "converged":         result.success,
        "optimizer_message": result.message,
        "achievable_vol_range": (min_v, max_v),
    }


# ─────────────────────────────────────────────
# 6. EFFICIENT FRONTIER (OPTIONAL)
# ─────────────────────────────────────────────

def efficient_frontier(
    mu: pd.Series,
    cov: pd.DataFrame,
    n_points: int = 30,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
) -> pd.DataFrame:
    """
    Trace the efficient frontier by sweeping target volatility levels,
    using the same box constraints as the main optimizer.
    Returns a DataFrame with (vol, return, sharpe) for each feasible point.
    """
    assets  = mu.index.tolist()
    n       = len(assets)
    mu_arr  = mu.values
    cov_arr = cov.loc[assets, assets].values
    bounds  = [(min_weight, max_weight)] * n

    # Sweep only the achievable volatility window (under the box bounds)
    min_v = _solve_vol_extreme(cov_arr, bounds, n, minimize_vol=True)  or 0.02
    max_v = _solve_vol_extreme(cov_arr, bounds, n, minimize_vol=False) or 0.30
    vols  = np.linspace(min_v, max_v, n_points)

    records = []
    for tv in vols:
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
            {"type": "eq", "fun": lambda w, tv=tv: portfolio_vol(w, cov_arr) - tv},
        ]
        result = minimize(
            lambda w: -portfolio_return(w, mu_arr),
            np.clip(np.ones(n) / n, min_weight, max_weight),
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 500},
        )
        if result.success:
            w = result.x
            records.append({
                "volatility": portfolio_vol(w, cov_arr),
                "return":     portfolio_return(w, mu_arr),
                "sharpe":     portfolio_return(w, mu_arr) / portfolio_vol(w, cov_arr),
            })

    return pd.DataFrame(records)


# ─────────────────────────────────────────────
# 7. REPORTING
# ─────────────────────────────────────────────

def print_results(result: dict, er_source: str):
    """Print a formatted summary of optimizer output."""
    sep = "─" * 55

    print(f"\n{sep}")
    print("  PORTFOLIO OPTIMIZER — RESULTS")
    print(sep)
    print(f"  Expected returns source : {er_source}")
    print(f"  Target volatility       : {TARGET_VOL:.1%}")
    print(f"  Weight box per asset    : {MIN_WEIGHT:.0%} – {MAX_WEIGHT:.0%}")
    rng = result.get("achievable_vol_range")
    if rng and rng[0] is not None:
        print(f"  Achievable vol range    : {rng[0]:.1%} – {rng[1]:.1%}")
    print(f"  Converged               : {result['converged']}")
    print(sep)
    print(f"  Realized Portfolio Stats")
    print(f"    Expected Return : {result['expected_return']:.2%}")
    print(f"    Volatility      : {result['volatility']:.2%}")
    print(f"    Sharpe Ratio    : {result['sharpe_ratio']:.3f}")
    print(sep)
    print("  Optimal Weights")
    for asset, w in result["weights"].items():
        bar = "█" * int(w * 40)
        print(f"    {asset:<12} {w:>6.2%}  {bar}")
    print(sep)


# ─────────────────────────────────────────────
# 8. MAIN
# ─────────────────────────────────────────────

class PortfolioOptimizer:
    """
    Main entry point. Encapsulates the full pipeline.

    Usage:
        opt = PortfolioOptimizer()
        opt.run()

        # Later, once macro model is ready:
        opt.set_expected_returns({"SPY": 0.08, "VXF": 0.09, ...})
        opt.run()
    """

    def __init__(self):
        self.returns : Optional[pd.DataFrame] = None
        self.cov     : Optional[pd.DataFrame] = None
        self.er      : Optional[ExpectedReturns] = None
        self.result  : Optional[dict] = None

    def load_data(self, path: str = RETURNS_PATH):
        print("\n[1/4] Loading returns from data pipeline...")
        self.returns = load_returns(path)
        print("\n[2/4] Computing covariance matrix...")
        self.cov     = compute_covariance(self.returns)
        self.er      = ExpectedReturns(self.returns)
        print(f"      Covariance matrix: {self.cov.shape[0]}×{self.cov.shape[1]}")

    def set_expected_returns(self, forecasts: dict):
        """Swap in macro model forecasts. Call after load_data()."""
        if self.er is None:
            raise RuntimeError("Call load_data() before set_expected_returns().")
        self.er.set_macro_model_returns(forecasts)

    def run(self, target_vol: float = TARGET_VOL):
        if self.returns is None:
            self.load_data()

        assets = self.returns.columns.tolist()
        mu     = self.er.get(assets)
        cov    = self.cov.loc[assets, assets]

        print(f"\n[3/4] Running optimizer (target vol = {target_vol:.1%})...")
        self.result = optimize(mu, cov, target_vol)

        print("\n[4/4] Results:")
        print_results(self.result, self.er.source)
        return self.result

    def get_frontier(self, n_points: int = 30) -> pd.DataFrame:
        """Compute and return the full efficient frontier."""
        if self.returns is None:
            self.load_data()
        assets = self.returns.columns.tolist()
        mu     = self.er.get(assets)
        cov    = self.cov.loc[assets, assets]
        print("\nComputing efficient frontier...")
        frontier = efficient_frontier(mu, cov, n_points)
        print(f"  {len(frontier)} feasible points found.")
        return frontier

    def summary_stats(self) -> pd.DataFrame:
        """Return a table of per-asset annualized stats."""
        if self.returns is None:
            self.load_data()
        stats = pd.DataFrame({
            "Ann. Return":     self.returns.mean() * TRADING_PERIODS,
            "Ann. Volatility": self.returns.std()  * np.sqrt(TRADING_PERIODS),
            "Sharpe":         (self.returns.mean() * TRADING_PERIODS) /
                              (self.returns.std()  * np.sqrt(TRADING_PERIODS)),
            "Start Date":      self.returns.apply(lambda c: c.first_valid_index()),
        })
        return stats.sort_values("Ann. Return", ascending=False)


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────
if __name__ == "__main__":
    opt = PortfolioOptimizer()

    # Step 1: load data and run with historical mean returns (placeholder)
    result = opt.run()

    # Step 2: print per-asset stats
    print("\nPer-Asset Summary Statistics:")
    print(opt.summary_stats().to_string())

    # ── MACRO MODEL SWAP-IN (example — uncomment when ready) ────────────
    # opt.set_expected_returns({
    #     "SPY":       0.085,
    #     "VXF":       0.090,
    #     "EWC":       0.075,
    #     "EFA":       0.070,
    #     "VWO":       0.095,
    #     "AGG":       0.040,
    #     "INTL_BOND": 0.035,
    #     "EMB":       0.055,
    #     "DBC":       0.050,
    # })
    # opt.run()
    # ────────────────────────────────────────────────────────────────────