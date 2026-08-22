"""
STRATEGY: Opening Range Sweep-and-Reverse (ORB Sweep)
=============================================

Concept:
This is a variation of the plain Opening Range Breakout (see orb.py) that
fades false breakouts instead of following them.

Plain ORB reads a CLOSE beyond the opening range as continuation and trades
in that direction. But a common intraday pattern is a "stop hunt" or
"liquidity sweep": price pokes just past the opening range to trigger
stop-loss orders resting there, then snaps back inside the range as those
stops get absorbed and real buyers/sellers step back in. Plain ORB would
either miss this move entirely or get chopped up entering on the wrong side
right before the reversal.

Sweep-and-reverse entry logic:
- If price trades BELOW the opening range low (a downside sweep) and then
  CLOSES back ABOVE the opening range low -> read as a failed breakdown,
  buyers regaining control -> go LONG, fading the sweep.
- If price trades ABOVE the opening range high (an upside sweep) and then
  CLOSES back BELOW the opening range high -> read as a failed breakout,
  sellers regaining control -> go SHORT, fading the sweep.
- The sweep and the reversal-close can happen in the same 5-minute bar (a
  bar that wicks past the level but closes back inside it) or across
  several bars (price stays outside the range for a while before finally
  closing back inside). Either way counts as a sweep-and-reverse signal.
- Whichever direction's reversal condition is met first "wins" for the day
  - once positioned, hold until stopped out, target hit, or market close.
  No reversing mid-day.

This is the opposite entry trigger from orb.py: plain ORB enters ON a close
beyond the range (trading the breakout), while this strategy enters on a
close back INSIDE the range after price already traded beyond it (trading
the failure of the breakout). Everything else - opening range definition,
risk management, exit rules, and data handling - is identical to orb.py.

Risk management (1:2 risk/reward):
The opening range size (high - low) is used as the "risk unit" for the
trade, since it's a natural measure of how much this stock is moving that
morning:
- Stop-loss: 1.5x the opening range, against the trade direction
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
bigger sample, at the cost of coarser resolution on exactly when a sweep
or reversal happens within each 5-minute bar. The opening range is the
first three 5-minute bars (9:30, 9:35, 9:40), covering the 9:30-9:45 AM
window.
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
    swept_below = False
    swept_above = False

    # Walk forward 5-minute bar by bar - track whether price has swept
    # past either edge of the opening range, then take whichever
    # reversal (a close back inside the range) happens first.
    for i in range(len(after_open)):
        row = after_open.iloc[i]

        if row["Low"] < or_low:
            swept_below = True
        if row["High"] > or_high:
            swept_above = True

        if swept_below and row["Close"] > or_low:
            direction = "LONG"
            entry_price = row["Close"]
            entry_idx = i
            break
        elif swept_above and row["Close"] < or_high:
            direction = "SHORT"
            entry_price = row["Close"]
            entry_idx = i
            break

    if direction is None:
        print(f"{day}: No sweep-and-reverse - no trade "
              f"(range {or_low:.2f}-{or_high:.2f})")
        continue

    if direction == "LONG":
        stop_price = entry_price - 1.5 * or_range
        target_price = entry_price + 2 * or_range
    else:
        stop_price = entry_price + 1.5 * or_range
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
