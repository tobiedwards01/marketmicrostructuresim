from mm_sim.agents.market_maker import NaiveMarketMaker
from mm_sim.event_loop import EventLoop
from mm_sim.models import OrderStatus, Side


def make_mm(reference_price=10_000, half_spread=10, quote_size=5, max_inventory=20, requote_interval=1.0):
    return NaiveMarketMaker(
        agent_id=1,
        reference_price=reference_price,
        half_spread_ticks=half_spread,
        quote_size=quote_size,
        max_inventory=max_inventory,
        requote_interval=requote_interval,
    )


class TestQuotesAroundReferencePriceWhenBookEmpty:
    def test_quotes_symmetric_spread_around_reference_price(self):
        mm = make_mm(reference_price=10_000, half_spread=10, quote_size=5)
        loop = EventLoop([mm])

        mm.act(loop.time, loop)

        assert loop.book.best_bid == 9_990
        assert loop.book.best_ask == 10_010
        assert loop.book.spread == 20
        resting_bid = loop.book.bids[9_990][0]
        resting_ask = loop.book.asks[10_010][0]
        assert resting_bid.quantity == 5
        assert resting_ask.quantity == 5


class TestQuotesAroundMidPrice:
    def test_recenters_on_current_mid_price_not_reference_price(self):
        mm = make_mm(reference_price=10_000, half_spread=10, quote_size=5)
        loop = EventLoop([mm])
        # other participants have pushed the market well away from the MM's reference price;
        # spread wide of where the MM's own quotes will land (mid +/- 10) so the two are distinguishable
        loop.submit_limit(agent_id=2, side=Side.BUY, price=10_480, quantity=5)
        loop.submit_limit(agent_id=2, side=Side.SELL, price=10_520, quantity=5)

        mm.act(loop.time, loop)

        # MM's own quotes should sit around the market mid (10_500), not its stale reference price
        bid_prices = list(loop.book.bids.keys())
        ask_prices = list(loop.book.asks.keys())
        assert 10_480 in bid_prices  # the other agent's bid, untouched
        assert 10_490 in bid_prices  # MM's own bid, mid (10_500) - half_spread (10)
        assert 10_510 in ask_prices  # MM's own ask, mid (10_500) + half_spread (10)


class TestRequoteCancelsPreviousQuotes:
    def test_previous_quotes_are_cancelled_before_placing_new_ones(self):
        mm = make_mm()
        loop = EventLoop([mm])

        mm.act(loop.time, loop)
        first_bid_id = mm._bid_order_id
        first_ask_id = mm._ask_order_id
        assert first_bid_id is not None and first_ask_id is not None

        loop.time = 1.0
        mm.act(loop.time, loop)

        assert loop.book.orders_by_id[first_bid_id].status is OrderStatus.CANCELLED
        assert loop.book.orders_by_id[first_ask_id].status is OrderStatus.CANCELLED
        assert mm._bid_order_id != first_bid_id
        assert mm._ask_order_id != first_ask_id


class TestInventoryLimits:
    def test_stops_quoting_bid_once_max_long_inventory_reached(self):
        mm = make_mm(quote_size=10, max_inventory=10)
        loop = EventLoop([mm])

        mm.act(loop.time, loop)  # MM posts bid @ 9990 and ask @ 10010
        loop.submit_limit(agent_id=2, side=Side.SELL, price=9_990, quantity=10)  # fills MM's bid fully

        # inventory reconciles against the trade log on the MM's next wake, not
        # instantaneously -- it has no way to know about a fill from someone else's
        # order until then
        loop.time = 1.0
        mm.act(loop.time, loop)  # requote: syncs the fill, then should skip the bid (at max)

        assert mm.inventory == 10
        assert loop.book.best_bid is None  # no bid resting -- limit hit

    def test_stops_quoting_ask_once_max_short_inventory_reached(self):
        mm = make_mm(quote_size=10, max_inventory=10)
        loop = EventLoop([mm])

        mm.act(loop.time, loop)  # MM posts bid @ 9990 and ask @ 10010
        loop.submit_limit(agent_id=2, side=Side.BUY, price=10_010, quantity=10)  # fills MM's ask fully

        loop.time = 1.0
        mm.act(loop.time, loop)

        assert mm.inventory == -10
        assert loop.book.best_ask is None

        loop.time = 1.0
        mm.act(loop.time, loop)

        assert loop.book.best_ask is None
