# Market Microstructure Simulator

A limit-order-book market built from scratch, populated with multiple types of trading
agents (noise traders, an informed trader, market makers), used to study emergent
microstructure dynamics — spreads, price impact, adverse selection — and to train a
reinforcement-learning market-making agent inside the simulated market.

## Status

Phase 0 (research & design), Phase 1 (core matching engine), and Phase 2 (baseline
agent population) complete. Phase 3 (simulation metrics pipeline) up next.

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
```

## Architecture

- `src/mm_sim/models.py` — `Order`, `Trade`, and their enums
- `src/mm_sim/order_book.py` — the limit order book: price-time-priority matching, market orders (IOC), cancellation, self-trade prevention
- `src/mm_sim/event_loop.py` — heapq-based discrete-event simulator that wakes agents in timestamp order
- `src/mm_sim/agents/` — `NoiseTrader`, `InformedTrader`, `NaiveMarketMaker`

See [DESIGN.md](DESIGN.md) for the data model and event-loop design in more depth, and
[DECISIONS.md](DECISIONS.md) for why things ended up the way they did.

## Results

_To be filled in during Phase 3/4 (metrics pipeline and emergent-behaviour analysis)._
