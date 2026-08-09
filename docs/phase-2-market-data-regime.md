# Phase 2 — Market Data and Regime Engine

## Data path

```text
MT5 Terminal
  -> MT5MarketDataProvider (read-only)
  -> MarketSnapshot
  -> closed-bar normalization
  -> RegimeEngine
  -> RegimeAssessment
```

The provider is intentionally read-only. It does not import or call any order-placement API. Execution remains a separate future adapter.

## Data quality

Every snapshot carries one of `REAL`, `HISTORICAL`, `SIMULATED`, or `UNAVAILABLE`. Missing live data is never converted into simulated data.

For MT5 position-based history requests, the forming bar is excluded from regime calculations. This avoids making a regime decision from an unfinished candle.

## Regime evidence

The classifier combines:

- EMA(20) vs EMA(50) separation normalized by ATR
- ATR(14) and ATR/price volatility
- ADX(14) trend strength
- 20-bar price slope
- 20-bar dispersion relative to ATR
- recent range width

The result is one of the canonical regimes already defined in Phase 1.

## Safety behavior

- unavailable data -> `UNTRADEABLE`
- insufficient closed bars -> `UNTRADEABLE`
- no broker connection is required for CI
- the MT5 adapter is read-only in this phase
- no Telegram notification is emitted by Phase 2
- no order can be submitted by Phase 2

## Provider decision

MT5 remains the first operational data source because the execution target is MT5 and the official Python integration exposes bar retrieval. An external provider remains an abstraction point. Twelve Data is retained as a candidate external source; it documents real-time/historical Forex data and intraday time-series support. Provider selection should be revisited when Phase 2 is connected to a real environment and latency/coverage/quotas can be measured.
