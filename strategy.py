import yfinance as yf
import matplotlib.pyplot as plt

ticker = "SPY"
data = yf.download(ticker, period="10y")

data["SMA_short"] = data["Close"].rolling(window=20).mean()
data["SMA_long"] = data["Close"].rolling(window=50).mean()

data["Signal"] = 0
data.loc[data["SMA_short"] > data["SMA_long"], "Signal"] = 1
data.loc[data["SMA_short"] < data["SMA_long"], "Signal"] = -1

data["Position"] = data["Signal"].diff()
data["Daily_Return"] = data["Close"].pct_change()
data["Strategy_Return"] = data["Daily_Return"] * data["Signal"].shift(1)

strategy_total_return = (1 + data["Strategy_Return"]).prod() - 1
buyhold_total_return = (1 + data["Daily_Return"]).prod() - 1

cumulative = (1 + data["Strategy_Return"]).cumprod()
running_max = cumulative.cummax()
drawdown = (cumulative - running_max) / running_max
max_drawdown = drawdown.min()

crossovers = data[data["Position"] != 0]
print(crossovers[["Close", "SMA_short", "SMA_long", "Signal", "Position"]])
print(f"\nStrategy Total Return: {strategy_total_return:.2%}")
print(f"Buy & Hold Total Return: {buyhold_total_return:.2%}")
print(f"Max Drawdown: {max_drawdown:.2%}")