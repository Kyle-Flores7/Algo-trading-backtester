"""
STRATEGY COMPARISON
=====================

Runs every strategy in strategies/ over the same time period and ticker,
then prints a side-by-side comparison table. This is the actual "library"
output - a single place to see how every strategy stacks up against
buy-and-hold and against each other.
"""

import yfinance as yf
from backtest import run_backtest

ticker = "AAPL"
period = "10y"

print(f"Downloading {ticker} data ({period})...\n")
data = yf.download(ticker, period=period)
data.columns = data.columns.get_level_values(0)

results_summary = []

# --- Strategy 1: SMA Crossover ---
sma_data = data.copy()
sma_data["SMA_short"] = sma_data["Close"].rolling(window=20).mean()
sma_data["SMA_long"] = sma_data["Close"].rolling(window=50).mean()
sma_data["Signal"] = 0
sma_data.loc[sma_data["SMA_short"] > sma_data["SMA_long"], "Signal"] = 1
sma_data.loc[sma_data["SMA_short"] < sma_data["SMA_long"], "Signal"] = -1
sma_results = run_backtest(sma_data, strategy_name="SMA Crossover (20/50)")
results_summary.append(("SMA Crossover (20/50)", sma_results))

# --- Strategy 2: RSI Mean-Reversion ---
rsi_data = data.copy()
delta = rsi_data["Close"].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)
avg_gain = gain.rolling(window=14).mean()
avg_loss = loss.rolling(window=14).mean()
rs = avg_gain / avg_loss
rsi_data["RSI"] = 100 - (100 / (1 + rs))
rsi_data["Signal"] = 0
rsi_data.loc[rsi_data["RSI"] < 25, "Signal"] = 1
rsi_data.loc[rsi_data["RSI"] > 75, "Signal"] = -1
rsi_results = run_backtest(rsi_data, strategy_name="RSI Mean-Reversion (25/75 tuned)")
results_summary.append(("RSI Mean-Reversion (25/75)", rsi_results))

# --- Strategy 3: Breakout ---
bo_data = data.copy()
window = 20
bo_data["Rolling_High"] = bo_data["Close"].rolling(window=window).max()
bo_data["Rolling_Low"] = bo_data["Close"].rolling(window=window).min()
bo_data["Signal"] = 0
bo_data.loc[bo_data["Close"] >= bo_data["Rolling_High"], "Signal"] = 1
bo_data.loc[bo_data["Close"] <= bo_data["Rolling_Low"], "Signal"] = -1
bo_data["Signal"] = bo_data["Signal"].replace(0, None).ffill().fillna(0)
bo_results = run_backtest(bo_data, strategy_name="Breakout (20-day)")
results_summary.append(("Breakout (20-day)", bo_results))

# --- Strategy 4: MACD ---
macd_data = data.copy()
ema_fast = macd_data["Close"].ewm(span=12, adjust=False).mean()
ema_slow = macd_data["Close"].ewm(span=26, adjust=False).mean()
macd_data["MACD_Line"] = ema_fast - ema_slow
macd_data["Signal_Line"] = macd_data["MACD_Line"].ewm(span=9, adjust=False).mean()
macd_data["Signal"] = 0
macd_data.loc[macd_data["MACD_Line"] > macd_data["Signal_Line"], "Signal"] = 1
macd_data.loc[macd_data["MACD_Line"] < macd_data["Signal_Line"], "Signal"] = -1
macd_results = run_backtest(macd_data, strategy_name="MACD (12/26/9)")
results_summary.append(("MACD (12/26/9)", macd_results))

# --- Strategy 5: Bollinger Bands ---
bb_data = data.copy()
bb_window = 20
bb_data["Middle_Band"] = bb_data["Close"].rolling(window=bb_window).mean()
bb_data["StdDev"] = bb_data["Close"].rolling(window=bb_window).std()
bb_data["Upper_Band"] = bb_data["Middle_Band"] + (2 * bb_data["StdDev"])
bb_data["Lower_Band"] = bb_data["Middle_Band"] - (2 * bb_data["StdDev"])
bb_data["Signal"] = 0
bb_data.loc[bb_data["Close"] <= bb_data["Lower_Band"], "Signal"] = 1
bb_data.loc[bb_data["Close"] >= bb_data["Upper_Band"], "Signal"] = -1
bb_results = run_backtest(bb_data, strategy_name="Bollinger Bands (20, 2std)")
results_summary.append(("Bollinger Bands (20, 2std)", bb_results))

# --- Print Summary Table ---
print("\n\n========== SUMMARY ==========")
print(f"{'Strategy':<28}{'Return':>12}{'Buy&Hold':>12}{'Max DD':>12}")
for name, r in results_summary:
    print(f"{name:<28}{r['strategy_return']:>11.2%} {r['buyhold_return']:>11.2%} {r['max_drawdown']:>11.2%}")