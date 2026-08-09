# Telegram Final Output

The production signal path ends at Telegram. The system does not place broker orders.

`Market data → regime → strategy selection → anticipation → trigger → risk validation → Telegram`

The user manually executes approved BUY/SELL signals in Exness MT5 on iOS.

## Runtime secrets

Set these only in the runtime environment:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Do not commit real values to GitHub.

## Alert contract

Every trade alert contains:

- pair
- BUY/SELL direction
- status
- strategy
- market regime
- entry
- stop loss
- take profit
- risk/reward
- risk
- score
- confidence
- timeframes
- evidence
- trigger
- invalidation
- expiry

`NO_TRADE` is not sent as a trade alert.

The message explicitly identifies execution as `MANUAL — Exness MT5` so there is no ambiguity that the system is not placing the order.
