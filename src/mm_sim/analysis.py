from mm_sim.metrics import BookSnapshot, OrderImpact


def mid_price_returns(snapshots: list[BookSnapshot]) -> list[float]:
    """Simple returns between consecutive snapshots with a defined mid price.

    Snapshots where mid_price is None (one side of the book briefly empty) are
    dropped rather than treated as a return to/from zero -- a gap in coverage,
    not a real price move.
    """
    mids = [s.mid_price for s in snapshots if s.mid_price is not None]
    return [
        (mids[i] - mids[i - 1]) / mids[i - 1]
        for i in range(1, len(mids))
        if mids[i - 1] != 0
    ]


def estimate_volatility(snapshots: list[BookSnapshot]) -> float:
    """Realized volatility of the mid price, in price units per sqrt(unit
    simulated time) -- i.e. the sigma such that Var(S_t - S_0) ~= sigma^2 * t,
    which is what the Avellaneda-Stoikov model needs (it assumes the mid price
    follows dS = sigma * dW, working in raw price units, not log-returns).

    Uses the standard realized-variance estimator: sum of squared price changes
    divided by total elapsed time. Timestamped snapshots (not evenly spaced)
    are used directly rather than resampled to a fixed grid, since the
    estimator doesn't require even spacing.
    """
    points = [(s.timestamp, s.mid_price) for s in snapshots if s.mid_price is not None]
    if len(points) < 2:
        return 0.0
    elapsed = points[-1][0] - points[0][0]
    if elapsed <= 0:
        return 0.0
    sum_sq_changes = sum((points[i][1] - points[i - 1][1]) ** 2 for i in range(1, len(points)))
    return (sum_sq_changes / elapsed) ** 0.5


def pearson_correlation(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n != len(ys) or n == 0:
        raise ValueError("xs and ys must be the same non-zero length")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / (var_x**0.5 * var_y**0.5)


def autocorrelation(series: list[float], lag: int) -> float:
    """Pearson correlation of `series` against itself shifted by `lag` steps.

    Volatility clustering shows up as autocorrelation(abs(returns), lag) being
    clearly positive at small lags, in contrast to autocorrelation(returns, lag)
    (raw, signed returns) being close to zero -- that contrast is the actual
    stylized fact (Cont 2001), not either number alone.
    """
    if lag <= 0:
        raise ValueError("lag must be positive")
    if lag >= len(series):
        raise ValueError("lag must be smaller than the series length")
    return pearson_correlation(series[:-lag], series[lag:])


def bucket_price_impact_by_size(
    impacts: list[OrderImpact], n_buckets: int = 10
) -> list[tuple[float, float, int]]:
    """Group filled orders into `n_buckets` equal-width buckets by size, returning
    (avg_size, avg_abs_price_impact, count) per non-empty bucket, sorted by size.

    Used to check whether impact grows sub-linearly (concave) with trade size --
    Kyle's model predicts linear impact; a common empirical finding is concave
    (e.g. square-root-law-style) impact instead.
    """
    filled = [
        (impact.filled_quantity, abs(impact.price_impact))
        for impact in impacts
        if impact.filled_quantity > 0 and impact.price_impact is not None
    ]
    if not filled:
        return []

    min_size = min(size for size, _ in filled)
    max_size = max(size for size, _ in filled)
    if min_size == max_size:
        avg_impact = sum(impact for _, impact in filled) / len(filled)
        return [(float(min_size), avg_impact, len(filled))]

    width = (max_size - min_size) / n_buckets
    buckets: list[list[tuple[int, float]]] = [[] for _ in range(n_buckets)]
    for size, impact in filled:
        idx = min(int((size - min_size) / width), n_buckets - 1)
        buckets[idx].append((size, impact))

    result = []
    for bucket in buckets:
        if not bucket:
            continue
        sizes = [s for s, _ in bucket]
        bucket_impacts = [i for _, i in bucket]
        result.append((sum(sizes) / len(sizes), sum(bucket_impacts) / len(bucket_impacts), len(bucket)))
    return result
