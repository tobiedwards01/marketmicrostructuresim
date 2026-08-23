import pytest

from mm_sim.models import Order, OrderStatus, OrderType, Side
from mm_sim.order_book import OrderBook


def make_limit(order_id, side, price, quantity, agent_id=1, timestamp=0.0):
    return Order(
        order_id=order_id,
        agent_id=agent_id,
        side=side,
        order_type=OrderType.LIMIT,
        price=price,
        quantity=quantity,
        remaining=quantity,
        timestamp=timestamp,
        seq=order_id,
    )


class TestCancelRestingOrder:
    def test_cancel_returns_true_and_marks_cancelled(self):
        book = OrderBook()
        order = make_limit(1, Side.BUY, price=9_900, quantity=10)
        book.submit_limit_order(order)

        assert book.cancel_order(1) is True
        assert order.status is OrderStatus.CANCELLED

    def test_cancelling_the_only_order_at_a_level_still_leaves_it_in_the_deque(self):
        # Lazy deletion: cancel doesn't touch the book structure directly.
        book = OrderBook()
        order = make_limit(1, Side.BUY, price=9_900, quantity=10)
        book.submit_limit_order(order)
        book.cancel_order(1)

        assert order in book.bids[9_900]
        # but best_bid still reports it -- it's only purged when matching walks past it
        assert book.best_bid == 9_900


class TestCancelTerminalOrder:
    def test_cancelling_already_filled_order_is_a_no_op(self):
        book = OrderBook()
        resting = make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        book.submit_limit_order(resting)
        incoming = make_limit(2, Side.BUY, price=10_000, quantity=5, agent_id=2)
        book.submit_limit_order(incoming)
        assert resting.status is OrderStatus.FILLED

        assert book.cancel_order(1) is False
        assert resting.status is OrderStatus.FILLED

    def test_cancelling_already_cancelled_order_is_a_no_op(self):
        book = OrderBook()
        order = make_limit(1, Side.BUY, price=9_900, quantity=10)
        book.submit_limit_order(order)
        book.cancel_order(1)

        assert book.cancel_order(1) is False
        assert order.status is OrderStatus.CANCELLED


class TestCancelUnknownOrder:
    def test_raises_key_error(self):
        book = OrderBook()
        with pytest.raises(KeyError):
            book.cancel_order(999)


class TestCancelledOrderSkippedByMatching:
    def test_incoming_order_matches_next_live_order_not_the_cancelled_one(self):
        book = OrderBook()
        first = make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        second = make_limit(2, Side.SELL, price=10_000, quantity=5, agent_id=1)
        book.submit_limit_order(first)
        book.submit_limit_order(second)
        book.cancel_order(1)

        incoming = make_limit(3, Side.BUY, price=10_000, quantity=5, agent_id=2)
        trades = book.submit_limit_order(incoming)

        assert len(trades) == 1
        assert trades[0].maker_order_id == 2  # not the cancelled order #1
        assert incoming.status is OrderStatus.FILLED

    def test_price_level_with_only_a_cancelled_order_is_purged_and_book_updates(self):
        book = OrderBook()
        only_order = make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        book.submit_limit_order(only_order)
        deeper = make_limit(2, Side.SELL, price=10_100, quantity=5, agent_id=1)
        book.submit_limit_order(deeper)
        book.cancel_order(1)

        incoming = make_limit(3, Side.BUY, price=10_100, quantity=5, agent_id=2)
        trades = book.submit_limit_order(incoming)

        assert len(trades) == 1
        assert trades[0].maker_order_id == 2
        # the cancelled level should have been purged entirely
        assert 10_000 not in book.asks
        assert book.best_ask is None  # deeper level fully consumed too
