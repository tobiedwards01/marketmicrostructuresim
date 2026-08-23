"""Phase 6 deliverable: a flash-crash stress test. A sudden, large drop in the
informed trader's "true price" partway through the run -- simulating
unexpected bad news -- triggers a burst of aggressive informed selling as its
signal diverges from the market's still-stale quotes. Compares how the three
market maker types built across this project (naive fixed-spread,
Avellaneda-Stoikov, trained Q-learning) each hold up.

Run with:
    uv run python examples/phase6_stress_test.py

Requires models/q_learning_market_maker.json (run train_rl_market_maker.py
first if it doesn't exist).
"""

from pathlib import Path

import matplotlib.pyplot as plt

from mm_sim.agents.avellaneda_stoikov import AvellanedaStoikovMarketMaker
from mm_sim.agents.market_maker import NaiveMarketMaker
from mm_sim.agents.rl_market_maker import QLearningMarketMaker
from mm_sim.analysis import estimate_volatility
from mm_sim.event_loop import EventLoop
from run_simulation import END_TIME, REFERENCE_PRICE, build_agents

MODEL_PATH = Path(__file__).parent.parent / "models" / "q_learning_market_maker.json"
OUTPUT_DIR = Path(__file__).parent / "output"

SHOCK_TIME = 100.0
SHOCK_SIZE = 1_500  # $15 sudden drop in the informed trader's belief
CHECKPOINT_INTERVAL = 2.0


def build_scenario_agents(market_maker, seed_offset: int = 0):
    agents, informed_trader, naive_mm = build_agents(seed_offset=seed_offset)
    agents = [a for a in agents if a is not naive_mm]
    agents.append(market_maker)
    return agents, informed_trader


def run_stress_test(market_maker, seed_offset: int = 0) -> list[dict]:
    agents, informed_trader = build_scenario_agents(market_maker, seed_offset)
    loop = EventLoop(agents)

    checkpoints = []
    t = 0.0
    shocked = False
    while t < END_TIME:
        t = min(t + CHECKPOINT_INTERVAL, END_TIME)
        loop.run_until(t)
        if not shocked and t >= SHOCK_TIME:
            informed_trader.true_price = max(1, informed_trader.true_price - SHOCK_SIZE)
            shocked = True

        mid = loop.book.mid_price if loop.book.mid_price is not None else REFERENCE_PRICE
        checkpoints.append(
            {
                "time": t,
                "mid": mid / 100,
                "spread": (loop.book.spread / 100) if loop.book.spread is not None else None,
                "inventory": market_maker.inventory,
                "mtm": market_maker.mark_to_market(mid) / 100,
            }
        )
    return checkpoints


def build_naive_mm() -> NaiveMarketMaker:
    return NaiveMarketMaker(
        agent_id=300, reference_price=REFERENCE_PRICE, half_spread_ticks=10,
        quote_size=10, max_inventory=50, requote_interval=0.5,
    )


def build_as_mm(sigma: float) -> AvellanedaStoikovMarketMaker:
    return AvellanedaStoikovMarketMaker(
        agent_id=301, reference_price=REFERENCE_PRICE, horizon=END_TIME,
        gamma=0.0002, sigma=sigma, k=1.5, quote_size=10, max_inventory=50, requote_interval=0.5,
    )


def build_rl_mm() -> QLearningMarketMaker:
    agent = QLearningMarketMaker(
        agent_id=302, reference_price=REFERENCE_PRICE, horizon=END_TIME,
        quote_size=10, max_inventory=50, requote_interval=0.5, epsilon=0.0,
    )
    agent.load(MODEL_PATH)
    return agent


def plot_series(ax, results: dict[str, list[dict]], key: str, title: str, ylabel: str) -> None:
    for name, records in results.items():
        xs = [r["time"] for r in records if r[key] is not None]
        ys = [r[key] for r in records if r[key] is not None]
        ax.plot(xs, ys, label=name)
    ax.axvline(SHOCK_TIME, color="red", linestyle=":", linewidth=1)
    ax.set_title(title)
    ax.set_xlabel("simulated time")
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=8)


def main() -> None:
    baseline_agents, _, _ = build_agents()
    baseline_loop = EventLoop(baseline_agents)
    baseline_loop.run_until(END_TIME)
    sigma = estimate_volatility(baseline_loop.book_snapshots)

    scenarios = {
        "Naive": build_naive_mm(),
        "Avellaneda-Stoikov": build_as_mm(sigma),
        "Q-learning (trained)": build_rl_mm(),
    }
    results = {name: run_stress_test(mm) for name, mm in scenarios.items()}

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    plot_series(axes[0][0], results, "mid", "Mid price", "$")
    plot_series(axes[0][1], results, "spread", "Spread", "$")
    plot_series(axes[1][0], results, "inventory", "Market maker inventory", "units")
    plot_series(axes[1][1], results, "mtm", "Market maker mark-to-market P&L", "$")
    fig.suptitle(f"Phase 6 stress test: informed-selling shock at t={SHOCK_TIME:.0f} (-${SHOCK_SIZE / 100:.0f} belief drop)")
    fig.tight_layout()

    OUTPUT_DIR.mkdir(exist_ok=True)
    fig.savefig(OUTPUT_DIR / "phase6_stress_test.png", dpi=150)
    print(f"Saved to {OUTPUT_DIR / 'phase6_stress_test.png'}")

    print(f"\n{'Market maker':<22} {'inv @shock':>11} {'inv final':>10} {'P&L @shock':>12} {'P&L final':>12}")
    for name, records in results.items():
        at_shock = [r for r in records if r["time"] <= SHOCK_TIME][-1]
        final = records[-1]
        print(
            f"{name:<22} {at_shock['inventory']:>11} {final['inventory']:>10} "
            f"${at_shock['mtm']:>10.2f} ${final['mtm']:>10.2f}"
        )


if __name__ == "__main__":
    main()
