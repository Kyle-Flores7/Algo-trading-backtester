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

(See `results/*.txt` for saved per-ticker runs on SPY, QQQ, AAPL, and TSLA. Return/buy-hold figures shift slightly between runs since `yfinance` pulls a rolling 10y window from "today.")

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

## Full strategy comparison on TSLA (10y)

Added TSLA as a fourth ticker specifically because it's far more volatile than SPY/QQQ/AAPL — a stress test for the "RSI wins on individual/trending stocks, Bollinger Bands wins on broad indexes" pattern.

| Strategy | Return | Buy & Hold | Max Drawdown |
|---|---|---|---|
| SMA Crossover (20/50) | -64.83% | +2351.79% | -87.32% |
| RSI Mean-Reversion (25/75) | -92.09% | +2351.79% | -94.94% |
| Breakout (20-day) | -12.44% | +2351.79% | -86.85% |
| MACD (12/26/9) | +639.99% | +2351.79% | -72.78% |
| Bollinger Bands (20, 2std) | -87.10% | +2351.79% | -91.69% |

**The pattern breaks completely on TSLA.** Every mean-reversion strategy (RSI, Bollinger Bands) is a near-total loss here — RSI mean-reversion is the single worst result seen in any comparison so far (-92.09% return, -94.94% max drawdown), and Bollinger Bands isn't far behind (-87.10%). The only strategy that survives is MACD, a trend-following strategy, which turns in the best result of any strategy/ticker combination tested to date (+639.99%).

The likely explanation: TSLA's 10y buy-and-hold return is +2351.79% (vs. roughly 300% for SPY over the same window) — this is a stock defined by sustained, multi-year trends punctuated by sharp pullbacks, not mean-reverting chop. Mean-reversion strategies interpret those pullbacks as "buy the dip" and repeatedly buy into corrections within a structural trend, compounding losses. A trend-following strategy (MACD) instead rides the trend and avoids fighting it.

**Revised takeaway**: "RSI wins on individual/trending stocks" was really "RSI wins on individual stocks with *moderate* trends" (AAPL). It does not generalize to a stock with TSLA's degree of volatility and sustained directional momentum — there, trend-following (MACD) dominates and mean-reversion is actively dangerous. Ticker-specific volatility/trend character matters more than "index vs. single stock" as the deciding factor.

## Running conclusion as of last test

No single strategy tested so far wins on every ticker. RSI mean-reversion (25/75, 14-day) is the most *consistent* performer across SPY, QQQ, and AAPL (positive return and controlled drawdown on all three), and Bollinger Bands (20, 2std) outperforms it on SPY and QQQ specifically but underperforms on AAPL — however, TSLA breaks both: RSI and Bollinger Bands are the two worst results seen in any test to date, while MACD (previously a weak/negative performer on SPY) produces the best result of any strategy/ticker pair. Strategy choice should be conditioned on the ticker's trend/volatility character, not treated as a fixed ranking — this reflects the specific tickers/period tested.
