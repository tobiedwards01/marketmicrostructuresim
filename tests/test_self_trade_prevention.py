from mm_sim.models import Order, OrderStatus, OrderType, Side
from mm_sim.order_book import OrderBook


def make_limit(order_id, side, price, quantity, agent_id, timestamp=0.0):
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


class TestSkipsOwnOrderMatchesNext:
    def test_incoming_order_skips_own_resting_order_and_matches_the_next(self):
        book = OrderBook()
        own = make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        other = make_limit(2, Side.SELL, price=10_000, quantity=5, agent_id=2)
        book.submit_limit_order(own)
        book.submit_limit_order(other)

        incoming = make_limit(3, Side.BUY, price=10_000, quantity=5, agent_id=1)
        trades = book.submit_limit_order(incoming)

        assert len(trades) == 1
        assert trades[0].maker_order_id == 2  # other agent's order, not its own
        assert incoming.status is OrderStatus.FILLED
        # its own resting order is untouched, still sitting in the book
        assert own.status is OrderStatus.NEW
        assert own.remaining == 5

    def test_own_order_preserved_in_place_not_removed_from_queue(self):
        book = OrderBook()
        own = make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        other = make_limit(2, Side.SELL, price=10_000, quantity=5, agent_id=2)
        book.submit_limit_order(own)
        book.submit_limit_order(other)

        incoming = make_limit(3, Side.BUY, price=10_000, quantity=5, agent_id=1)
        book.submit_limit_order(incoming)

        assert list(book.asks[10_000]) == [own]


class TestOnlyOwnLiquidityMeansOrderRests:
    def test_order_that_would_only_match_itself_rests_instead(self):
        book = OrderBook()
        own = make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        book.submit_limit_order(own)

        incoming = make_limit(2, Side.BUY, price=10_000, quantity=5, agent_id=1)
        trades = book.submit_limit_order(incoming)

        assert trades == []
        assert incoming.status is OrderStatus.NEW
        assert incoming.remaining == 5
        assert own.status is OrderStatus.NEW  # untouched
        assert book.best_bid == 10_000
        assert book.best_ask == 10_000  # both rest -- book "locked" by STP, not a real cross


class TestSkipsToNextPriceLevel:
    def test_own_liquidity_at_best_price_skipped_in_favor_of_worse_priced_other_agent(self):
        book = OrderBook()
        own_best = make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        other_worse = make_limit(2, Side.SELL, price=10_010, quantity=5, agent_id=2)
        book.submit_limit_order(own_best)
        book.submit_limit_order(other_worse)

        incoming = make_limit(3, Side.BUY, price=10_010, quantity=5, agent_id=1)
        trades = book.submit_limit_order(incoming)

        assert len(trades) == 1
        assert trades[0].price == 10_010
        assert trades[0].maker_order_id == 2
        assert own_best.status is OrderStatus.NEW  # skipped, left resting at the better price


class TestSelfTradePreventionWithMarketOrders:
    def test_market_order_skips_own_liquidity_too(self):
        book = OrderBook()
        own = make_limit(1, Side.SELL, price=10_000, quantity=5, agent_id=1)
        other = make_limit(2, Side.SELL, price=10_000, quantity=5, agent_id=2)
        book.submit_limit_order(own)
        book.submit_limit_order(other)

        from mm_sim.models import Order as _Order

        market_order = _Order(
            order_id=3,
            agent_id=1,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=5,
            remaining=5,
            timestamp=0.0,
            seq=3,
        )
        trades = book.submit_market_order(market_order)

        assert len(trades) == 1
        assert trades[0].maker_order_id == 2
        assert own.status is OrderStatus.NEW
