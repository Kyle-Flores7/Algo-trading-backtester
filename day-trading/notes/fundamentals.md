# Day Trading Fundamentals

Notes on day trading / futures concepts, built alongside the swing-trading
strategy library. This is a separate track - different data (intraday, not
daily), different mechanics (futures, not stocks), different timeframe.

Goal: understand the fundamentals thoroughly before writing any code, same
discipline used for the swing-trading strategies - concept first, then code.

---

## Futures Contracts - The Basics

A futures contract is an agreement to buy or sell a specific asset at a
specific price on a specific future date. Day trading futures means buying
and selling the CONTRACT ITSELF for its price movement - not planning to
hold to expiration or take delivery of anything.

### What makes futures different from stocks

**1. Leverage is built in, not optional**
You only put up a fraction of the contract's total value, called MARGIN.
A relatively small move in the underlying index represents a much larger
percentage move relative to actual capital at risk. Cuts both ways - can
generate meaningful income on a smaller account, but risk scales the same way.

**2. Contract specs stocks don't have**
- Tick size: smallest price increment the contract can move
  (NQ = 0.25 points)
- Tick value: dollar amount one tick is worth
  (NQ = $5/tick, MNQ (Micro) = $0.50/tick)
- Expiration: contracts expire and roll over periodically (quarterly),
  unlike a stock held indefinitely

**3. Micro contracts exist for smaller accounts**
NQ (full-size) requires substantial margin. MNQ (Micro NQ) is 1/10th the
size, same underlying index, dramatically lower capital requirement per
trade. Realistic starting point given account size, not full-size NQ.

---

## Session Timing & Opening Range

Unlike swing trading (where only the daily close mattered), day trading is
built around SPECIFIC WINDOWS of the day where volume and volatility are
highest - because that's where the most opportunity (and risk) exists.

### Key session: New York open, 9:30 AM ET

Why this time matters so much for US index futures like NQ:
- This is when the stock market itself opens (NQ tracks the Nasdaq-100)
- The first 15-30 minutes after 9:30 AM sees a massive spike in volume and
  volatility - overnight news, pre-market positioning, and the broader
  trading population all converge at once

### Opening Range Breakout (ORB)

The simplest, most well-documented day trading strategy - a good starting
point, similar in spirit to SMA Crossover being the simplest swing strategy.

- Mark the high and low of price during a defined window after the open
  (commonly the first 5, 15, or 30 minutes - e.g. 9:30-9:45 AM)
- If price breaks ABOVE that range's high afterward -> often read as a
  bullish continuation signal
- If price breaks BELOW that range's low -> bearish signal

---

## Liquidity & Liquidity Sweeps

"Liquidity" here does NOT mean how easy a stock is to buy/sell (the normal
definition). In day trading terminology, it refers to clusters of pending
orders sitting at specific price levels - most commonly STOP-LOSS orders
resting just above recent highs or just below recent lows.

### Why it matters

Traders who bought near a recent low often place a stop-loss just below it
(a common, near-universal habit). That creates a cluster of sell orders
sitting right below that low. Price will sometimes push just far enough to
trigger that cluster of stops (forcing those traders out at a loss) before
reversing back in the original direction.

### Liquidity Sweep

Price breaks a recent high or low - looking like a real breakout - triggers
the resting stop orders sitting there, then reverses. Retail traders who
read the break as "the real move" often get caught buying/selling right
before the reversal.

### Connection to ORB

A more refined version of ORB doesn't just trade the first breakout of the
opening range blindly - it watches for a SWEEP of the opening range high/low
(price breaks it, then reverses back inside) as a stronger signal than a
clean breakout, since it suggests the "obvious" traders just got trapped.

**Honest caveat:** this is a real, documented phenomenon, not nonsense - but
it's genuinely hard to code into precise, testable rules. "Did price sweep
liquidity or just legitimately break out" often requires judgment that's
harder to define than something like "RSI < 25." Will need to be dealt with
honestly when actually building this, not assumed to be as clean as the
swing strategies were.

---

## Next up: candlestick basics, then shaping the first ORB strategy

## Data Reality Check

ORB needs INTRADAY data (minute-by-minute), not the daily data used
everywhere in strategies/. This is a genuinely new technical requirement.

- yfinance can pull intraday data, but only recent history (~60 days for
  1-minute candles) - nowhere near the 10yr depth used for daily strategies
- Real historical NQ/MNQ minute data typically requires a paid provider
- Plan: build and prove the ORB logic on QQQ intraday data first (free,
  highly correlated with NQ), then solve real futures data sourcing once
  the strategy logic itself is confirmed working

## Next session: build day-trading/data/pull_intraday.py to pull QQQ
## 1-minute data and confirm we can identify the opening range correctly