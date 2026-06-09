"""
Efficient Frontier Comparison — Constrained vs Unconstrained
=============================================================
Visualizes the diversification tradeoff of the box constraints
(per-asset floor + cap) against an unconstrained long-only frontier.

The gap between the two curves at the 10% target volatility is the
"cost of diversification" — the Sharpe/return given up in exchange for
not letting the portfolio concentrate into 2–3 assets.

Run the data pipeline + have returns_aligned.csv first, then:
    python -m macro_portfolio.optimizer.plot_frontier

Output:
    outputs/efficient_frontier.png

Note: This uses the SAME historical-mean placeholder returns as the
optimizer. Once the macro model is wired in, the frontier shape will
shift — re-run this to regenerate the chart for the final report.
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless / no display needed
import matplotlib.pyplot as plt

from macro_portfolio.optimizer import optimizer as O
from macro_portfolio.paths import OUTPUTS_DIR


# ─────────────────────────────────────────────
# Styling
# ─────────────────────────────────────────────

OUTPUT_PATH = str(OUTPUTS_DIR / "efficient_frontier.png")

COLOR_CONSTRAINED   = "#2563eb"   # blue  — the box-constrained frontier (what we use)
COLOR_UNCONSTRAINED = "#9ca3af"   # gray  — the theoretical unconstrained frontier
COLOR_TARGET        = "#dc2626"   # red   — the 10% target line / points
COLOR_ASSETS        = "#94a3b8"   # slate — individual asset scatter


def build_frontiers(opt: O.PortfolioOptimizer, n_points: int = 40):
    """
    Compute both frontiers and both 10%-vol optimal points.
    Returns a dict of everything the plot needs.
    """
    assets = opt.returns.columns.tolist()
    mu     = opt.er.get(assets)
    cov    = opt.cov.loc[assets, assets]

    print("  Computing CONSTRAINED frontier (box: "
          f"{O.MIN_WEIGHT:.0%}–{O.MAX_WEIGHT:.0%})...")
    front_box = O.efficient_frontier(
        mu, cov, n_points=n_points,
        min_weight=O.MIN_WEIGHT, max_weight=O.MAX_WEIGHT,
    )

    print("  Computing UNCONSTRAINED frontier (long-only, 0%–100%)...")
    front_free = O.efficient_frontier(
        mu, cov, n_points=n_points,
        min_weight=0.0, max_weight=1.0,
    )

    # The two 10%-vol optimal portfolios
    print("  Solving 10% optimal — constrained...")
    pt_box = O.optimize(mu, cov, target_vol=O.TARGET_VOL,
                        min_weight=O.MIN_WEIGHT, max_weight=O.MAX_WEIGHT)
    print("  Solving 10% optimal — unconstrained...")
    pt_free = O.optimize(mu, cov, target_vol=O.TARGET_VOL,
                         min_weight=0.0, max_weight=1.0)

    # Per-asset points (annualized vol vs return) for context
    asset_vol = opt.returns.std() * np.sqrt(O.TRADING_PERIODS)
    asset_ret = mu  # already annualized

    return {
        "front_box":  front_box,
        "front_free": front_free,
        "pt_box":     pt_box,
        "pt_free":    pt_free,
        "asset_vol":  asset_vol,
        "asset_ret":  asset_ret,
        "assets":     assets,
    }


def plot(data: dict, out_path: str = OUTPUT_PATH):
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=150)

    fb, ff = data["front_box"], data["front_free"]
    pb, pf = data["pt_box"], data["pt_free"]

    # ── Frontier curves ──
    if not ff.empty:
        ax.plot(ff["volatility"] * 100, ff["return"] * 100,
                color=COLOR_UNCONSTRAINED, lw=2.2, ls="--",
                label="Unconstrained frontier (long-only)", zorder=2)
    if not fb.empty:
        ax.plot(fb["volatility"] * 100, fb["return"] * 100,
                color=COLOR_CONSTRAINED, lw=2.6,
                label=f"Constrained frontier ({O.MIN_WEIGHT:.0%}–{O.MAX_WEIGHT:.0%} box)",
                zorder=3)

    # ── Individual assets (context) ──
    ax.scatter(data["asset_vol"] * 100, data["asset_ret"] * 100,
               color=COLOR_ASSETS, s=35, zorder=2, alpha=0.8)
    for name in data["assets"]:
        ax.annotate(name,
                    (data["asset_vol"][name] * 100, data["asset_ret"][name] * 100),
                    textcoords="offset points", xytext=(5, 4),
                    fontsize=7.5, color="#64748b")

    # ── The two 10%-vol optimal portfolios ──
    ax.scatter([pf["volatility"] * 100], [pf["expected_return"] * 100],
               color=COLOR_UNCONSTRAINED, edgecolor="black", s=130,
               marker="o", zorder=5)
    ax.scatter([pb["volatility"] * 100], [pb["expected_return"] * 100],
               color=COLOR_CONSTRAINED, edgecolor="black", s=140,
               marker="D", zorder=6,
               label=f"Our portfolio @ {O.TARGET_VOL:.0%} vol")

    # ── Target vol vertical line ──
    ax.axvline(O.TARGET_VOL * 100, color=COLOR_TARGET, ls=":", lw=1.5,
               alpha=0.7, zorder=1)
    ax.text(O.TARGET_VOL * 100 + 0.15, ax.get_ylim()[0] + 0.3,
            f"{O.TARGET_VOL:.0%} target", color=COLOR_TARGET,
            fontsize=8.5, rotation=90, va="bottom")

    # ── Annotate the diversification cost (vertical gap at 10%) ──
    gap = (pf["expected_return"] - pb["expected_return"]) * 100
    if gap > 0.01:
        x = O.TARGET_VOL * 100
        ax.annotate(
            "", xy=(x, pf["expected_return"] * 100),
            xytext=(x, pb["expected_return"] * 100),
            arrowprops=dict(arrowstyle="<->", color=COLOR_TARGET, lw=1.4),
            zorder=7,
        )
        ax.text(x + 0.35,
                (pf["expected_return"] + pb["expected_return"]) / 2 * 100,
                f"diversification cost\n≈ {gap:.2f}% return\n"
                f"(Sharpe {pf['sharpe_ratio']:.2f} → {pb['sharpe_ratio']:.2f})",
                fontsize=8, color=COLOR_TARGET, va="center")

    # ── Labels / cosmetics ──
    ax.set_xlabel("Annualized Volatility (%)", fontsize=11)
    ax.set_ylabel("Annualized Expected Return (%)", fontsize=11)
    ax.set_title("Efficient Frontier — Diversification Tradeoff of Box Constraints",
                 fontsize=13, fontweight="bold", pad=12)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.95)
    ax.grid(True, alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)

    # Caveat footnote — keeps the "placeholder returns" honest for Greg
    fig.text(0.012, 0.012,
             "Expected returns = historical-mean placeholder. Frontier will "
             "shift once the macro model is wired in.",
             fontsize=7.5, color="#94a3b8", style="italic")

    fig.tight_layout(rect=[0, 0.03, 1, 1])
    fig.savefig(out_path, bbox_inches="tight")
    print(f"\n  Saved chart → {out_path}")

    # Print the headline numbers for the talk track with Greg
    print("\n  ── Tradeoff summary (for the Greg conversation) ──")
    print(f"    Unconstrained @ 10% vol : {pf['expected_return']:.2%} return, "
          f"Sharpe {pf['sharpe_ratio']:.3f}")
    print(f"    Constrained   @ 10% vol : {pb['expected_return']:.2%} return, "
          f"Sharpe {pb['sharpe_ratio']:.3f}")
    print(f"    Cost of diversification : {gap:.2f}% return give-up")
    return out_path


def main():
    print("\n[1/3] Loading data + computing covariance...")
    opt = O.PortfolioOptimizer()
    opt.load_data()

    print("\n[2/3] Building frontiers...")
    data = build_frontiers(opt)

    print("\n[3/3] Plotting...")
    plot(data)


if __name__ == "__main__":
    main()