"""
STRATEGY: RSI Mean-Reversion + Trend Filter (Hybrid)
=======================================================

Concept:
This combines two things we've already tested separately:

1. RSI Mean-Reversion (25/75) - our safest, most consistent strategy across
   SPY, QQQ, and AAPL (best drawdown control every time)
2. A trend filter (SMA-based) - a "is this a bull or bear regime" marker

THE HYPOTHESIS:
On AAPL, pure RSI mean-reversion underperformed trend-following strategies
because AAPL had strong, sustained uptrends - and RSI kept betting AGAINST
those trends every time price got "overbought." The idea: only take RSI
signals that agree with the broader trend.

FOUR VERSIONS TESTED (all on AAPL, 10yr):

  Baseline - Plain RSI, no filter:
    +43.70% return, -28.69% max drawdown   <- STILL THE BEST

  v1 - 200-day SMA filter, BOTH directions gated:
    +3.48% return, -19.24% max drawdown

  v2 - 200-day SMA filter, only BUY side gated:
    +11.49% return, -29.84% max drawdown

  v3 - 50-day SMA filter, BOTH directions gated:
    -0.35% return, -2.62% max drawdown   (best drawdown, but flat return)

CONCLUSION:
Every filtered version underperformed plain RSI on return. Filtering did
sometimes reduce drawdown (v1, v3), but never by enough to justify how much
return it cost - and v2 (filtering only the buy side) actually made
drawdown WORSE while barely improving return. A faster filter (v3, 50-day)
minimized risk almost entirely but essentially killed the strategy's
ability to generate any real return at all.

TAKEAWAY: plain, unfiltered RSI mean-reversion remains the strongest
strategy in this library, across every ticker AND every filtering attempt
tested. This is a genuinely useful finding - it would have been easy to
assume "adding a trend filter should obviously help" and just trade that
belief without testing it. The data says otherwise, at least for this
specific combination of indicators. Not every intuitive improvement is a
real improvement - that's exactly what backtesting is for.

This file keeps the v1 (200-day, both directions gated) version as the
active code below, as a working reference implementation of the hybrid
approach, even though it hasn't beaten the baseline.
"""

import yfinance as yf
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest import run_backtest

ticker = "AAPL"
data = yf.download(ticker, period="10y")

# Flatten multi-level columns from yfinance
data.columns = data.columns.get_level_values(0)

# --- Calculate RSI ---
delta = data["Close"].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)
avg_gain = gain.rolling(window=14).mean()
avg_loss = loss.rolling(window=14).mean()
rs = avg_gain / avg_loss
data["RSI"] = 100 - (100 / (1 + rs))

# --- Calculate Trend Filter (200-day SMA) ---
data["SMA_200"] = data["Close"].rolling(window=200).mean()
data["Uptrend"] = data["Close"] > data["SMA_200"]

# --- Generate Signals ---
# Buy: RSI oversold AND price above 200-day SMA (dip in an uptrend)
# Sell: RSI overbought AND price below 200-day SMA (bounce in a downtrend)
data["Signal"] = 0
data.loc[(data["RSI"] < 25) & (data["Uptrend"] == True), "Signal"] = 1
data.loc[(data["RSI"] > 75) & (data["Uptrend"] == False), "Signal"] = -1

print(data[["Close", "RSI", "SMA_200", "Uptrend", "Signal"]].tail(15))

# --- Backtest Performance (shared helper) ---
results = run_backtest(data, strategy_name="RSI + Trend Filter (Hybrid v1)")