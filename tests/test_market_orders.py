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


def make_market(order_id, side, quantity, agent_id=1, timestamp=0.0):
    return Order(
        order_id=order_id,
        agent_id=agent_id,
        side=side,
        order_type=OrderType.MARKET,
        price=None,
        quantity=quantity,
        remaining=quantity,
        timestamp=timestamp,
        seq=order_id,
    )


class TestFullFill:
    def test_market_order_fully_fills_against_resting_liquidity(self):
        book = OrderBook()
        resting = make_limit(1, Side.SELL, price=10_000, quantity=10, agent_id=1)
        book.submit_limit_order(resting)

        incoming = make_market(2, Side.BUY, quantity=10, agent_id=2)
        trades = book.submit_market_order(incoming)

        assert len(trades) == 1
        assert trades[0].price == 10_000
        assert trades[0].quantity == 10
        assert incoming.status is OrderStatus.FILLED
        assert incoming.remaining == 0


class TestPartialFillCancelsRemainder:
    def test_unfilled_remainder_is_cancelled_not_resting(self):
        book = OrderBook()
        resting = make_limit(1, Side.SELL, price=10_000, quantity=4, agent_id=1)
        book.submit_limit_order(resting)

        incoming = make_market(2, Side.BUY, quantity=10, agent_id=2)
        trades = book.submit_market_order(incoming)

        assert len(trades) == 1
        assert trades[0].quantity == 4
        assert incoming.status is OrderStatus.CANCELLED
        assert incoming.remaining == 6

        # never rests -- book has nothing on either side afterward
        assert book.best_bid is None
        assert book.best_ask is None
        assert 2 not in book.orders_by_id


class TestEmptyBook:
    def test_market_order_against_empty_book_is_a_clean_no_op(self):
        book = OrderBook()
        incoming = make_market(1, Side.BUY, quantity=5, agent_id=1)
        trades = book.submit_market_order(incoming)

        assert trades == []
        assert incoming.status is OrderStatus.CANCELLED
        assert incoming.remaining == 5


class TestSweepsMultipleLevels:
    def test_market_order_ignores_price_and_sweeps_levels(self):
        book = OrderBook()
        book.submit_limit_order(make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1))
        book.submit_limit_order(make_limit(2, Side.SELL, price=10_500, quantity=5, agent_id=1))

        incoming = make_market(3, Side.BUY, quantity=10, agent_id=2)
        trades = book.submit_market_order(incoming)

        assert [t.price for t in trades] == [10_000, 10_500]
        assert incoming.status is OrderStatus.FILLED


class TestWrongOrderType:
    def test_submit_market_order_rejects_limit_order(self):
        import pytest

        book = OrderBook()
        limit_order = make_limit(1, Side.BUY, price=10_000, quantity=5)
        with pytest.raises(ValueError):
            book.submit_market_order(limit_order)
