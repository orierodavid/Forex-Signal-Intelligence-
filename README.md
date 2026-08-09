# Forex Signal Intelligence

Production-oriented Forex market intelligence, anticipation, risk validation, and controlled MT5 execution platform.

## Current status

**Phase 3 — modular strategy framework and initial seven regime-aware strategy families.**

Default execution mode remains `ANALYSIS_ONLY`. Phase 3 is analysis-only: strategies detect and rank candidates, but cannot submit broker orders.

## Architecture

```text
Market Data Provider ──┐
                       ├─> Regime Engine ─> Strategy Engine ─> Signal ─> Risk/Execution Gate ─> Broker Adapter
News Provider ─────────┘                                                               │
                                                                                       └─> MT5 / Exness Demo
```

The analysis engine is broker-independent. MT5/Exness remains an adapter concern.

## Phase 3 strategy framework

Every strategy receives a `StrategyContext` and returns a deterministic `StrategyResult`. A result is a candidate, not an executable trade. The selector only chooses candidates that meet the configured score threshold and suppresses close-scored opposing candidates rather than manufacturing directional certainty.

Initial strategy families:

1. `TREND_PULLBACK`
2. `BREAKOUT_RETEST`
3. `LIQUIDITY_SWEEP_REVERSAL`
4. `RANGE_BREAKOUT`
5. `SUPPORT_RESISTANCE_REJECTION`
6. `MOMENTUM_CONTINUATION`
7. `MEAN_REVERSION`

Each family declares compatible market regimes and produces:

- direction
- score
- eligibility
- trigger
- invalidation
- evidence
- strategy metadata

## Strategy selection

The default minimum candidate score is `70/100`.

The selector:

- evaluates every configured strategy
- excludes strategies incompatible with the current regime
- ranks eligible candidates deterministically
- rejects low-score candidates
- rejects materially ambiguous opposing candidates
- returns `NO_TRADE` when no candidate is sufficiently qualified

This layer does not calculate broker position size and does not place orders.

## Phase 2 data path

```text
MT5 Terminal
  -> MT5MarketDataProvider (read-only)
  -> MarketSnapshot
  -> closed-bar normalization
  -> RegimeEngine
  -> RegimeAssessment
  -> StrategySelector
  -> StrategyResult
```

The MT5 Python integration supports position-based bar retrieval. The implementation normalizes returned bars chronologically and excludes the still-forming bar from regime calculations. If the provider is unavailable or history is insufficient, the regime is `UNTRADEABLE` rather than inferred from missing data.

## Regime engine

The classifier combines:

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

Phase 3 contains **no order-placement implementation**. No Exness account is connected by this phase, and no live execution path exists.
