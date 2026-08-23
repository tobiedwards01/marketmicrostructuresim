"""Phase 5 deliverable: compares the trained Q-learning market maker's learned
quoting behaviour against the Avellaneda-Stoikov closed-form benchmark, across
the same grid of (inventory, time-remaining) values.

Run with:
    uv run python examples/compare_rl_vs_avellaneda_stoikov.py

Requires models/q_learning_market_maker.json to already exist -- run
train_rl_market_maker.py first if it doesn't.
"""

from pathlib import Path

import matplotlib.pyplot as plt

from mm_sim.agents.avellaneda_stoikov import AvellanedaStoikovMarketMaker
from mm_sim.agents.rl_market_maker import QLearningMarketMaker
from mm_sim.analysis import estimate_volatility
from mm_sim.event_loop import EventLoop
from run_simulation import END_TIME, REFERENCE_PRICE, build_agents

MODEL_PATH = Path(__file__).parent.parent / "models" / "q_learning_market_maker.json"
OUTPUT_DIR = Path(__file__).parent / "output"

MAX_INVENTORY = 50
GAMMA = 0.0002
K = 1.5


def half_spread_and_skew(mid: float, bid: float, ask: float) -> tuple[float, float]:
    """skew > 0 means quotes are centered BELOW mid (agent is keener to sell
    than buy) -- matches both agents' internal sign convention directly, so
    the two are comparable without any adjustment.
    """
    return (ask - bid) / 2, mid - (bid + ask) / 2


def estimate_sigma() -> float:
    """Realized volatility from a baseline run (same setup as run_simulation.py,
    with the naive market maker), rather than a hand-picked guess -- Phase 5
    reusing a Phase 4 tool on a fresh question.
    """
    agents, _, _ = build_agents()
    loop = EventLoop(agents)
    loop.run_until(END_TIME)
    return estimate_volatility(loop.book_snapshots)


def main() -> None:
    sigma = estimate_sigma()
    print(f"Estimated sigma from a baseline run: {sigma:.4f} (price units per sqrt(time))")

    rl_agent = QLearningMarketMaker(
        agent_id=400, reference_price=REFERENCE_PRICE, horizon=END_TIME,
        quote_size=10, max_inventory=MAX_INVENTORY, requote_interval=0.5, epsilon=0.0,
    )
    rl_agent.load(MODEL_PATH)

    as_agent = AvellanedaStoikovMarketMaker(
        agent_id=401, reference_price=REFERENCE_PRICE, horizon=END_TIME,
        gamma=GAMMA, sigma=sigma, k=K, quote_size=10, max_inventory=MAX_INVENTORY, requote_interval=0.5,
    )

    mid = float(REFERENCE_PRICE)

    fig, (ax_spread, ax_skew) = plt.subplots(1, 2, figsize=(12, 4.5))

    # Panel 1: half-spread vs. time remaining, at zero inventory
    sim_times = list(range(0, int(END_TIME), 5))
    rl_spreads, as_spreads = [], []
    for t in sim_times:
        rl_bid, rl_ask = rl_agent.greedy_quotes(mid, inventory=0, sim_time=t)
        as_bid, as_ask = as_agent.quotes(mid, inventory=0, time_remaining=END_TIME - t)
        rl_spreads.append(half_spread_and_skew(mid, rl_bid, rl_ask)[0])
        as_spreads.append(half_spread_and_skew(mid, as_bid, as_ask)[0])

    ax_spread.plot(sim_times, rl_spreads, marker="o", markersize=3, label="Q-learning (learned)")
    ax_spread.plot(sim_times, as_spreads, linestyle="--", label="Avellaneda-Stoikov (closed form)")
    ax_spread.set_xlabel("simulated time")
    ax_spread.set_ylabel("half-spread (ticks)")
    ax_spread.set_title("Half-spread vs. time (inventory = 0)")
    ax_spread.legend()

    # Panel 2: skew vs. inventory, at mid-horizon
    mid_time = END_TIME / 2
    inventories = list(range(-MAX_INVENTORY, MAX_INVENTORY + 1, 5))
    rl_skews, as_skews = [], []
    for inv in inventories:
        rl_bid, rl_ask = rl_agent.greedy_quotes(mid, inventory=inv, sim_time=mid_time)
        as_bid, as_ask = as_agent.quotes(mid, inventory=inv, time_remaining=END_TIME - mid_time)
        rl_skews.append(half_spread_and_skew(mid, rl_bid, rl_ask)[1])
        as_skews.append(half_spread_and_skew(mid, as_bid, as_ask)[1])

    ax_skew.plot(inventories, rl_skews, marker="o", markersize=3, label="Q-learning (learned)")
    ax_skew.plot(inventories, as_skews, linestyle="--", label="Avellaneda-Stoikov (closed form)")
    ax_skew.axhline(0, color="black", linewidth=0.5)
    ax_skew.axvline(0, color="black", linewidth=0.5)
    ax_skew.set_xlabel("inventory")
    ax_skew.set_ylabel("skew (ticks, + = quotes shifted down)")
    ax_skew.set_title(f"Quote skew vs. inventory (t={mid_time:.0f}, mid-horizon)")
    ax_skew.legend()

    fig.suptitle("Q-learning vs. Avellaneda-Stoikov: learned vs. closed-form quoting behaviour")
    fig.tight_layout()
    OUTPUT_DIR.mkdir(exist_ok=True)
    fig.savefig(OUTPUT_DIR / "phase5_rl_vs_avellaneda_stoikov.png", dpi=150)
    print(f"Saved comparison to {OUTPUT_DIR / 'phase5_rl_vs_avellaneda_stoikov.png'}")

    print("\nHalf-spread vs time (inventory=0):")
    for t, rl_s, as_s in zip(sim_times[::4], rl_spreads[::4], as_spreads[::4]):
        print(f"  t={t:>4}  RL={rl_s:6.1f}  AS={as_s:6.1f}")

    print("\nSkew vs inventory (t=mid-horizon):")
    for inv, rl_k, as_k in zip(inventories[::2], rl_skews[::2], as_skews[::2]):
        print(f"  inv={inv:>4}  RL={rl_k:6.1f}  AS={as_k:6.1f}")


if __name__ == "__main__":
    main()
