# CRT (Candle Range Theory) — Future Strategy Notes

**Status:** Deferred to Phase 2 (after stock strategy library + fundamentals are solid)

## Why deferred
- Involves NQ futures (leverage, different risk profile than stocks)
- Discretionary/subjective setup (liquidity sweeps, HTF bias) — harder to code into clean rules than SMA-style strategies
- Targets the 8:30am NY open session — a fast, competitive window, not beginner territory

## Planned build sequence (from external research, saved for reference)
1. CRT Scanner — detect and flag setups, no trading
2. Backtesting Engine — run against historical data, calculate win rate/expectancy/drawdown
3. Trading Assistant — bot suggests trades, human decides
4. Paper-Trading Bot — fully automated on simulated money
5. Automated Trading — only after V4 proves consistent

## Core CRT logic (rough)
Previous candle establishes range → current candle sweeps high/low → closes back inside range → determine bullish/bearish bias → target opposite liquidity.

## Risk framework to apply when built
- Risk per trade: 0.25–0.5% of account
- Max 2-3 trades/day
- Hard daily loss limit: ~1–1.5%
- No size increases after a loss, no revenge trading

## Validation bar before considering funded/live
- 50-100 backtested historical setups minimum
- 2-3 consecutive profitable paper-trading months
- Controlled drawdown, very few rule violations