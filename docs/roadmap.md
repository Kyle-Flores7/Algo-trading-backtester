# Roadmap

## Current stage: strategy research / backtesting

Building and comparing individual technical-analysis strategies (SMA crossover, RSI mean-reversion, breakout, MACD, Bollinger Bands, RSI+trend hybrids) against historical data. No automation, no order execution.

## Next: better metrics, testing, risk management

- Stronger backtest metrics (e.g. Sharpe ratio, win rate, exposure time) beyond return/buy-hold/max drawdown
- Automated/regression tests for indicator math and `run_backtest()`
- A defined risk-management approach (see `risk-management.md` — not yet implemented)

## Later: paper trading

Simulated live trading against real-time or near-real-time data, no real money involved, to validate a strategy's behavior outside of historical backtests.

## Eventually: live / funded trading

Only after a strategy has cleared backtesting, testing, risk management, and a paper-trading validation period. Not scoped or scheduled yet.

---

`future-strategies/crt-notes.md` documents a separate, deferred idea (a discretionary futures strategy) that is explicitly out of scope until the stock strategy library and fundamentals above are solid.
