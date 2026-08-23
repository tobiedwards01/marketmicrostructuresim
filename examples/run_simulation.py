"""Phase 2 demo: noise traders + an informed trader + a naive market maker,
all interacting through the real EventLoop and OrderBook.

Run with:
    uv run python examples/run_simulation.py

There's no metrics pipeline yet (that's Phase 3) -- this just runs the
simulation and prints a few summary numbers so you can see it actually doing
something end to end.
"""

from mm_sim.agents import InformedTrader, NaiveMarketMaker, NoiseTrader
from mm_sim.event_loop import EventLoop
from mm_sim.models import Side

REFERENCE_PRICE = 10_000  # $100.00, in cents
END_TIME = 200.0


def build_agents() -> list:
    noise_traders = [
        NoiseTrader(
            agent_id=100 + i,
            reference_price=REFERENCE_PRICE,
            price_band_ticks=50,
            min_quantity=1,
            max_quantity=10,
            arrival_rate=1.5,
            seed=1000 + i,
        )
        for i in range(5)
    ]
    informed_trader = InformedTrader(
        agent_id=200,
        initial_true_price=REFERENCE_PRICE,
        true_price_volatility=2.0,
        signal_noise_std=5.0,
        edge_threshold=15,
        quantity=10,
        arrival_rate=0.3,
        seed=2000,
    )
    market_maker = NaiveMarketMaker(
        agent_id=300,
        reference_price=REFERENCE_PRICE,
        half_spread_ticks=10,
        quote_size=10,
        max_inventory=50,
        requote_interval=0.5,
    )
    return [*noise_traders, informed_trader, market_maker], informed_trader, market_maker


def main() -> None:
    agents, informed_trader, market_maker = build_agents()
    loop = EventLoop(agents)

    loop.run_until(END_TIME)

    trades = loop.trade_log
    informed_trades = [t for t in trades if t.taker_agent_id == informed_trader.agent_id]
    mm_trades = [t for t in trades if market_maker.agent_id in (t.maker_agent_id, t.taker_agent_id)]

    print(f"Simulated {END_TIME:.0f} time units with {len(agents)} agents "
          f"(5 noise traders, 1 informed trader, 1 market maker)\n")

    print(f"Total trades: {len(trades)}")
    if trades:
        avg_price = sum(t.price for t in trades) / len(trades) / 100
        buy_initiated = sum(1 for t in trades if t.aggressor_side is Side.BUY)
        print(f"  avg trade price: ${avg_price:.2f}")
        print(f"  buy-initiated:  {buy_initiated} ({buy_initiated / len(trades):.0%})")
        print(f"  sell-initiated: {len(trades) - buy_initiated} ({1 - buy_initiated / len(trades):.0%})")

    print(f"\nInformed trader: {len(informed_trades)} trades as taker "
          f"(final belief of true price: ${informed_trader.true_price / 100:.2f})")

    print(f"\nMarket maker: {len(mm_trades)} trades, final inventory {market_maker.inventory}")

    bid = f"${loop.book.best_bid / 100:.2f}" if loop.book.best_bid is not None else "--"
    ask = f"${loop.book.best_ask / 100:.2f}" if loop.book.best_ask is not None else "--"
    spread = f"${loop.book.spread / 100:.2f}" if loop.book.spread is not None else "--"
    print(f"\nFinal book: best_bid={bid}  best_ask={ask}  spread={spread}")


if __name__ == "__main__":
    main()
