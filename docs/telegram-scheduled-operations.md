# Telegram Scheduled Operations

## Runtime model

The scheduled workflow is designed for a **self-hosted Windows GitHub Actions runner** labeled `mt5`. The runner must have the MetaTrader 5 desktop terminal installed and connected to the intended Exness account. The workflow reads market data only; it never submits broker orders.

```text
GitHub schedule
      -> Windows self-hosted runner
      -> MT5 terminal (read-only market data)
      -> H4 / H1 / M15
      -> Regime / Strategy / Anticipation / Risk
      -> Telegram
      -> Manual execution in Exness MT5 iOS
```

## GitHub configuration

Create these **Actions secrets** in the repository:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional repository variables:

- `FOREX_SYMBOL` (default: `EURUSD`)
- `MT5_TERMINAL_PATH` (only if the terminal is not discoverable by the MetaTrader5 package)

Do not commit Telegram credentials or Exness credentials to Git.

## Windows runner requirements

The runner must be online when scheduled jobs execute and must have:

1. Windows.
2. MetaTrader 5 desktop installed.
3. The intended Exness account already logged in to MT5.
4. GitHub Actions runner labels: `self-hosted`, `windows`, `mt5`.
5. Python 3.11+ available (the workflow also installs the requested Python version).

## Trigger safety

`TRIGGER_CONFIRMED` is intentionally `false` in the scheduled workflow. The pipeline must not convert an anticipation/READY state into a trade signal merely because the price is inside an entry zone. An explicit trigger detector must establish the confirmation before an alert is sent.

This prevents the scheduler from turning a watch/anticipation into an automatic trade recommendation without the strategy's trigger condition being satisfied.

## Schedule

The workflow runs every 15 minutes and can also be started manually with **Run workflow**. GitHub Actions schedules are UTC-based.

The workflow is a scheduler/runner, not a replacement for the Windows MT5 terminal. A GitHub-hosted Linux runner cannot access a locally installed MT5 terminal.
