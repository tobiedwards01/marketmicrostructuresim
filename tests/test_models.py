import pytest

from mm_sim.models import Order, OrderStatus, OrderType, Side, Trade


def make_order(**overrides):
    defaults = dict(
        order_id=1,
        agent_id=1,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=10_000,
        quantity=100,
        remaining=100,
        timestamp=0.0,
        seq=1,
    )
    defaults.update(overrides)
    return Order(**defaults)


def make_trade(**overrides):
    defaults = dict(
        trade_id=1,
        timestamp=0.0,
        price=10_000,
        quantity=50,
        maker_order_id=1,
        taker_order_id=2,
        maker_agent_id=1,
        taker_agent_id=2,
        aggressor_side=Side.BUY,
    )
    defaults.update(overrides)
    return Trade(**defaults)


class TestOrder:
    def test_defaults_to_new_status(self):
        order = make_order()
        assert order.status is OrderStatus.NEW

    def test_remaining_starts_equal_to_quantity_by_convention(self):
        order = make_order(quantity=100, remaining=100)
        assert order.remaining == order.quantity

    def test_remaining_is_mutable(self):
        order = make_order(quantity=100, remaining=100)
        order.remaining -= 40
        assert order.remaining == 60
        assert order.quantity == 100  # original size untouched

    @pytest.mark.parametrize("bad_quantity", [0, -1, -100])
    def test_rejects_non_positive_quantity(self, bad_quantity):
        with pytest.raises(ValueError):
            make_order(quantity=bad_quantity, remaining=bad_quantity)

    @pytest.mark.parametrize("bad_remaining", [-1, 101])
    def test_rejects_remaining_out_of_bounds(self, bad_remaining):
        with pytest.raises(ValueError):
            make_order(quantity=100, remaining=bad_remaining)

    def test_limit_order_requires_price(self):
        with pytest.raises(ValueError):
            make_order(order_type=OrderType.LIMIT, price=None)

    def test_market_order_forbids_price(self):
        with pytest.raises(ValueError):
            make_order(order_type=OrderType.MARKET, price=10_000)

    def test_market_order_with_no_price_is_valid(self):
        order = make_order(order_type=OrderType.MARKET, price=None)
        assert order.price is None

    @pytest.mark.parametrize("bad_price", [0, -1, -500])
    def test_rejects_non_positive_price(self, bad_price):
        with pytest.raises(ValueError):
            make_order(price=bad_price)


class TestTrade:
    def test_is_immutable(self):
        trade = make_trade()
        with pytest.raises(AttributeError):
            trade.quantity = 999

    @pytest.mark.parametrize("bad_quantity", [0, -1])
    def test_rejects_non_positive_quantity(self, bad_quantity):
        with pytest.raises(ValueError):
            make_trade(quantity=bad_quantity)

    @pytest.mark.parametrize("bad_price", [0, -1])
    def test_rejects_non_positive_price(self, bad_price):
        with pytest.raises(ValueError):
            make_trade(price=bad_price)
