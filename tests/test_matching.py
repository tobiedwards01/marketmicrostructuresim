from mm_sim.models import Order, OrderStatus, OrderType, Side
from mm_sim.order_book import OrderBook


def make_order(order_id, side, price, quantity, seq=None, agent_id=1, timestamp=0.0):
    return Order(
        order_id=order_id,
        agent_id=agent_id,
        side=side,
        order_type=OrderType.LIMIT,
        price=price,
        quantity=quantity,
        remaining=quantity,
        timestamp=timestamp,
        seq=seq if seq is not None else order_id,
    )


class TestNoCross:
    def test_non_crossing_order_just_rests(self):
        book = OrderBook()
        resting = make_order(1, Side.SELL, price=10_100, quantity=10)
        book.submit_limit_order(resting)

        incoming = make_order(2, Side.BUY, price=10_000, quantity=10)
        trades = book.submit_limit_order(incoming)

        assert trades == []
        assert incoming.status is OrderStatus.NEW
        assert incoming.remaining == 10
        assert book.best_bid == 10_000
        assert book.best_ask == 10_100


class TestFullFill:
    def test_incoming_order_fully_fills_against_one_resting_order(self):
        book = OrderBook()
        resting = make_order(1, Side.SELL, price=10_000, quantity=10, agent_id=1)
        book.submit_limit_order(resting)

        incoming = make_order(2, Side.BUY, price=10_000, quantity=10, agent_id=2)
        trades = book.submit_limit_order(incoming)

        assert len(trades) == 1
        trade = trades[0]
        assert trade.price == 10_000
        assert trade.quantity == 10
        assert trade.maker_order_id == 1
        assert trade.taker_order_id == 2
        assert trade.aggressor_side is Side.BUY

        assert resting.remaining == 0
        assert resting.status is OrderStatus.FILLED
        assert incoming.remaining == 0
        assert incoming.status is OrderStatus.FILLED

        # resting order fully consumed -> book empty on both sides
        assert book.best_bid is None
        assert book.best_ask is None


class TestPartialFill:
    def test_incoming_order_partially_fills_and_rests_remainder(self):
        book = OrderBook()
        resting = make_order(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        book.submit_limit_order(resting)

        incoming = make_order(2, Side.BUY, price=10_000, quantity=10, agent_id=2)
        trades = book.submit_limit_order(incoming)

        assert len(trades) == 1
        assert trades[0].quantity == 5

        assert resting.remaining == 0
        assert resting.status is OrderStatus.FILLED

        assert incoming.remaining == 5
        assert incoming.status is OrderStatus.PARTIALLY_FILLED
        assert book.best_bid == 10_000  # remainder now resting
        assert book.orders_by_id[2] is incoming

    def test_resting_order_partially_filled_stays_at_front_of_queue(self):
        book = OrderBook()
        resting = make_order(1, Side.SELL, price=10_000, quantity=10, agent_id=1)
        book.submit_limit_order(resting)

        incoming = make_order(2, Side.BUY, price=10_000, quantity=4, agent_id=2)
        trades = book.submit_limit_order(incoming)

        assert len(trades) == 1
        assert trades[0].quantity == 4
        assert resting.remaining == 6
        assert resting.status is OrderStatus.PARTIALLY_FILLED
        assert incoming.remaining == 0
        assert incoming.status is OrderStatus.FILLED

        # partially-filled resting order should still be at the front of its level
        assert list(book.asks[10_000]) == [resting]


class TestSweepMultipleLevels:
    def test_incoming_order_sweeps_across_price_levels(self):
        book = OrderBook()
        ask1 = make_order(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        ask2 = make_order(2, Side.SELL, price=10_010, quantity=5, agent_id=1)
        ask3 = make_order(3, Side.SELL, price=10_020, quantity=5, agent_id=1)
        for o in (ask1, ask2, ask3):
            book.submit_limit_order(o)

        incoming = make_order(4, Side.BUY, price=10_020, quantity=12, agent_id=2)
        trades = book.submit_limit_order(incoming)

        assert [t.price for t in trades] == [10_000, 10_010, 10_020]
        assert [t.quantity for t in trades] == [5, 5, 2]

        assert ask1.status is OrderStatus.FILLED
        assert ask2.status is OrderStatus.FILLED
        assert ask3.status is OrderStatus.PARTIALLY_FILLED
        assert ask3.remaining == 3

        assert incoming.remaining == 0
        assert incoming.status is OrderStatus.FILLED
        assert book.best_ask == 10_020  # ask3's leftover 3 still resting


class TestPriceTimePriority:
    def test_older_order_at_same_price_fills_first(self):
        book = OrderBook()
        older = make_order(1, Side.SELL, price=10_000, quantity=5, agent_id=1, timestamp=1.0)
        newer = make_order(2, Side.SELL, price=10_000, quantity=5, agent_id=1, timestamp=2.0)
        book.submit_limit_order(older)
        book.submit_limit_order(newer)

        incoming = make_order(3, Side.BUY, price=10_000, quantity=5, agent_id=2, timestamp=3.0)
        trades = book.submit_limit_order(incoming)

        assert len(trades) == 1
        assert trades[0].maker_order_id == 1  # older order, not newer
        assert older.status is OrderStatus.FILLED
        assert newer.status is OrderStatus.NEW
        assert newer.remaining == 5


class TestBookNeverCrossed:
    def test_book_is_never_crossed_after_a_sequence_of_orders(self):
        # Distinct agent_ids throughout -- otherwise self-trade prevention would
        # legitimately block some of these crosses, which is a different behavior
        # (see test_self_trade_prevention.py) and not what this test is checking.
        book = OrderBook()
        orders = [
            make_order(1, Side.BUY, price=9_990, quantity=10, agent_id=1),
            make_order(2, Side.SELL, price=10_010, quantity=10, agent_id=2),
            make_order(3, Side.BUY, price=10_020, quantity=5, agent_id=3),  # crosses ask
            make_order(4, Side.SELL, price=9_985, quantity=20, agent_id=4),  # crosses remaining bids
        ]
        for o in orders:
            book.submit_limit_order(o)

        if book.best_bid is not None and book.best_ask is not None:
            assert book.best_bid < book.best_ask
