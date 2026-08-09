# Forex Signal Intelligence

Production-oriented Forex market intelligence, anticipation, risk validation, and controlled MT5 execution platform.

## Current status

**Phase 1 — architecture, data models, configuration, and provider interfaces.**

Default execution mode is `ANALYSIS_ONLY`. No broker order can be submitted by this phase.

## Architecture

```text
Market Data Provider ──┐
                       ├─> Analysis Layer ─> Signal Contract ─> Risk/Execution Gate ─> Broker Adapter
News Provider ─────────┘                                                        │
                                                                                └─> MT5 / Exness Demo
```

The analysis layer is broker-independent. MT5/Exness is an adapter concern.

## Execution modes

- `ANALYSIS_ONLY` — default; no orders.
- `DEMO_PAPER` — paper execution only; no broker orders.
- `DEMO_EXECUTION` — broker execution permitted only when `EXECUTION_ENABLED=true` and a demo account is deliberately configured.
- `LIVE_DISABLED` — reserved safety state; live execution is not implemented/enabled.

## Security

Credentials are runtime configuration only. Do not commit `.env`, passwords, API keys, or Telegram tokens. Use GitHub/host secret stores as appropriate.

## Market data decision

The provider interface deliberately separates market data from execution. MT5 is the initial broker/execution target. A dedicated market-data adapter can use MT5 terminal data or an external provider without changing strategy code.

Twelve Data is a viable external-provider candidate because its current Forex offering exposes real-time and historical FX data, 1-minute through 8-hour intraday intervals, and a WebSocket interface. Provider selection will be finalized during Phase 2 after testing coverage, quotas, latency, symbol mapping, and licensing requirements.

## Development

```bash
python -m pip install -e '.[test]'
pytest
```

The official MetaTrader 5 Python integration exposes terminal initialization/login, account information, symbol specifications, tick data, rates, positions, history, and order submission. The execution adapter will therefore run where the MetaTrader 5 terminal is available; the strategy engine remains broker-independent.
