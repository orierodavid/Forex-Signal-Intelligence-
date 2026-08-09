# Forex Signal Intelligence

Production-oriented Forex market intelligence, anticipation, risk validation, and controlled MT5 execution platform.

## Current status

**Phase 2 — real market-data adapter foundation and multi-factor H4/H1/M15 regime engine.**

Default execution mode remains `ANALYSIS_ONLY`. Phase 2 is read-only: it can retrieve market data and classify regimes, but it cannot submit broker orders.

## Architecture

```text
Market Data Provider ──┐
                       ├─> Regime Engine ─> Strategy Engine ─> Signal ─> Risk/Execution Gate ─> Broker Adapter
News Provider ─────────┘                                                               │
                                                                                       └─> MT5 / Exness Demo
```

The analysis engine is broker-independent. MT5/Exness remains an adapter concern.

## Phase 2 data path

```text
MT5 Terminal
  -> MT5MarketDataProvider (read-only)
  -> MarketSnapshot
  -> closed-bar normalization
  -> RegimeEngine
  -> RegimeAssessment
```

The MT5 Python integration supports position-based bar retrieval. The implementation normalizes returned bars chronologically and excludes the still-forming bar from regime calculations. If the provider is unavailable or history is insufficient, the regime is `UNTRADEABLE` rather than inferred from missing data.

## Regime engine

The initial classifier combines:

- EMA(20) / EMA(50) separation normalized by ATR
- ATR(14) volatility
- ADX(14) trend strength
- 20-bar price slope
- 20-bar dispersion relative to ATR
- recent range width

Supported classifications:

`STRONG_TREND_UP`, `TREND_UP`, `RANGE`, `TRANSITION`, `TREND_DOWN`, `STRONG_TREND_DOWN`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `UNTRADEABLE`.

## Data quality

Snapshots explicitly identify `REAL`, `HISTORICAL`, `SIMULATED`, or `UNAVAILABLE`. Live-data failure is never silently replaced with simulated data.

## External provider abstraction

MT5 is the initial operational market-data source because it is also the planned execution target. Twelve Data remains an external-provider candidate; provider selection will be finalized after measuring symbol coverage, quotas, latency, and operational requirements.

## Execution modes

- `ANALYSIS_ONLY` — default; no orders.
- `DEMO_PAPER` — paper execution only; no broker orders.
- `DEMO_EXECUTION` — broker execution permitted only when explicitly enabled and configured for demo.
- `LIVE_DISABLED` — live execution remains disabled.

## Security

Credentials are runtime configuration only. Never commit `.env`, passwords, API keys, or Telegram tokens.

## Development

```bash
python -m pip install -e '.[test]'
pytest
```

## Safety status

Phase 2 contains **no order-placement implementation**. No Exness account is connected by this phase, and no live execution path exists.
