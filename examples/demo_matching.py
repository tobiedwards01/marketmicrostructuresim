"""Small hand-run demo of the Phase 1 matching engine.

Run with:
    uv run python examples/demo_matching.py

There's no simulation loop or agents yet (that's Phase 2+) -- this just
submits a handful of orders directly to an OrderBook so you can see the
matching logic actually do something.
"""

from itertools import count

from mm_sim.models import Order, OrderType, Side
from mm_sim.order_book import OrderBook

order_ids = count(1)


def submit(book: OrderBook, side: Side, price: int, quantity: int, agent_id: int) -> None:
    order_id = next(order_ids)
    order = Order(
        order_id=order_id,
        agent_id=agent_id,
        side=side,
        order_type=OrderType.LIMIT,
        price=price,
        quantity=quantity,
        remaining=quantity,
        timestamp=0.0,
        seq=order_id,  # single order submitted at a time here, so seq can mirror order_id
    )
    print(f"  submit  {side.name:4s} {quantity:>4d} @ {price / 100:.2f}  (order #{order.order_id}, agent {agent_id})")
    trades = book.submit_limit_order(order)
    for t in trades:
        print(
            f"    -> TRADE {t.quantity} @ {t.price / 100:.2f}  "
            f"(maker order #{t.maker_order_id} / agent {t.maker_agent_id}, "
            f"taker order #{t.taker_order_id} / agent {t.taker_agent_id})"
        )
    print_book(book)


def print_book(book: OrderBook) -> None:
    bid = f"{book.best_bid / 100:.2f}" if book.best_bid is not None else "--"
    ask = f"{book.best_ask / 100:.2f}" if book.best_ask is not None else "--"
    spread = f"{book.spread / 100:.2f}" if book.spread is not None else "--"
    print(f"    book: best_bid={bid}  best_ask={ask}  spread={spread}")


def main() -> None:
    book = OrderBook()

    print("Building a resting book (agent 1 quoting both sides):")
    submit(book, Side.BUY, price=9_950, quantity=10, agent_id=1)
    submit(book, Side.BUY, price=9_940, quantity=15, agent_id=1)
    submit(book, Side.SELL, price=10_050, quantity=10, agent_id=1)
    submit(book, Side.SELL, price=10_060, quantity=15, agent_id=1)

    print("\nAgent 2 sends a buy that partially crosses the best ask:")
    submit(book, Side.BUY, price=10_050, quantity=6, agent_id=2)

    print("\nAgent 3 sends a large sell that sweeps through both remaining bid levels:")
    submit(book, Side.SELL, price=9_900, quantity=20, agent_id=3)


if __name__ == "__main__":
    main()
