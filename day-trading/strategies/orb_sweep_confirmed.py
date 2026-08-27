"""
STRATEGY: Opening Range Sweep-and-Reverse - Confirmed Entry (ORB Sweep Confirmed)
=============================================

Concept:
Same MNQ=F sweep-and-reverse setup as orb_sweep_futures.py, with one change:
entry requires a confirmation bar.

Plain sweep-and-reverse (orb_sweep_futures.py) enters the instant price
closes back inside the opening range after sweeping past it - the very bar
that closes back inside IS the entry trigger. That's fast, but it also
means every "fakeout of the fakeout" (price closes back inside for one bar,
then immediately fails again and continues the original breakout
direction) gets entered anyway, right before it reverses again.

This variant adds a confirmation requirement: the close-back-inside bar is
now treated as a SIGNAL, not an entry trigger. Entry only happens if the
very next 5-minute bar ALSO closes in the same direction the signal bar
moved (i.e. its close is beyond the signal bar's close, continuing the
same way) - confirming the reversal has follow-through instead of being a
single-bar blip. If that next bar fails to confirm (closes back the other
way), the signal is dropped - but the sweep flags stay set, so a later bar
that closes back inside the range becomes a fresh signal, which then needs
its own confirmation bar in turn. Whichever direction is the first to
actually get a confirmed entry "wins" for the day - once positioned, hold
until stopped out, target hit, or market close. No reversing mid-day.

Sweep-and-reverse signal logic (unchanged from orb_sweep_futures.py):
- If price trades BELOW the opening range low (a downside sweep) and then
  CLOSES back ABOVE the opening range low -> failed breakdown signal,
  LONG if confirmed.
- If price trades ABOVE the opening range high (an upside sweep) and then
  CLOSES back BELOW the opening range high -> failed breakout signal,
  SHORT if confirmed.
- The sweep and the signal close can happen in the same 5-minute bar (a
  bar that wicks past the level but closes back inside it) or across
  several bars.

Confirmation logic (new):
- Signal bar closes back inside the range in direction D (LONG or SHORT).
- The NEXT bar is checked: if its close continues further in direction D
  than the signal bar's close did (higher close for LONG, lower close for
  SHORT), the signal is confirmed - entry happens at that next bar's close.
- If the next bar doesn't continue in direction D, the signal is dropped
  (no entry from it). Sweep tracking carries on, so a later close back
  inside the range can still produce a new signal to confirm.
- Because entry is pushed one bar later than orb_sweep_futures.py, entries
  happen at a worse average price when a move is genuinely reversing (the
  cost of waiting for confirmation) but should avoid entries on moves that
  immediately fail again.

Risk management (1:2 risk/reward) - identical to orb_sweep_futures.py:
The opening range size (high - low) is the "risk unit":
- Stop-loss: 1.5x the opening range, against the trade direction
- Profit target: 2x the opening range, in the trade direction
- Whichever is hit first - stop, target, or market close (4:00 PM ET) if
  neither is hit - closes the trade. No overnight positions.

If a single 5-minute bar's high/low range touches both the stop and the
target (a wide or gappy bar), the stop is assumed to hit first - the
conservative assumption, since we can't see what happened first within
the bar from 5-minute OHLC data alone.

Futures-specific handling - overnight session filtering (unchanged from
orb_sweep_futures.py): MNQ trades nearly 24 hours a day, so each calendar
date's data is restricted to the NY day session (9:30 AM - 4:00 PM ET)
with between_time() before the opening range, the incomplete-day check, or
the post-open trade walk are computed, so overnight bars never leak in.
The opening range is still the first three 5-minute bars of the day
session (9:30, 9:35, 9:40), covering 9:30-9:45 AM ET.

This is intraday, not daily, data - each day is tested independently
rather than one continuous equity curve like the swing strategies in
strategies/. backtest.py's run_backtest() assumes one row per day and
can't be reused here, so P/L is tracked manually, one trading day at a
time.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100) but can be overridden,
# e.g. `python orb_sweep_confirmed.py NQ=F`, to compare against the
# full-size contract.
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
    # overnight bars alongside the actual NY day session. Restrict to the
    # 9:30 AM - 4:00 PM ET day session up front so overnight bars never
    # leak into the opening range, the trade walk, or the completeness
    # check below.
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

    # A signal (close back inside the range after a sweep) is held as
    # "pending" until the following bar either confirms it (closes further
    # in the same direction -> enter) or fails to (drop the signal, keep
    # scanning for a fresh one).
    pending_direction = None
    pending_close = None

    for i in range(len(after_open)):
        row = after_open.iloc[i]

        # Resolve a pending signal from the previous bar using this bar's
        # close, before this bar can become a new signal in its own right.
        if pending_direction == "LONG":
            if row["Close"] > pending_close:
                direction = "LONG"
                entry_price = row["Close"]
                entry_idx = i
                break
            pending_direction = None
        elif pending_direction == "SHORT":
            if row["Close"] < pending_close:
                direction = "SHORT"
                entry_price = row["Close"]
                entry_idx = i
                break
            pending_direction = None

        if row["Low"] < or_low:
            swept_below = True
        if row["High"] > or_high:
            swept_above = True

        if pending_direction is None:
            if swept_below and row["Close"] > or_low:
                pending_direction = "LONG"
                pending_close = row["Close"]
            elif swept_above and row["Close"] < or_high:
                pending_direction = "SHORT"
                pending_close = row["Close"]

    if direction is None:
        print(f"{day}: No confirmed sweep-and-reverse - no trade "
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
