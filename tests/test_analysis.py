import pytest

from mm_sim.analysis import (
    autocorrelation,
    bucket_price_impact_by_size,
    mid_price_returns,
    pearson_correlation,
)
from mm_sim.metrics import BookSnapshot, OrderImpact
from mm_sim.models import OrderType, Side


def make_snapshot(timestamp, mid_price):
    return BookSnapshot(
        timestamp=timestamp, best_bid=None, best_ask=None, spread=None,
        mid_price=mid_price, bid_depth=0, ask_depth=0,
    )


def make_impact(filled_quantity, price_impact, timestamp=0.0, agent_id=1):
    return OrderImpact(
        timestamp=timestamp, agent_id=agent_id, side=Side.BUY, order_type=OrderType.LIMIT,
        requested_quantity=filled_quantity, filled_quantity=filled_quantity,
        mid_price_before=100.0, mid_price_after=100.0 + price_impact,
    )


class TestMidPriceReturns:
    def test_computes_simple_returns_between_consecutive_mids(self):
        snapshots = [make_snapshot(0, 100.0), make_snapshot(1, 101.0), make_snapshot(2, 99.99)]
        returns = mid_price_returns(snapshots)

        assert returns[0] == pytest.approx(0.01)
        assert returns[1] == pytest.approx((99.99 - 101.0) / 101.0)

    def test_skips_snapshots_with_no_mid_price(self):
        snapshots = [make_snapshot(0, 100.0), make_snapshot(1, None), make_snapshot(2, 102.0)]
        returns = mid_price_returns(snapshots)

        assert len(returns) == 1
        assert returns[0] == pytest.approx(0.02)  # 100 -> 102, skipping the gap entirely

    def test_empty_or_single_snapshot_gives_no_returns(self):
        assert mid_price_returns([]) == []
        assert mid_price_returns([make_snapshot(0, 100.0)]) == []


class TestPearsonCorrelation:
    def test_perfect_positive_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [2, 4, 6, 8, 10]
        assert pearson_correlation(xs, ys) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [10, 8, 6, 4, 2]
        assert pearson_correlation(xs, ys) == pytest.approx(-1.0)

    def test_no_variance_in_y_returns_zero_rather_than_dividing_by_zero(self):
        xs = [1, 2, 3]
        ys = [5, 5, 5]
        assert pearson_correlation(xs, ys) == 0.0

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            pearson_correlation([1, 2], [1, 2, 3])


class TestAutocorrelation:
    def test_linear_series_has_near_perfect_lag_one_autocorrelation(self):
        series = [float(i) for i in range(1, 11)]
        assert autocorrelation(series, lag=1) == pytest.approx(1.0)

    def test_alternating_series_has_negative_lag_one_autocorrelation(self):
        series = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
        assert autocorrelation(series, lag=1) == pytest.approx(-1.0)

    def test_rejects_non_positive_lag(self):
        with pytest.raises(ValueError):
            autocorrelation([1.0, 2.0, 3.0], lag=0)

    def test_rejects_lag_too_large_for_series(self):
        with pytest.raises(ValueError):
            autocorrelation([1.0, 2.0], lag=2)


class TestBucketPriceImpactBySize:
    def test_excludes_zero_fill_and_undefined_impact(self):
        impacts = [
            make_impact(filled_quantity=0, price_impact=0.0),
            OrderImpact(
                timestamp=0.0, agent_id=1, side=Side.BUY, order_type=OrderType.MARKET,
                requested_quantity=5, filled_quantity=5, mid_price_before=None, mid_price_after=None,
            ),
            make_impact(filled_quantity=5, price_impact=0.1),
        ]
        result = bucket_price_impact_by_size(impacts, n_buckets=5)

        total_count = sum(count for _, _, count in result)
        assert total_count == 1

    def test_empty_input_returns_empty_list(self):
        assert bucket_price_impact_by_size([]) == []

    def test_uniform_size_collapses_to_one_bucket(self):
        impacts = [make_impact(filled_quantity=10, price_impact=0.05) for _ in range(4)]
        result = bucket_price_impact_by_size(impacts, n_buckets=5)

        assert len(result) == 1
        avg_size, avg_impact, count = result[0]
        assert avg_size == 10.0
        assert avg_impact == pytest.approx(0.05)
        assert count == 4

    def test_buckets_preserve_total_count_across_a_size_range(self):
        impacts = [make_impact(filled_quantity=q, price_impact=0.01 * q) for q in range(1, 21)]
        result = bucket_price_impact_by_size(impacts, n_buckets=4)

        assert sum(count for _, _, count in result) == 20
        # sorted by size ascending
        sizes = [avg_size for avg_size, _, _ in result]
        assert sizes == sorted(sizes)
