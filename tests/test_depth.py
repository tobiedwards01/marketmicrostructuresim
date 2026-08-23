from mm_sim.models import Order, OrderType, Side
from mm_sim.order_book import OrderBook


def make_limit(order_id, side, price, quantity, agent_id=1):
    return Order(
        order_id=order_id, agent_id=agent_id, side=side, order_type=OrderType.LIMIT,
        price=price, quantity=quantity, remaining=quantity, timestamp=0.0, seq=order_id,
    )


class TestEmptyBook:
    def test_depth_is_zero_on_both_sides(self):
        book = OrderBook()
        assert book.bid_depth == 0
        assert book.ask_depth == 0


class TestSumsAcrossPriceLevels:
    def test_bid_depth_sums_quantity_across_multiple_price_levels(self):
        book = OrderBook()
        book.submit_limit_order(make_limit(1, Side.BUY, price=9_990, quantity=10))
        book.submit_limit_order(make_limit(2, Side.BUY, price=9_980, quantity=15))
        book.submit_limit_order(make_limit(3, Side.SELL, price=10_010, quantity=7))

        assert book.bid_depth == 25
        assert book.ask_depth == 7


class TestReflectsPartialFills:
    def test_depth_decreases_after_a_partial_fill(self):
        book = OrderBook()
        book.submit_limit_order(make_limit(1, Side.SELL, price=10_000, quantity=10, agent_id=1))
        book.submit_limit_order(make_limit(2, Side.BUY, price=10_000, quantity=4, agent_id=2))

        assert book.ask_depth == 6  # 10 - 4 filled


class TestExcludesCancelledOrders:
    def test_cancelled_order_does_not_count_toward_depth(self):
        book = OrderBook()
        book.submit_limit_order(make_limit(1, Side.BUY, price=9_990, quantity=10))
        book.submit_limit_order(make_limit(2, Side.BUY, price=9_980, quantity=15))

        book.cancel_order(1)

        # order #1 is lazily-deleted -- still physically in the deque -- but must
        # not be double-counted as live depth
        assert book.bid_depth == 15

    def test_cancelling_everything_on_a_side_leaves_zero_depth(self):
        book = OrderBook()
        book.submit_limit_order(make_limit(1, Side.SELL, price=10_010, quantity=5))
        book.submit_limit_order(make_limit(2, Side.SELL, price=10_020, quantity=8))

        book.cancel_order(1)
        book.cancel_order(2)

        assert book.ask_depth == 0
