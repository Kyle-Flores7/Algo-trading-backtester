"""
STRATEGY: Bollinger Bands Mean-Reversion
===========================================

Concept:
Bollinger Bands measure volatility, not just momentum (unlike RSI). They're
built from:

- Middle Band = 20-day SMA of price
- Upper Band  = Middle Band + (2 x standard deviation of recent price)
- Lower Band  = Middle Band - (2 x standard deviation of recent price)

The bands widen when volatility is high and narrow when it's low - they
adapt to current market conditions rather than using a fixed scale.

- When price touches or drops BELOW the lower band -> considered unusually
  cheap relative to its own recent volatility -> BUY signal
- When price touches or rises ABOVE the upper band -> considered unusually
  expensive -> SELL signal

This is philosophically similar to RSI (both are mean-reversion ideas), but
the mechanism differs: RSI measures momentum on a fixed 0-100 scale,
Bollinger Bands measure price relative to ITS OWN recent volatility. Worth
testing whether a volatility-based signal behaves differently than a
momentum-based one, especially given plain RSI has been undefeated so far
across every strategy and filter we've tested.
"""

import yfinance as yf
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest import run_backtest

tickers = ["SPY", "QQQ", "AAPL"]

for ticker in tickers:
    data = yf.download(ticker, period="10y")

    # Flatten multi-level columns from yfinance
    data.columns = data.columns.get_level_values(0)

    # --- Calculate Bollinger Bands ---
    window = 20
    data["Middle_Band"] = data["Close"].rolling(window=window).mean()
    data["StdDev"] = data["Close"].rolling(window=window).std()
    data["Upper_Band"] = data["Middle_Band"] + (2 * data["StdDev"])
    data["Lower_Band"] = data["Middle_Band"] - (2 * data["StdDev"])

    # --- Generate Signals ---
    # Buy: price drops below (or touches) the lower band
    # Sell: price rises above (or touches) the upper band
    data["Signal"] = 0
    data.loc[data["Close"] <= data["Lower_Band"], "Signal"] = 1
    data.loc[data["Close"] >= data["Upper_Band"], "Signal"] = -1

    print(f"\n=== {ticker} ===")
    print(data[["Close", "Lower_Band", "Middle_Band", "Upper_Band", "Signal"]].tail(15))

    # --- Backtest Performance (shared helper) ---
    results = run_backtest(data, strategy_name=f"Bollinger Bands (20, 2std) - {ticker}")