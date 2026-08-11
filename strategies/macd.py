"""
STRATEGY: MACD (Moving Average Convergence Divergence)
==========================================================

Concept:
MACD tracks the relationship between two exponential moving averages (EMAs)
of price - a fast one and a slow one - rather than comparing price directly
to a single average.

- MACD Line = 12-day EMA minus 26-day EMA
- Signal Line = 9-day EMA of the MACD Line itself

- When MACD Line crosses ABOVE the Signal Line -> momentum is accelerating
  upward -> BUY signal
- When MACD Line crosses BELOW the Signal Line -> momentum is decelerating
  or turning down -> SELL signal

Unlike SMA crossover (price vs. average) or RSI (bounded 0-100 oscillator),
MACD is tracking the RATE OF CHANGE of momentum itself. EMAs also react
faster to recent price changes than SMAs, since they weight recent prices
more heavily.

RESULTS (SPY, 10yr): -5.98% return, -38.28% max drawdown - the WORST
performer of the 4 strategies tested so far.

LIBRARY-WIDE PATTERN (4 strategies tested):
  - SMA Crossover (trend-following, lagging):    +15.73%, -37.87% DD
  - RSI Mean-Reversion (reversal, tuned 25/75):  +34.72%, -10.51% DD  <- BEST
  - Breakout (trend-following, momentum entry):  +18.32%, -28.53% DD
  - MACD (trend-following, fast-reacting):       -5.98%,  -38.28% DD

Both trend-following strategies tested here (SMA and MACD) underperformed
the one reversal-based strategy (RSI), regardless of whether the
trend-following approach was slow (SMA) or fast-reacting (MACD). This
suggests that in this specific market period, betting on price reverting
to the mean has genuinely outperformed betting on trend continuation -
not just a quirk of one particular strategy's parameters.
"""

import yfinance as yf
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest import run_backtest

ticker = "SPY"
data = yf.download(ticker, period="10y")

# Flatten multi-level columns from yfinance
data.columns = data.columns.get_level_values(0)

# --- Calculate MACD ---
ema_fast = data["Close"].ewm(span=12, adjust=False).mean()
ema_slow = data["Close"].ewm(span=26, adjust=False).mean()

data["MACD_Line"] = ema_fast - ema_slow
data["Signal_Line"] = data["MACD_Line"].ewm(span=9, adjust=False).mean()

# --- Generate Signals ---
# Signal = 1 (buy) when MACD Line is above Signal Line (bullish momentum)
# Signal = -1 (sell) when MACD Line is below Signal Line (bearish momentum)
data["Signal"] = 0
data.loc[data["MACD_Line"] > data["Signal_Line"], "Signal"] = 1
data.loc[data["MACD_Line"] < data["Signal_Line"], "Signal"] = -1

# --- Backtest Performance (shared helper) ---
results = run_backtest(data, strategy_name="MACD (12/26/9)")

print(data[["Close", "MACD_Line", "Signal_Line"]].tail(15))