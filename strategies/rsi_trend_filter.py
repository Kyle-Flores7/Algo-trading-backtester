"""
STRATEGY: RSI Mean-Reversion + Trend Filter (Hybrid)
=======================================================

Concept:
This combines two things we've already tested separately:

1. RSI Mean-Reversion (25/75) - our safest, most consistent strategy across
   SPY, QQQ, and AAPL (best drawdown control every time)
2. A 200-day SMA trend filter - a classic "is this a bull or bear regime"
   marker

THE HYPOTHESIS:
On AAPL, pure RSI mean-reversion underperformed trend-following strategies
(MACD, Breakout) because AAPL had strong, sustained uptrends - and RSI kept
betting AGAINST those trends every time price got "overbought." This hybrid
only takes RSI's buy signals when price is ABOVE the 200-day SMA (buying
dips within an established uptrend, not catching a falling knife in a
downtrend), and only takes sell signals when price is BELOW the 200-day SMA.

In other words: use RSI to time entries, but let the long-term trend decide
which direction is even allowed.

If this improves on plain RSI (especially on trending stocks like AAPL),
that's real evidence combining ideas beats using either alone.

RESULTS - THE HYPOTHESIS WAS WRONG (or at least this version was):

  SPY:  Plain RSI +34.72% / -10.51% DD  ->  Hybrid -9.26% / -9.63% DD
  AAPL: Plain RSI +43.70% / -28.69% DD  ->  Hybrid  +3.48% / -19.24% DD

On BOTH tickers, the hybrid reduced drawdown somewhat, but return collapsed
far more than the risk reduction justified. The filter was too restrictive:
requiring BOTH "RSI extreme" AND "trend agrees" at the same time cut out far
more good trades than bad ones, leaving the strategy mostly sitting flat.

WHY THIS IS STILL VALUABLE:
This disproves an intuitive-sounding idea with real evidence rather than
assumption - a good reminder that "this should logically work better" is
not the same as "this tested better." Backtesting exists exactly to catch
cases like this before risking real money on a plausible-sounding idea.

NEXT IDEAS TO TRY (not yet tested):
  - A shorter/looser trend filter (e.g. 50-day SMA instead of 200-day),
    so it reacts faster and filters less aggressively
  - Only filtering SELL signals against the trend, not both directions
  - Requiring trend agreement as a "tiebreaker" rather than a hard gate
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
# Otherwise: no signal (stay flat) - this filters out counter-trend bets
data["Signal"] = 0
data.loc[(data["RSI"] < 25) & (data["Uptrend"] == True), "Signal"] = 1
data.loc[(data["RSI"] > 75) & (data["Uptrend"] == False), "Signal"] = -1

print(data[["Close", "RSI", "SMA_200", "Uptrend", "Signal"]].tail(15))

# --- Backtest Performance (shared helper) ---
results = run_backtest(data, strategy_name="RSI + Trend Filter (Hybrid)")