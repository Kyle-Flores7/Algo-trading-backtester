"""
STRATEGY: Opening Range Breakout (ORB)
=============================================

Concept:
The first 15 minutes after the market opens (9:30-9:45 AM ET) tend to see a
spike in volume and volatility, as overnight news and pre-market positioning
all get resolved at once. That window's high and low form the "opening
range" - a reference level for the rest of the day.

- If price CLOSES ABOVE the opening range high after 9:45 -> read as
  bullish continuation -> go LONG for the rest of the day
- If price CLOSES BELOW the opening range low after 9:45 -> read as
  bearish continuation -> go SHORT for the rest of the day
- Whichever direction triggers first "wins" for the day - once positioned,
  hold until stopped out, target hit, or market close. No reversing mid-day.

Risk management (1:2 risk/reward):
The opening range size (high - low) is used as the "risk unit" for the
trade, since it's a natural measure of how much this stock is moving that
morning:
- Stop-loss: 1x the opening range, against the trade direction
- Profit target: 2x the opening range, in the trade direction
- Whichever is hit first - stop, target, or market close (4:00 PM ET) if
  neither is hit - closes the trade. No overnight positions, ever, this is
  a pure day-trading strategy, not swing trading with intraday timing.

If a single 5-minute bar's high/low range touches both the stop and the
target (a wide or gappy bar), the stop is assumed to hit first - the
conservative assumption, since we can't see what happened first within
the bar from 5-minute OHLC data alone.

This is intraday, not daily, data - each day is tested independently rather
than one continuous equity curve like the swing strategies in strategies/.
backtest.py's run_backtest() assumes one row per day and can't be reused
here, so P/L is tracked manually, one trading day at a time.

Data note: yfinance caps 1-minute history at 8 trading days per request,
which was too small a sample to draw much from. 5-minute bars relax that
cap to 60 calendar days - 60 actual trading days of data - a meaningfully
bigger sample, at the cost of coarser resolution on exactly when a
breakout happens within each 5-minute bar. The opening range is now the
first three 5-minute bars (9:30, 9:35, 9:40), covering the same 9:30-9:45
AM window as before.
"""

import pandas as pd
import yfinance as yf

ticker = "QQQ"
data = yf.download(ticker, period="60d", interval="5m")

# Flatten multi-level columns from yfinance (e.g. "Close"/"QQQ" stacked)
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

trades = []
days_tested = 0

for day, day_data in data.groupby(data.index.date):
    # Opening range = first three 5-minute bars (9:30, 9:35, 9:40),
    # covering the same 9:30-9:45 AM window as the 1-minute version.
    opening_range = day_data.between_time("09:30", "09:40")
    if opening_range.empty:
        continue

    # Skip the current/incomplete trading day - its last bar won't reach
    # market close yet, so it has no real exit price to measure P/L against.
    # A completed day's last 5-minute bar is 15:55 (covers 15:55-16:00).
    if day_data.index[-1].time() < pd.Timestamp("15:55").time():
        print(f"{day}: Skipped - incomplete session (in progress)")
        continue

    days_tested += 1
    or_high = opening_range["High"].max()
    or_low = opening_range["Low"].min()
    or_range = or_high - or_low

    after_open = day_data.between_time("09:45", "15:55")
    close_price = day_data["Close"].iloc[-1]

    direction = None
    entry_price = None
    entry_idx = None

    # Walk forward 5-minute bar by bar - take whichever breakout happens first
    for i in range(len(after_open)):
        row = after_open.iloc[i]
        if row["Close"] > or_high:
            direction = "LONG"
            entry_price = row["Close"]
            entry_idx = i
            break
        elif row["Close"] < or_low:
            direction = "SHORT"
            entry_price = row["Close"]
            entry_idx = i
            break

    if direction is None:
        print(f"{day}: No breakout - no trade "
              f"(range {or_low:.2f}-{or_high:.2f})")
        continue

    if direction == "LONG":
        stop_price = entry_price - or_range
        target_price = entry_price + 2 * or_range
    else:
        stop_price = entry_price + or_range
        target_price = entry_price - 2 * or_range

    exit_price = close_price
    exit_reason = "close"

    # Check each bar after entry for a stop or target hit, using intrabar
    # high/low (not just closes) since a stop/target can be hit mid-bar.
    for j in range(entry_idx + 1, len(after_open)):
        bar = after_open.iloc[j]
        if direction == "LONG":
            if bar["Low"] <= stop_price:
                exit_price, exit_reason = stop_price, "stop"
                break
            elif bar["High"] >= target_price:
                exit_price, exit_reason = target_price, "target"
                break
        else:
            if bar["High"] >= stop_price:
                exit_price, exit_reason = stop_price, "stop"
                break
            elif bar["Low"] <= target_price:
                exit_price, exit_reason = target_price, "target"
                break

    if direction == "LONG":
        pnl = exit_price - entry_price
    else:
        pnl = entry_price - exit_price

    trades.append(pnl)
    print(f"{day}: {direction} | Entry = {entry_price:.2f} | "
          f"Exit = {exit_price:.2f} ({exit_reason}) | P/L = {pnl:+.2f} points")

# --- Summary ---
print("\n--- Summary ---")
print(f"Days tested: {days_tested}")
print(f"Trades taken: {len(trades)}")
if trades:
    total_pnl = sum(trades)
    winners = [p for p in trades if p > 0]
    losers = [p for p in trades if p < 0]
    print(f"Total P/L: {total_pnl:+.2f} points")
    print(f"Win rate: {len(winners)}/{len(trades)} ({len(winners) / len(trades):.0%})")
    if winners:
        print(f"Average win: {sum(winners) / len(winners):+.2f} points")
    if losers:
        print(f"Average loss: {sum(losers) / len(losers):+.2f} points")
