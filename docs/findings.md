# Findings

Historical backtest results and tuning conclusions, moved out of CLAUDE.md so they don't consume context every session. Detailed reasoning for each strategy also lives in that strategy's own docstring in `strategies/*.py`.

## Strategy comparison (10y backtests)

| Strategy | Ticker | Return | Buy & Hold | Max Drawdown |
|---|---|---|---|---|
| SMA Crossover (20/50) | SPY | +13.93% | +310.26% | -46.69% |
| RSI Mean-Reversion (25/75) | SPY | +34.40% | +310.26% | -10.51% |
| Breakout (20-day) | SPY | +17.85% | +310.26% | -28.53% |
| MACD (12/26/9) | SPY | -5.99% | +310.26% | -38.28% |
| Bollinger Bands (20, 2std) | SPY | +70.49% | +310.26% | -8.53% |

(See `results/*.txt` for saved per-ticker runs on SPY, QQQ, and AAPL. Return/buy-hold figures shift slightly between runs since `yfinance` pulls a rolling 10y window from "today.")

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

## Bollinger Bands (20, 2std) across tickers

Added as a second mean-reversion strategy — same "bet on a snap-back" philosophy as RSI, but measuring price against its own recent volatility (bands) instead of a fixed 0-100 momentum scale (RSI).

- SPY: +70.49% return, -8.53% max drawdown — beats RSI on both return and drawdown
- QQQ: +64.71% return, -13.25% max drawdown — beats RSI on return, slightly worse drawdown
- AAPL: -8.81% return, -23.64% max drawdown — underperforms RSI (+41.27%) on this ticker

**Takeaway**: Bollinger Bands outperformed RSI mean-reversion on the two broad-index ETFs (SPY, QQQ) by a wide margin on return, but lost money on AAPL where RSI stayed solidly positive. This mirrors the earlier pattern seen with trend-following strategies on AAPL — a single stock with strong sustained trends behaves differently than diversified index ETFs, so no strategy tested so far wins across all three tickers. Worth treating per-ticker performance, not just an aggregate winner, as the more honest way to compare strategies going forward.

## Running conclusion as of last test

No single strategy tested so far wins on every ticker. RSI mean-reversion (25/75, 14-day) remains the most *consistent* performer across SPY, QQQ, and AAPL (positive return and controlled drawdown on all three). Bollinger Bands (20, 2std) now outperforms it on SPY and QQQ specifically, but underperforms on AAPL. Treat both as current baselines to beat, not a permanent conclusion — this reflects the specific tickers/period tested.
