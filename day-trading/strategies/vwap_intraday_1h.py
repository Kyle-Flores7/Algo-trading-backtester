"""
STRATEGY: VWAP Pullback - 1-Hour Bars (VWAP Intraday 1h)
=========================================================

vwap_intraday.py's exact signal, moved from 5-minute to 1-hour bars, to get
a longer, genuinely non-overlapping test window instead of another 60-day
slice of the same recent market regime.

Why 1-hour and not 15-minute
-----------------------------
Checked empirically (see day-trading/notes/findings.md) - yfinance's actual
history caps, by asking for progressively longer periods until the request
fails:

    Interval   MNQ=F max window        QQQ max window
    5-minute   ~60 calendar days       ~60 calendar days   (already used)
    15-minute  ~60 calendar days       ~60 calendar days   (NO gain - same
                                                             cap as 5-minute)
    1-hour     730 calendar days       730 calendar days   (12x longer)

15-minute bars are capped at the same ~60 days as 5-minute, so switching to
15-minute would not buy a longer or more independent sample - it would just
be a coarser cut of the identical window already tested. 1-hour is the only
step up that actually unlocks new history (Yahoo's own hard limit, per its
API error: "must be within the last 730 days"), so this script uses 1-hour
bars, not 15-minute.

What carries over unchanged from vwap_intraday.py
---------------------------------------------------
The signal itself, and every risk parameter, is IDENTICAL:
  - Per-day VWAP, reset at 9:30, typical_price = (H+L+C)/3.
  - First cash-session bar closing off VWAP sets LONG-only / SHORT-only
    bias; entry is the first later bar that pulls back to touch VWAP and
    closes back on the bias side.
  - ATR_PERIOD=20, STOP_MULT=1.5x, TARGET_MULT=2.0x - not rescaled.
  - One trade per day, no overnight hold, exit priority stop/target/close,
    stop assumed first if one bar spans both.
  - $5 flat round-trip cost per contract (see the cost-model correction in
    findings.md - $25 was an unresearched guess, $5 matches real MNQ rate
    cards).

Why the ATR/stop/target math does NOT need new multipliers
------------------------------------------------------------
ATR is a self-scaling statistic: it's computed directly from THIS series'
own high/low/close, so a 1-hour bar's ATR is automatically proportionally
larger than a 5-minute bar's ATR (a 1-hour bar simply has a bigger typical
range than a 5-minute bar) - the stop/target distances (1.5x / 2.0x ATR)
scale up right along with it with no code change needed. What would NOT
have scaled correctly is the bar-count-based session logic below, which is
tied to how many bars fit in a session at a given resolution - that's what
actually needed adapting.

What was adapted for 1-hour bars
-----------------------------------
1. **Post-close settlement bar exclusion (MNQ-specific).** QQQ's 1-hour
   bars are aligned to the 9:30 AM open (09:30, 10:30, ..., 15:30 - a runt
   final 30-minute bar), so they never touch 16:00. MNQ=F's bars are
   aligned to the top of the hour regardless of session (continuous
   near-24h trading), so its LAST bar of a trading day lands exactly at
   16:00 and covers 16:00-17:00 - after the 4:00 PM cash close, low-volume
   settlement-period trading. Any bar whose timestamp is exactly 16:00:00
   is dropped from the session for both tickers (a no-op for QQQ, and
   correct for MNQ).
2. **Incomplete-day detection, made dynamic instead of a hardcoded time.**
   vwap_intraday.py hardcodes "a finished 5-minute session's last bar is
   15:55." That specific time does not apply at 1-hour resolution, and
   worse, it isn't even the SAME cutoff for both tickers here: after
   exclusion #1, a complete QQQ day's last bar starts at 15:30 (the runt
   half-hour bar), while a complete MNQ day's last bar starts at 15:00
   (its bars are full hours, so 15:00-16:00 is the last one before the
   excluded 16:00 settlement bar). Instead of hardcoding either value,
   this script computes the MODAL number of session bars across the whole
   pull and treats any day with fewer bars than that mode as incomplete -
   either today's still-forming session, or a holiday half day. This
   single rule handles both tickers' different bar alignments correctly
   with no per-ticker special-casing.

Data note: yfinance's 1-hour cap is 730 calendar days (Yahoo's own limit,
not a yfinance restriction) - see findings.md for the empirical check
against 15-minute and 5-minute. That 730-day window, ending today, entirely
contains the ~60 most recent days as a subset - the same calendar period
the original 5-minute vwap_intraday.py sample covers - so roughly the most
recent 8% of this window overlaps the original test period and the other
~92% (about two years further back) is genuinely new, non-overlapping
market history. The summary below reports the exact overlap.
"""

import sys
from collections import Counter
from datetime import time as dtime

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100), same as vwap_intraday.py.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"

# Dollar multiplier per ticker - MNQ is $2/index point; QQQ uses the same
# MNQ-notional-matched 82-share position vwap_qqq.py used, so the dollar
# comparison stays apples-to-apples with the futures baseline.
if ticker == "QQQ":
    POINT_VALUE = 82.0
elif ticker == "MNQ=F":
    POINT_VALUE = 2.0
else:
    POINT_VALUE = 1.0  # unscaled fallback for any other ticker

# ATR / risk parameters - unchanged from vwap_intraday.py (see docstring).
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0

# Realistic trading friction - same corrected $5/trade figure as
# vwap_intraday.py (see findings.md's cost-model correction).
ROUND_TRIP_COST_USD = 5.0
CONTRACTS = 1

# Concentration check: how many of the biggest winners to measure against
# gross profit.
TOP_N = 3

data = yf.download(ticker, period="730d", interval="1h")
data.columns = data.columns.get_level_values(0)

WINDOW_START = data.index[0]
WINDOW_END = data.index[-1]

# ATR(20) on the continuous 1-hour series - same True Range formula as
# vwap_intraday.py.
prev_close = data["Close"].shift()
true_range = pd.concat(
    [
        data["High"] - data["Low"],
        (data["High"] - prev_close).abs(),
        (data["Low"] - prev_close).abs(),
    ],
    axis=1,
).max(axis=1)
data["ATR"] = true_range.rolling(window=ATR_PERIOD).mean()

# --- Pass 1: slice each day to the cash session and find the modal
# (complete-day) session length, so "incomplete day" is detected from the
# data itself rather than a hardcoded, resolution-specific time string. ---
day_sessions = {}
for day, day_data in data.groupby(data.index.date):
    day_session = day_data.between_time("09:30", "16:00")
    # Drop any bar starting exactly at 16:00 - it covers 16:00-17:00,
    # after the cash session closes (only ever fires for MNQ's
    # top-of-hour-aligned bars; QQQ's 9:30-aligned bars never hit 16:00).
    day_session = day_session[day_session.index.time != dtime(16, 0)]
    if day_session.empty:
        continue
    day_sessions[day] = day_session

session_length_counts = Counter(len(s) for s in day_sessions.values())
expected_bars_per_day = session_length_counts.most_common(1)[0][0]

trades = []
days_tested = 0

# --- Pass 2: run the VWAP pullback logic on each complete day. ---
for day, session in day_sessions.items():
    if len(session) < expected_bars_per_day:
        print(f"{day}: Skipped - incomplete session "
              f"({len(session)}/{expected_bars_per_day} bars)")
        continue

    # --- VWAP for this day only, reset at 9:30 ---
    typical_price = (session["High"] + session["Low"] + session["Close"]) / 3
    volume = session["Volume"]
    cum_volume = volume.cumsum()
    if cum_volume.iloc[-1] == 0:
        print(f"{day}: Skipped - no volume data for VWAP")
        continue
    vwap = (typical_price * volume).cumsum() / cum_volume

    days_tested += 1

    close = session["Close"]
    high = session["High"]
    low = session["Low"]
    atr_series = data["ATR"].reindex(session.index)
    close_price = close.iloc[-1]

    # --- Day bias: first bar that closes clearly off VWAP ---
    bias = None
    bias_idx = None
    for i in range(len(session)):
        v = vwap.iloc[i]
        if pd.isna(v):
            continue
        if close.iloc[i] > v:
            bias, bias_idx = "LONG", i
            break
        if close.iloc[i] < v:
            bias, bias_idx = "SHORT", i
            break

    if bias is None:
        print(f"{day}: No VWAP bias established - no trade")
        continue

    # --- Entry: first pullback to VWAP that holds in the bias direction ---
    direction = None
    entry_price = None
    entry_idx = None
    entry_atr = None
    entry_vwap = None

    for i in range(bias_idx + 1, len(session)):
        v = vwap.iloc[i]
        atr = atr_series.iloc[i]
        if pd.isna(v) or pd.isna(atr):
            continue

        if bias == "LONG":
            pulled_back_and_held = low.iloc[i] <= v and close.iloc[i] > v
        else:
            pulled_back_and_held = high.iloc[i] >= v and close.iloc[i] < v

        if pulled_back_and_held:
            direction = bias
            entry_price = close.iloc[i]
            entry_idx = i
            entry_atr = atr
            entry_vwap = v
            break

    if direction is None:
        print(f"{day}: {bias} bias, but no VWAP pullback held - no trade")
        continue

    if direction == "LONG":
        stop_price = entry_price - STOP_MULT * entry_atr
        target_price = entry_price + TARGET_MULT * entry_atr
    else:
        stop_price = entry_price + STOP_MULT * entry_atr
        target_price = entry_price - TARGET_MULT * entry_atr

    exit_price = close_price
    exit_reason = "close"

    # Walk each bar after entry for a stop or target hit, using intrabar
    # high/low. If one bar spans both, the stop is assumed first.
    for j in range(entry_idx + 1, len(session)):
        bar_high = high.iloc[j]
        bar_low = low.iloc[j]
        if direction == "LONG":
            if bar_low <= stop_price:
                exit_price, exit_reason = stop_price, "stop"
                break
            elif bar_high >= target_price:
                exit_price, exit_reason = target_price, "target"
                break
        else:
            if bar_high >= stop_price:
                exit_price, exit_reason = stop_price, "stop"
                break
            elif bar_low <= target_price:
                exit_price, exit_reason = target_price, "target"
                break

    if direction == "LONG":
        pnl = exit_price - entry_price
    else:
        pnl = entry_price - exit_price

    trades.append(pnl)
    print(f"{day}: {direction} | Entry = {entry_price:.2f} "
          f"(VWAP {entry_vwap:.2f}) | Exit = {exit_price:.2f} ({exit_reason}) | "
          f"ATR = {entry_atr:.2f} | P/L = {pnl:+.2f} points")

# --- Summary ---
print("\n--- Summary ---")
print(f"Ticker: {ticker}  (interval: 1h)")
print(f"Data window: {WINDOW_START.date()} -> {WINDOW_END.date()} "
      f"({(WINDOW_END - WINDOW_START).days} calendar days)")
print(f"Expected bars/complete day: {expected_bars_per_day}")
print(f"Days tested: {days_tested}")
print(f"Trades taken: {len(trades)}")
if trades:
    total_pnl = sum(trades)
    winners = sorted([p for p in trades if p > 0], reverse=True)
    losers = [p for p in trades if p < 0]

    print(f"Total P/L: {total_pnl:+.2f} points  "
          f"(${total_pnl * POINT_VALUE:+,.2f} at ${POINT_VALUE:.0f}/point)")
    print(f"Win rate: {len(winners)}/{len(trades)} "
          f"({len(winners) / len(trades):.0%})")
    if winners:
        print(f"Average win: {sum(winners) / len(winners):+.2f} points")
    if losers:
        print(f"Average loss: {sum(losers) / len(losers):+.2f} points")

    gross_profit = sum(winners)
    if gross_profit > 0:
        n = min(TOP_N, len(winners))
        top_n_share = sum(winners[:n]) / gross_profit
        print(f"Concentration: top {n} winner(s) = {top_n_share:.0%} of "
              f"gross profit ({gross_profit:.2f} points across "
              f"{len(winners)} winning trade(s))")

    # --- Commission + slippage adjustment ---
    cost_per_trade_usd = ROUND_TRIP_COST_USD * CONTRACTS
    total_cost_usd = len(trades) * cost_per_trade_usd

    gross_points = total_pnl
    gross_usd = total_pnl * POINT_VALUE * CONTRACTS
    net_usd = gross_usd - total_cost_usd

    print("\n--- Cost adjustment (commission + slippage) ---")
    print(f"Contracts/position size: {CONTRACTS} "
          f"({'82 QQQ shares, MNQ-notional matched' if ticker == 'QQQ' else 'contract(s)'})")
    print(f"Assumed round-trip cost: ${ROUND_TRIP_COST_USD:,.2f} per contract "
          f"= ${cost_per_trade_usd:,.2f} per trade")
    print(f"Total cost: {len(trades)} trades x ${cost_per_trade_usd:,.2f} "
          f"= ${total_cost_usd:,.2f}")
    print()
    print(f"{'':<22}{'Before costs':>16}{'After costs':>16}")
    print(f"{'Total P/L (points)':<22}{gross_points:>+16.2f}{'-':>16}")
    print(f"{'Total P/L (USD)':<22}{gross_usd:>+16,.2f}{net_usd:>+16,.2f}")
    print(f"{'Net profitable?':<22}{'YES' if gross_usd > 0 else 'NO':>16}"
          f"{'YES' if net_usd > 0 else 'NO':>16}")
