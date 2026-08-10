"""
STRATEGY: SMA Crossover (20/50)
==================================

Concept:
Calculate two moving averages of the closing price - a short-term average
(20 days) and a long-term average (50 days).

- When the short-term average crosses ABOVE the long-term average, that's
  read as a BUY signal (recent momentum is outpacing the longer trend)
- When the short-term average crosses BELOW the long-term average, that's
  read as a SELL signal (momentum turning down)

This is one of the most basic, most widely used trend-following strategies.
It tends to lag - it gets you in and out AFTER a move has already started -
which matters most in choppy markets (whipsaws) and in strong trends
(it gives back the early part of the move).
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

# --- Calculate Moving Averages ---
data["SMA_short"] = data["Close"].rolling(window=20).mean()
data["SMA_long"] = data["Close"].rolling(window=50).mean()

# --- Generate Signals ---
# Signal = 1 (bullish state) when short average is above long average
# Signal = -1 (bearish state) when short average is below long average
data["Signal"] = 0
data.loc[data["SMA_short"] > data["SMA_long"], "Signal"] = 1
data.loc[data["SMA_short"] < data["SMA_long"], "Signal"] = -1

# --- Find Crossover Moments ---
# Position tracks where Signal actually CHANGES - these are the real
# buy/sell trade triggers, not just the ongoing state
data["Position"] = data["Signal"].diff()
crossovers = data[data["Position"] != 0]
print(crossovers[["Close", "SMA_short", "SMA_long", "Signal", "Position"]])

# --- Backtest Performance (shared helper) ---
results = run_backtest(data, strategy_name="SMA Crossover (20/50)")