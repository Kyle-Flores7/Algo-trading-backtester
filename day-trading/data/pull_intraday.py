"""
Pull 1-minute QQQ data and print the opening range (9:30-9:45 AM ET) for
each of the last 5 trading days.

Proof-of-concept for Opening Range Breakout (ORB) - confirms we can pull
intraday data and correctly isolate the opening range before building any
actual strategy logic on top of it.
"""

import yfinance as yf

ticker = "QQQ"
data = yf.download(ticker, period="5d", interval="1m")

# Flatten multi-level columns from yfinance (e.g. "Close"/"QQQ" stacked)
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

# Opening range window: 9:30-9:45 AM ET
opening_range = data.between_time("09:30", "09:44")

for day, rows in opening_range.groupby(opening_range.index.date):
    high = rows["High"].max()
    low = rows["Low"].min()
    print(f"{day}: Opening Range High = {high:.2f}, Low = {low:.2f}")
