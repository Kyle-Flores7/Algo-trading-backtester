"""
STRATEGY: RSI Mean Reversion
=============================

Concept:
RSI (Relative Strength Index) measures how "overbought" or "oversold" a stock
is, on a scale of 0-100, based on recent price momentum.

- When RSI drops very low (typically below 30) — the stock has dropped a lot
  recently, so it's considered "oversold," and the bet is that it's due to
  bounce back up -> BUY signal

- When RSI climbs very high (typically above 70) — "overbought," the bet is
  it's due to pull back -> SELL signal

This is philosophically the opposite of the SMA crossover strategy. Crossover
strategies bet trends continue. Mean-reversion bets extremes snap back.
Trending markets tend to favor crossovers; choppy/sideways markets tend to
favor mean-reversion.
"""

import yfinance as yf
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest import run_backtest

ticker = "SPY"
data = yf.download(ticker, period="10y")

# Flatten multi-level columns from yfinance (e.g. "Close"/"SPY" stacked)
data.columns = data.columns.get_level_values(0)

# --- Calculate RSI ---
# delta = day-to-day price change
delta = data["Close"].diff()

# gain = only the up days (down days become 0)
gain = delta.where(delta > 0, 0)

# loss = only the down days, flipped positive (up days become 0)
loss = -delta.where(delta < 0, 0)

# 14-day rolling averages of gains/losses (the standard RSI period)
avg_gain = gain.rolling(window=14).mean()
avg_loss = loss.rolling(window=14).mean()

# rs = ratio of average gains to average losses
rs = avg_gain / avg_loss

# Convert that ratio into the standard 0-100 RSI scale
data["RSI"] = 100 - (100 / (1 + rs))

# --- Generate Signals ---
# Signal = 1 (buy) when RSI is oversold (below 30)
# Signal = -1 (sell) when RSI is overbought (above 70)
# Signal = 0 otherwise (no strong signal, stay out / hold)
data["Signal"] = 0
data.loc[data["RSI"] < 30, "Signal"] = 1
data.loc[data["RSI"] > 70, "Signal"] = -1

print(data[["Close", "RSI"]].tail(15))

results = run_backtest(data, strategy_name="RSI Mean-Reversion (14)")