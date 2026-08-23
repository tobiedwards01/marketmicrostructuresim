# Market Microstructure Simulator

A limit-order-book market built from scratch, populated with multiple types of trading
agents (noise traders, an informed trader, market makers), used to study emergent
microstructure dynamics — spreads, price impact, adverse selection — and to train a
reinforcement-learning market-making agent inside the simulated market.

## Status

Phase 0 (research & design), Phase 1 (core matching engine), Phase 2 (baseline agent
population), Phase 3 (simulation metrics pipeline), and Phase 4 (emergent behaviour
analysis) complete. Phase 5 (learning market-making agent) up next.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
```

## Try it

```bash
uv run python examples/demo_matching.py    # a handful of orders against the matching engine directly
uv run python examples/run_simulation.py   # a full run: noise traders + informed trader + market maker
uv run python examples/plot_metrics.py     # the same run, plotted -- spread, depth, price impact, P&L per agent
uv run python examples/phase4_analysis.py  # Phase 4 experiments: spread vs. informed intensity, impact concavity, volatility clustering
```

## Architecture

- `src/mm_sim/models.py` — `Order`, `Trade`, and their enums
- `src/mm_sim/order_book.py` — the limit order book: price-time-priority matching, market orders (IOC), cancellation, self-trade prevention, live depth
- `src/mm_sim/event_loop.py` — heapq-based discrete-event simulator that wakes agents in timestamp order, recording metrics as it goes
- `src/mm_sim/agents/` — `NoiseTrader`, `InformedTrader`, `NaiveMarketMaker`
- `src/mm_sim/metrics.py` — book snapshots, per-order price impact, and mark-to-market P&L per agent
- `src/mm_sim/analysis.py` — returns, autocorrelation, correlation, and price-impact bucketing used to test stylized facts against theory

See [DESIGN.md](DESIGN.md) for the data model and event-loop design in more depth, and
[DECISIONS.md](DECISIONS.md) for why things ended up the way they did.

## Results

`examples/plot_metrics.py` produces a 4-panel dashboard from one simulated session: bid-ask
spread over time, order book depth over time, price impact vs. trade size, and P&L per
agent. A real run shows a clean adverse-selection pattern -- all five noise traders lose
money, while the informed trader and market maker both profit.

**[ANALYSIS.md](ANALYSIS.md)** is the Phase 4 deliverable: checking the simulator against
three microstructure stylized facts. Spread widens with informed-trading intensity
(Glosten-Milgrom, r=0.989) and price impact is concave in trade size (vs. Kyle's linear
baseline, r=-0.767) both hold up well; volatility clustering (Cont 2001) only holds up
weakly, with a specific mechanistic explanation for why in the writeup.
