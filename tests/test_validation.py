import random
from itertools import count

import pytest

from mm_sim.models import Order, OrderStatus, OrderType, Side
from mm_sim.order_book import OrderBook


class TestDuplicateOrderId:
    def test_resubmitting_same_order_id_raises(self):
        book = OrderBook()
        order1 = Order(
            order_id=1, agent_id=1, side=Side.BUY, order_type=OrderType.LIMIT,
            price=10_000, quantity=5, remaining=5, timestamp=0.0, seq=1,
        )
        book.submit_limit_order(order1)

        order2 = Order(
            order_id=1, agent_id=2, side=Side.SELL, order_type=OrderType.LIMIT,
            price=10_000, quantity=5, remaining=5, timestamp=1.0, seq=2,
        )
        with pytest.raises(ValueError):
            book.submit_limit_order(order2)

    def test_duplicate_check_applies_across_order_types(self):
        book = OrderBook()
        limit_order = Order(
            order_id=1, agent_id=1, side=Side.SELL, order_type=OrderType.LIMIT,
            price=10_000, quantity=5, remaining=5, timestamp=0.0, seq=1,
        )
        book.submit_limit_order(limit_order)

        market_order = Order(
            order_id=1, agent_id=2, side=Side.BUY, order_type=OrderType.MARKET,
            price=None, quantity=5, remaining=5, timestamp=1.0, seq=2,
        )
        with pytest.raises(ValueError):
            book.submit_market_order(market_order)

    def test_a_fully_filled_order_id_still_cannot_be_reused(self):
        book = OrderBook()
        resting = Order(
            order_id=1, agent_id=1, side=Side.SELL, order_type=OrderType.LIMIT,
            price=10_000, quantity=5, remaining=5, timestamp=0.0, seq=1,
        )
        book.submit_limit_order(resting)
        taker = Order(
            order_id=2, agent_id=2, side=Side.BUY, order_type=OrderType.LIMIT,
            price=10_000, quantity=5, remaining=5, timestamp=1.0, seq=2,
        )
        book.submit_limit_order(taker)
        assert resting.status is OrderStatus.FILLED

        reused_id = Order(
            order_id=1, agent_id=3, side=Side.BUY, order_type=OrderType.LIMIT,
            price=9_000, quantity=1, remaining=1, timestamp=2.0, seq=3,
        )
        with pytest.raises(ValueError):
            book.submit_limit_order(reused_id)


def _live_orders(side_book):
    orders = []
    for level in side_book.values():
        for order in level:
            if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                orders.append(order)
    return orders


def _assert_no_illegitimate_cross(book: OrderBook) -> None:
    """Two DIFFERENT agents' live resting orders should never be able to cross --
    that would mean a real match was missed. Same-agent crosses are fine (that's
    self-trade prevention correctly locking the book instead of self-matching).
    """
    bids = _live_orders(book.bids)
    asks = _live_orders(book.asks)
    for bid in bids:
        for ask in asks:
            if bid.agent_id != ask.agent_id:
                assert bid.price < ask.price, f"illegitimate cross: {bid} vs {ask}"


class TestRandomizedInvariants:
    def test_conservation_and_no_illegitimate_cross_over_random_sequence(self):
        rng = random.Random(1234)
        book = OrderBook()
        order_ids = count(1)
        agents = list(range(1, 6))
        all_orders: list[Order] = []
        all_trades = []

        for step in range(500):
            resting_ids = [
                oid for oid, o in book.orders_by_id.items()
                if o.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)
            ]
            if resting_ids and rng.random() < 0.15:
                book.cancel_order(rng.choice(resting_ids))
            else:
                order_id = next(order_ids)
                quantity = rng.randint(1, 20)
                order = Order(
                    order_id=order_id,
                    agent_id=rng.choice(agents),
                    side=rng.choice([Side.BUY, Side.SELL]),
                    order_type=OrderType.LIMIT,
                    price=rng.randint(9_800, 10_200),
                    quantity=quantity,
                    remaining=quantity,
                    timestamp=float(step),
                    seq=order_id,
                )
                trades = book.submit_limit_order(order)
                all_orders.append(order)
                all_trades.extend(trades)

            _assert_no_illegitimate_cross(book)

        total_filled_across_orders = sum(o.quantity - o.remaining for o in all_orders)
        total_trade_fill = 2 * sum(t.quantity for t in all_trades)
        assert total_filled_across_orders == total_trade_fill
        assert len(all_trades) > 0  # sanity check the random sequence actually produced matches
