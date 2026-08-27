"""
STRATEGY: Opening Range Sweep-and-Reverse - Futures (ORB Sweep Futures)
=============================================

Concept:
Same sweep-and-reverse logic as orb_sweep.py, applied to MNQ=F (Micro E-mini
Nasdaq-100 futures) instead of QQQ/SPY. MNQ is used rather than the full-size
NQ contract because its smaller notional size ($2/point vs $20/point) is a
more realistic position size for this kind of research/backtesting account -
see the fundamentals notes on instrument sizing. NQ=F and MNQ=F track the
same underlying index and move together almost tick-for-tick, so the
sweep-and-reverse signal logic itself is identical between them.

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

Risk management (1:2 risk/reward):
The opening range size (high - low) is used as the "risk unit" for the
trade, since it's a natural measure of how much this instrument is moving
that morning:
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

Futures-specific handling - overnight session filtering:
Unlike QQQ/SPY, which only trade during the 9:30 AM - 4:00 PM ET cash
session, futures like MNQ trade nearly 24 hours a day (Sunday 6 PM ET
through Friday 5 PM ET, with a short daily maintenance break). yfinance
groups this data by calendar date, so a naive groupby(data.index.date)
"day" for a futures ticker contains overnight bars (the evening session
bleeding past midnight, plus the start of the next evening session before
midnight) in addition to the actual NY day session. If left unfiltered,
those overnight bars would corrupt both the opening-range calculation and
the "is this day complete yet" check (the last bar of a calendar date
would be an evening-session bar near midnight, not the 15:55 bar that
closes out the day session).

To handle this, each calendar-date group is first restricted to the NY day
session (9:30 AM - 4:00 PM ET) with between_time() before anything else
happens - the opening range, the incomplete-day check, and the post-open
trade walk are all computed only from that filtered slice, exactly as they
would be for an equity ticker whose data never contains overnight bars in
the first place. The opening range itself is still the first three
5-minute bars of the day session (9:30, 9:35, 9:40), covering 9:30-9:45 AM
ET - the same NY session open used for QQQ/SPY.

Data note: yfinance caps 1-minute history at 8 trading days per request,
which was too small a sample to draw much from. 5-minute bars relax that
cap to 60 calendar days of history.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100) but can be overridden,
# e.g. `python orb_sweep_futures.py NQ=F`, to compare against the full-size
# contract.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"
data = yf.download(ticker, period="60d", interval="5m")

# Flatten multi-level columns from yfinance (e.g. "Close"/"MNQ=F" stacked)
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

trades = []
days_tested = 0

for day, day_data in data.groupby(data.index.date):
    # Futures trade nearly 24 hours, so a calendar-date group can contain
    # overnight bars (the prior evening session past midnight, and the
    # start of the next evening session before midnight) alongside the
    # actual NY day session. Restrict to the 9:30 AM - 4:00 PM ET day
    # session up front so overnight bars never leak into the opening
    # range, the trade walk, or the completeness check below.
    day_session = day_data.between_time("09:30", "16:00")
    if day_session.empty:
        continue

    # Opening range = first three 5-minute bars (9:30, 9:35, 9:40),
    # covering the 9:30-9:45 AM NY session open.
    opening_range = day_session.between_time("09:30", "09:40")
    if opening_range.empty:
        continue

    # Skip the current/incomplete trading day - its last bar won't reach
    # market close yet, so it has no real exit price to measure P/L against.
    # A completed day session's last 5-minute bar is 15:55 (covers
    # 15:55-16:00). Checked against day_session (not the raw calendar-date
    # group), since for futures the raw group's last bar is an overnight
    # bar near midnight rather than the day session's close.
    if day_session.index[-1].time() < pd.Timestamp("15:55").time():
        print(f"{day}: Skipped - incomplete session (in progress)")
        continue

    days_tested += 1
    or_high = opening_range["High"].max()
    or_low = opening_range["Low"].min()
    or_range = or_high - or_low

    after_open = day_session.between_time("09:45", "15:55")
    close_price = day_session["Close"].iloc[-1]

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
