from mm_sim.models import Order, OrderType, Side
from mm_sim.order_book import OrderBook


def make_order(order_id, side, price, quantity, seq=None, agent_id=1):
    return Order(
        order_id=order_id,
        agent_id=agent_id,
        side=side,
        order_type=OrderType.LIMIT,
        price=price,
        quantity=quantity,
        remaining=quantity,
        timestamp=0.0,
        seq=seq if seq is not None else order_id,
    )


class TestEmptyBook:
    def test_best_bid_is_none(self):
        assert OrderBook().best_bid is None

    def test_best_ask_is_none(self):
        assert OrderBook().best_ask is None

    def test_spread_is_none(self):
        assert OrderBook().spread is None

    def test_mid_price_is_none(self):
        assert OrderBook().mid_price is None


class TestSingleRestingOrder:
    def test_resting_bid_sets_best_bid(self):
        book = OrderBook()
        book._rest(make_order(1, Side.BUY, price=9_900, quantity=10))
        assert book.best_bid == 9_900
        assert book.best_ask is None

    def test_resting_ask_sets_best_ask(self):
        book = OrderBook()
        book._rest(make_order(1, Side.SELL, price=10_100, quantity=10))
        assert book.best_ask == 10_100
        assert book.best_bid is None

    def test_orders_by_id_lookup(self):
        book = OrderBook()
        order = make_order(1, Side.BUY, price=9_900, quantity=10)
        book._rest(order)
        assert book.orders_by_id[1] is order


class TestBestPricesWithBothSides:
    def test_best_bid_is_highest_bid(self):
        book = OrderBook()
        book._rest(make_order(1, Side.BUY, price=9_800, quantity=10))
        book._rest(make_order(2, Side.BUY, price=9_900, quantity=10))
        book._rest(make_order(3, Side.BUY, price=9_850, quantity=10))
        assert book.best_bid == 9_900

    def test_best_ask_is_lowest_ask(self):
        book = OrderBook()
        book._rest(make_order(1, Side.SELL, price=10_200, quantity=10))
        book._rest(make_order(2, Side.SELL, price=10_100, quantity=10))
        book._rest(make_order(3, Side.SELL, price=10_150, quantity=10))
        assert book.best_ask == 10_100

    def test_spread_and_mid_price(self):
        book = OrderBook()
        book._rest(make_order(1, Side.BUY, price=9_900, quantity=10))
        book._rest(make_order(2, Side.SELL, price=10_100, quantity=10))
        assert book.spread == 200
        assert book.mid_price == 10_000

    def test_same_price_level_orders_preserve_fifo_order(self):
        book = OrderBook()
        first = make_order(1, Side.BUY, price=9_900, quantity=10)
        second = make_order(2, Side.BUY, price=9_900, quantity=5)
        book._rest(first)
        book._rest(second)
        resting = list(book.bids[9_900])
        assert resting == [first, second]
