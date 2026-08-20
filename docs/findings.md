# Findings

Historical backtest results and tuning conclusions, moved out of CLAUDE.md so they don't consume context every session. Detailed reasoning for each strategy also lives in that strategy's own docstring in `strategies/*.py`.

## Strategy comparison (10y backtests)

| Strategy | Ticker | Return | Buy & Hold | Max Drawdown |
|---|---|---|---|---|
| SMA Crossover (20/50) | SPY | +15.73% | +314.09% | -46.69% |
| RSI Mean-Reversion (25/75) | SPY | +34.72% | +314.09% | -10.51% |
| Breakout (20-day) | SPY | +18.32% | +314.09% | -28.53% |
| MACD (12/26/9) | SPY | -5.98% | +314.09% | -38.28% |

(See `results/*.txt` for saved per-ticker runs on SPY, QQQ, and AAPL.)

## RSI mean-reversion threshold tuning (SPY, 10y)

- 30/70 (textbook default): +30.27% return, -13.09% max drawdown
- 25/75 (tighter): +34.72% return, -10.51% max drawdown — best so far
- 20/80 (very tight): +15.00% return, -12.43% max drawdown

Tighter thresholds helped up to a point (25/75), but going further (20/80) hurt both return and drawdown — too selective to catch enough trades.

## RSI + trend filter hybrid (AAPL, 10y)

Hypothesis: gating RSI signals with a trend filter (only take dip-buys in an uptrend, etc.) should help on trending tickers like AAPL.

- Baseline, plain RSI: +43.70% return, -28.69% max drawdown — best return
- v1, 200-day SMA filter (both directions gated): +3.48%, -19.24%
- v2, 200-day SMA filter (buy side only): +11.49%, -29.84% (worse drawdown than baseline)
- v3, 50-day SMA filter (both directions gated): -0.35%, -2.62% (best drawdown, ~flat return)

**Conclusion**: every filtered version underperformed plain RSI on return; drawdown reduction never justified the return given up. Hypothesis disproven — trend filtering was not a free improvement.

## Running conclusion as of last test

Plain, unfiltered RSI mean-reversion (25/75, 14-day) has been the most consistent risk-adjusted performer across SPY, QQQ, and AAPL, outperforming every trend-following strategy (SMA, Breakout, MACD) and every hybrid filter tested so far. Treat this as the baseline to beat in future strategy work, not a permanent conclusion — it reflects the specific tickers/period tested.
