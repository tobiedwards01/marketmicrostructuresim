"""Phase 4 deliverable: testing the simulator's "stylized facts" against known
microstructure theory. Each experiment below is tied to a specific theoretical
claim -- see ANALYSIS.md for the full writeup and interpretation.

Run with:
    uv run python examples/phase4_analysis.py

Produces three plots in examples/output/ and prints the numbers ANALYSIS.md
references.
"""

from pathlib import Path

import matplotlib.pyplot as plt

from mm_sim.analysis import (
    autocorrelation,
    bucket_price_impact_by_size,
    mid_price_returns,
    pearson_correlation,
)
from mm_sim.event_loop import EventLoop
from run_simulation import END_TIME, build_agents

OUTPUT_DIR = Path(__file__).parent / "output"

SEED_REPLICATES = [0, 10_000, 20_000]  # same seed sets re-tested at every informed-rate level
INFORMED_RATES = [0.05, 0.15, 0.3, 0.6, 1.0, 2.0]


def run(informed_arrival_rate: float, seed_offset: int) -> EventLoop:
    agents, _, _ = build_agents(informed_arrival_rate=informed_arrival_rate, seed_offset=seed_offset)
    loop = EventLoop(agents)
    loop.run_until(END_TIME)
    return loop


def mean_spread(loop: EventLoop) -> float:
    spreads = [s.spread for s in loop.book_snapshots if s.spread is not None]
    return sum(spreads) / len(spreads) / 100 if spreads else float("nan")


def experiment_spread_vs_informed_intensity() -> float:
    """Glosten-Milgrom: market makers widen spreads to protect against adverse
    selection from informed traders. As informed-trading intensity rises, the
    equilibrium spread should rise too.
    """
    print("=== Spread vs. informed-trading intensity (Glosten-Milgrom) ===")
    avg_spreads = []
    for rate in INFORMED_RATES:
        replicate_spreads = [mean_spread(run(rate, seed)) for seed in SEED_REPLICATES]
        avg = sum(replicate_spreads) / len(replicate_spreads)
        avg_spreads.append(avg)
        print(f"  informed arrival_rate={rate:<5} mean spread=${avg:.4f}  (n={len(replicate_spreads)} replicates)")

    corr = pearson_correlation(INFORMED_RATES, avg_spreads)
    print(f"  Pearson correlation(rate, spread) = {corr:.3f}")

    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.plot(INFORMED_RATES, avg_spreads, marker="o")
    ax.set_xlabel("informed trader arrival rate")
    ax.set_ylabel("mean spread ($)")
    ax.set_title(f"Spread vs. informed-trading intensity (r={corr:.2f})")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "phase4_spread_vs_informed_intensity.png", dpi=150)
    plt.close(fig)

    return corr


def experiment_price_impact_concavity() -> float:
    """Kyle (1985): linear price impact is the baseline theoretical prediction.
    A common empirical/extended-theory finding instead is CONCAVE impact --
    impact grows sub-linearly with trade size. Checking which one holds here.
    """
    print("\n=== Price impact vs. trade size (Kyle's linear baseline) ===")
    loop = run(informed_arrival_rate=0.3, seed_offset=0)
    buckets = bucket_price_impact_by_size(loop.order_impacts, n_buckets=8)

    sizes = [b[0] for b in buckets]
    impacts = [b[1] for b in buckets]
    for size, impact, count in buckets:
        print(f"  size~{size:5.1f}  avg |impact|=${impact / 100:.4f}  n={count}")

    # Concavity check: if impact grows sub-linearly with size, impact-per-unit
    # should DECREASE as size grows. Constant or increasing means linear/convex.
    impact_per_unit = [impact / size for size, impact in zip(sizes, impacts)]
    corr = pearson_correlation(sizes, impact_per_unit)
    verdict = "concave-consistent" if corr < 0 else "not concave-consistent"
    print(f"  Pearson correlation(size, impact/size) = {corr:.3f} ({verdict})")

    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.plot(sizes, [i / 100 for i in impacts], marker="o", label="observed")
    if sizes:
        linear_ref = [impacts[0] / 100 / sizes[0] * s for s in sizes]
        ax.plot(sizes, linear_ref, linestyle="--", color="gray", label="linear reference (Kyle)")
    ax.set_xlabel("filled quantity")
    ax.set_ylabel("avg |price impact| ($)")
    ax.set_title("Price impact vs. trade size")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "phase4_price_impact_concavity.png", dpi=150)
    plt.close(fig)

    return corr


def experiment_volatility_clustering() -> tuple[list[float], list[float]]:
    """Cont (2001) stylized facts of asset returns: large price changes tend to
    be followed by large price changes (of either sign) -- positive
    autocorrelation in |returns| despite near-zero autocorrelation in raw,
    signed returns.
    """
    print("\n=== Volatility clustering (Cont 2001 stylized facts) ===")
    loop = run(informed_arrival_rate=0.3, seed_offset=0)
    returns = mid_price_returns(loop.book_snapshots)
    abs_returns = [abs(r) for r in returns]

    lags = list(range(1, 21))
    raw_autocorr = [autocorrelation(returns, lag) for lag in lags]
    abs_autocorr = [autocorrelation(abs_returns, lag) for lag in lags]

    print(f"  n returns = {len(returns)}")
    print(f"  raw returns autocorrelation, lag 1-5:  {[round(v, 3) for v in raw_autocorr[:5]]}")
    print(f"  |returns| autocorrelation, lag 1-5:    {[round(v, 3) for v in abs_autocorr[:5]]}")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    width = 0.4
    ax.bar([lag - width / 2 for lag in lags], raw_autocorr, width=width, label="raw returns")
    ax.bar([lag + width / 2 for lag in lags], abs_autocorr, width=width, label="|returns|")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("lag")
    ax.set_ylabel("autocorrelation")
    ax.set_title("Return autocorrelation: raw vs. absolute (volatility clustering)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "phase4_volatility_clustering.png", dpi=150)
    plt.close(fig)

    return raw_autocorr, abs_autocorr


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    experiment_spread_vs_informed_intensity()
    experiment_price_impact_concavity()
    experiment_volatility_clustering()
    print(f"\nPlots saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
