"""Phase 3 deliverable: a metrics dashboard for one simulated trading session.

Runs the same agent setup as run_simulation.py, then plots the four metrics
Phase 3 is about: spread over time, order book depth over time, price impact
vs. trade size, and P&L per agent -- saved as one PNG.

Run with:
    uv run python examples/plot_metrics.py
"""

from pathlib import Path

import matplotlib.pyplot as plt

from mm_sim.event_loop import EventLoop
from mm_sim.metrics import compute_pnl
from run_simulation import END_TIME, build_agents

OUTPUT_PATH = Path(__file__).parent / "output" / "metrics_dashboard.png"

AGENT_LABELS = {
    200: "Informed",
    300: "Market Maker",
}


def agent_label(agent_id: int) -> str:
    if agent_id in AGENT_LABELS:
        return AGENT_LABELS[agent_id]
    if 100 <= agent_id < 200:
        return f"Noise {agent_id - 99}"
    return str(agent_id)


def plot_spread(ax, snapshots) -> None:
    times = [s.timestamp for s in snapshots if s.spread is not None]
    spreads = [s.spread / 100 for s in snapshots if s.spread is not None]
    ax.plot(times, spreads, linewidth=0.8)
    ax.set_title("Bid-ask spread over time")
    ax.set_xlabel("simulated time")
    ax.set_ylabel("spread ($)")


def plot_depth(ax, snapshots) -> None:
    times = [s.timestamp for s in snapshots]
    bid_depth = [s.bid_depth for s in snapshots]
    ask_depth = [s.ask_depth for s in snapshots]
    ax.plot(times, bid_depth, label="bid depth", linewidth=0.8)
    ax.plot(times, ask_depth, label="ask depth", linewidth=0.8)
    ax.set_title("Order book depth over time")
    ax.set_xlabel("simulated time")
    ax.set_ylabel("resting quantity")
    ax.legend()


def plot_price_impact(ax, impacts) -> None:
    sizes = [i.filled_quantity for i in impacts if i.filled_quantity > 0 and i.price_impact is not None]
    moves = [abs(i.price_impact) / 100 for i in impacts if i.filled_quantity > 0 and i.price_impact is not None]
    ax.scatter(sizes, moves, s=10, alpha=0.4)
    ax.set_title("Price impact vs. trade size")
    ax.set_xlabel("filled quantity")
    ax.set_ylabel("|mid price move| ($)")


def plot_pnl(ax, trades, mark_price) -> None:
    pnl = compute_pnl(trades, mark_price)
    agent_ids = sorted(pnl.keys())
    labels = [agent_label(a) for a in agent_ids]
    totals = [pnl[a].total / 100 for a in agent_ids]
    colors = ["tab:green" if t >= 0 else "tab:red" for t in totals]
    ax.bar(labels, totals, color=colors)
    ax.set_title("P&L per agent (mark-to-market)")
    ax.set_ylabel("P&L ($)")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.tick_params(axis="x", rotation=45)


def main() -> None:
    agents, _informed_trader, _market_maker = build_agents()
    loop = EventLoop(agents)
    loop.run_until(END_TIME)

    mark_price = loop.book.mid_price
    if mark_price is None:
        # book emptied out at the very end -- fall back to the last trade price
        mark_price = loop.trade_log[-1].price if loop.trade_log else 0

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    plot_spread(axes[0][0], loop.book_snapshots)
    plot_depth(axes[0][1], loop.book_snapshots)
    plot_price_impact(axes[1][0], loop.order_impacts)
    plot_pnl(axes[1][1], loop.trade_log, mark_price)

    fig.suptitle(f"Market Microstructure Simulator -- {END_TIME:.0f} time units, {len(loop.trade_log)} trades")
    fig.tight_layout()

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"Saved dashboard to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
