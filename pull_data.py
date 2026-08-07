import yfinance as yf
import matplotlib.pyplot as plt

ticker = "SPY"
data = yf.download(ticker, period="6mo")
data["Close"].plot(title=f"{ticker} Closing Price - Last 6 Months")
plt.xlabel("Date")
plt.ylabel("Price ($)")
plt .savefig("spy-chart.png")
print("Chart saved as spy_chart.png")
