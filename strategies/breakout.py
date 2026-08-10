"""
STRATEGY: Breakout (Donchian Channel style)
=============================================

Concept:
Instead of following a lagging average or betting on reversal, a breakout
strategy watches for NEW highs and lows over a recent window.

- When price closes at its highest point in the last N days -> that's read
  as real strength, momentum likely continues -> BUY signal
- When price closes at its lowest point in the last N days -> that's read
  as breakdown, momentum likely continues downward -> SELL signal

This is built specifically for trending markets - it buys strength directly,
rather than lagging behind it (like SMA) or fighting against it (like RSI
mean-reversion).
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

# Lookback window for defining a "new high" or "new low"
window = 20

# Rolling highest high and lowest low over the window
data["Rolling_High"] = data["Close"].rolling(window=window).max()
data["Rolling_Low"] = data["Close"].rolling(window=window).min()

# --- Generate Signals ---
# Signal = 1 (buy) when price closes at a new rolling high (breakout up)
# Signal = -1 (sell) when price closes at a new rolling low (breakdown)
# Otherwise, hold whatever the previous signal was (stay in the trend)
data["Signal"] = 0
data.loc[data["Close"] >= data["Rolling_High"], "Signal"] = 1
data.loc[data["Close"] <= data["Rolling_Low"], "Signal"] = -1

# Carry forward the last signal on days with no new breakout
data["Signal"] = data["Signal"].replace(0, None).ffill().fillna(0)

# --- Backtest Performance (shared helper) ---
results = run_backtest(data, strategy_name="Breakout (20-day)")
