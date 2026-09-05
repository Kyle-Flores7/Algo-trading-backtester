"""
STRATEGY: Multi-Factor Day Trade - Setup v1 (HTF Bias + Session + VWAP + Sweep)
================================================================================

Concept:
Every prior day-trading attempt combined at most two elements (a single
trigger, or a trigger plus one or two context filters - see
day-trading/notes/findings.md). This setup combines FOUR, each one already
individually proven or reasoned about somewhere in this project, on the
premise that a genuine confluence of independent conditions might filter
down to a higher-probability subset of setups where no single element did:

  1. HIGHER-TIMEFRAME BIAS - daily close vs 50-day SMA, using only the
     PRIOR completed daily bar (no lookahead). Identical mechanism to
     multifactor_v1.py's trend filter, but that test wrapped it around RSI
     at 5-minute resolution and never got a fair trial at this bar count /
     time scale - untested alone at 1-hour/multi-year scale.
  2. SESSION FILTER - entries only inside 9:30-11:00 AM ET. The foundational
     filter of this whole track, present in every script since orb.py.
  3. VWAP - structural anchor, calculated per-day exactly like
     vwap_intraday.py / vwap_intraday_1h.py: reset at 9:30,
     typical_price = (H+L+C)/3, cumulative volume-weighted. This is the one
     validated real signal the day-trading track has produced (see the
     "Milestone" section of findings.md - profitable at $5/trade cost on
     the original 60-day/5-minute sample, though see also the 1-hour
     follow-up that found the edge did not survive a longer window).
  4. LIQUIDITY SWEEP - a documented concept (orb_sweep.py and its variants),
     previously only tested fading an OPENING-RANGE level and never
     combined with a VWAP anchor. Here the level being swept is a rolling
     20-bar swing high/low (market structure), not the opening range.

Trigger logic
-------------
Both the sweep and the reclaim must happen inside the 9:30-11:00 AM entry
window (see "What was deliberately simplified" below for why).

  - swing_low  = rolling 20-bar minimum of Low, swing_high = rolling 20-bar
    maximum of High, each computed on the continuous 1-hour series and
    shifted by 1 bar so the current bar is compared against the PRIOR 20
    bars only (no lookahead - a bar cannot be part of its own swing level).

  - BULLISH bias day (LONG only): walking forward through the entry window,
    once any bar's Low breaks below swing_low (the sweep), watch for the
    first later bar (or the same bar) that CLOSES back above swing_low (the
    reclaim - a failed breakdown). That reclaim is only taken as an entry if
    VWAP at that bar is ABOVE swing_low too - i.e. VWAP sits further in the
    bias direction than the level just swept, so the reclaim is
    structurally a move TOWARD (or, if the close is already above VWAP,
    THROUGH) the VWAP anchor, not a reclaim of a level with nothing above
    it to advance toward.

  - BEARISH bias day (SHORT only): the mirror image - a sweep above
    swing_high, a reclaim close back below swing_high, taken only if VWAP
    is BELOW swing_high (so the reclaim is a move down toward/through VWAP).

  - Only the bias-aligned direction is ever considered on a given day
    (bullish bias days never take the SHORT sweep pattern and vice versa) -
    this is what "in the direction of the higher-timeframe bias" means
    structurally: bias picks which side of the market this setup is even
    looking for, VWAP-alignment then decides whether a given sweep+reclaim
    on that side counts.

What was deliberately simplified
---------------------------------
The prompt's spec leaves two things underspecified, resolved here as
follows:

  - The "prior 20-bar swing high/low" is computed on the continuous 1-hour
    series (like ATR below), so it can extend across day boundaries -
    at ~6-7 bars/day, 20 bars covers roughly the prior 3 trading days'
    structure, which is what "recent swing high/low" means at this
    resolution. It is NOT a per-day-reset level like VWAP.
  - Both the sweep and the reclaim must occur WITHIN the 9:30-11:00 entry
    window (not a sweep from yesterday's overnight session reclaimed at the
    open) - this keeps the signal cleanly inside the one filter (#2) that
    is unambiguous in the spec, rather than guessing how far back a
    qualifying sweep is allowed to have started.

Risk / exits / costs / one-trade-per-day / incomplete-day exclusion - ALL
carried over unchanged from vwap_intraday_1h.py, since that script already
solved the resolution-specific bar-count and settlement-bar problems this
setup also needs:
  - ATR_PERIOD=20, STOP_MULT=1.5x, TARGET_MULT=2.0x - ATR is self-scaling,
    no rescaling needed for 1-hour bars (see vwap_intraday_1h.py docstring).
  - Exit priority: stop / target / 4:00 PM ET close, whichever comes first;
    stop assumed first if one bar spans both (conservative, hourly OHLC
    can't show intrabar order).
  - One trade per day maximum - the entry scan stops at the first
    qualifying reclaim in the 9:30-11:00 window; trade MANAGEMENT continues
    through the rest of the session to the close.
  - MNQ's post-close settlement bar (exactly 16:00, covering 16:00-17:00) is
    dropped from the session (a no-op for QQQ).
  - Incomplete-day detection uses the MODAL session bar count across the
    whole pull, not a hardcoded time string (resolution- and
    ticker-alignment-independent, per vwap_intraday_1h.py).
  - $5 flat round-trip cost per contract (the corrected, broker-rate-card
    figure - see findings.md's cost-model correction; NOT the original
    unresearched $25 guess).

Selectivity funnel
------------------
Because four conditions must all line up, the summary reports how much
each stage cuts the raw candidate set: days with a usable HTF bias and a
complete session, days that additionally had a bias-aligned sweep+reclaim
at all (regardless of VWAP alignment), and days that were actually traded
(also VWAP-aligned). This directly measures what the VWAP-alignment
condition (#4's actual entry gate) is contributing on top of the raw
structural sweep pattern.

Data note: yfinance's 1-hour cap empirically returns each ticker's full
available history under period="730d" (see findings.md) - MNQ=F from
2024-04-14, QQQ from 2023-10-09, i.e. roughly 2.4-2.9 years depending on
run date. The daily series for the HTF bias is pulled separately over a
much longer window so the 50-day SMA and the "prior completed day" lookup
are defined across the entire hourly range.
"""

import sys
from collections import Counter
from datetime import time as dtime

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100), same as the other
# day-trading scripts.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"

# Dollar multiplier per ticker - MNQ is $2/index point; QQQ uses the same
# MNQ-notional-matched 82-share position vwap_qqq.py / vwap_intraday_1h.py
# used, so the dollar comparison stays apples-to-apples with the futures
# baseline.
if ticker == "QQQ":
    POINT_VALUE = 82.0
elif ticker == "MNQ=F":
    POINT_VALUE = 2.0
else:
    POINT_VALUE = 1.0  # unscaled fallback for any other ticker

# Signal / filter / risk parameters
SWING_LOOKBACK = 20       # bars, for the swept swing high/low
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0
TREND_SMA = 50            # daily bars, for the HTF bias
SESSION_START = "09:30"
SESSION_END = "11:00"     # entry-scan window end (management runs later)

# Realistic trading friction - same corrected $5/trade figure as
# vwap_intraday.py / vwap_intraday_1h.py (see findings.md's cost-model
# correction).
ROUND_TRIP_COST_USD = 5.0
CONTRACTS = 1

# Concentration check: how many of the biggest winners to measure against
# gross profit.
TOP_N = 3

# --- 1-hour intraday data (trigger, VWAP, ATR, swing levels) ---
data = yf.download(ticker, period="730d", interval="1h")
data.columns = data.columns.get_level_values(0)

WINDOW_START = data.index[0]
WINDOW_END = data.index[-1]

# ATR(20) on the continuous 1-hour series - same True Range formula used
# throughout the track.
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

# Swing high/low over the PRIOR 20 bars - shift(1) excludes the current bar
# so a bar is never compared against a window that includes itself (no
# lookahead). Computed on the continuous series, so it can span day
# boundaries - see docstring.
data["SwingHigh"] = data["High"].rolling(window=SWING_LOOKBACK).max().shift(1)
data["SwingLow"] = data["Low"].rolling(window=SWING_LOOKBACK).min().shift(1)

# --- Daily data (higher-timeframe bias) ---
# Pulled separately over a much longer window so the 50-day SMA and the
# prior-day lookup are defined across the entire hourly range.
daily = yf.download(ticker, period="5y", interval="1d")
daily.columns = daily.columns.get_level_values(0)
daily["SMA50"] = daily["Close"].rolling(window=TREND_SMA).mean()

# Bias for each date = was the PRIOR completed daily close above its 50-day
# SMA. .shift(1) pushes each day's own close/SMA comparison forward one
# day, so the trade day uses only information that existed before it
# opened (no lookahead) - identical to multifactor_v1.py's trend filter.
daily_bias_up = (daily["Close"] > daily["SMA50"]).shift(1)
bias_up_by_date = {ts.date(): val for ts, val in daily_bias_up.items()}

# --- Pass 1: slice each day to the cash session and find the modal
# (complete-day) session length, so "incomplete day" is detected from the
# data itself rather than a hardcoded, resolution-specific time string
# (same approach as vwap_intraday_1h.py). ---
day_sessions = {}
for day, day_data in data.groupby(data.index.date):
    day_session = day_data.between_time("09:30", "16:00")
    # Drop any bar starting exactly at 16:00 - it covers 16:00-17:00, after
    # the cash session closes (only ever fires for MNQ's top-of-hour
    # aligned bars; QQQ's 9:30-aligned bars never hit 16:00).
    day_session = day_session[day_session.index.time != dtime(16, 0)]
    if day_session.empty:
        continue
    day_sessions[day] = day_session

session_length_counts = Counter(len(s) for s in day_sessions.values())
expected_bars_per_day = session_length_counts.most_common(1)[0][0]

trades = []
days_tested = 0                  # complete session + prior-day bias available
days_with_sweep_reclaim = 0      # bias-aligned sweep+reclaim happened at all
# (days actually traded == len(trades), i.e. also VWAP-aligned)

# --- Pass 2: run the four-factor setup on each complete day. ---
for day, session in day_sessions.items():
    if len(session) < expected_bars_per_day:
        print(f"{day}: Skipped - incomplete session "
              f"({len(session)}/{expected_bars_per_day} bars)")
        continue

    bias_up = bias_up_by_date.get(day)
    if bias_up is None or pd.isna(bias_up):
        print(f"{day}: Skipped - no prior-day HTF bias reading available")
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
    bias_up = bool(bias_up)
    bias_label = "bullish" if bias_up else "bearish"

    close = session["Close"]
    high = session["High"]
    low = session["Low"]
    atr_series = data["ATR"].reindex(session.index)
    swing_high_series = data["SwingHigh"].reindex(session.index)
    swing_low_series = data["SwingLow"].reindex(session.index)
    close_price = close.iloc[-1]

    entry_window = session.between_time(SESSION_START, SESSION_END)

    direction = None
    entry_price = None
    entry_time = None
    entry_atr = None
    swept = False           # tracks the sweep flag within the entry window
    reclaim_seen = False    # structural sweep+reclaim, regardless of VWAP

    for i in range(len(entry_window)):
        ts = entry_window.index[i]
        bar_high = high.loc[ts]
        bar_low = low.loc[ts]
        bar_close = close.loc[ts]
        s_high = swing_high_series.loc[ts]
        s_low = swing_low_series.loc[ts]
        v = vwap.loc[ts]
        atr = atr_series.loc[ts]

        if pd.isna(s_high) or pd.isna(s_low) or pd.isna(v) or pd.isna(atr):
            continue

        if bias_up:
            # LONG-only: sweep below swing_low, reclaim close back above it.
            if bar_low < s_low:
                swept = True
            if swept and bar_close > s_low:
                reclaim_seen = True
                if v > s_low:
                    direction = "LONG"
                    entry_price = bar_close
                    entry_time = ts
                    entry_atr = atr
                    break
        else:
            # SHORT-only: sweep above swing_high, reclaim close back below it.
            if bar_high > s_high:
                swept = True
            if swept and bar_close < s_high:
                reclaim_seen = True
                if v < s_high:
                    direction = "SHORT"
                    entry_price = bar_close
                    entry_time = ts
                    entry_atr = atr
                    break

    if reclaim_seen:
        days_with_sweep_reclaim += 1

    if direction is None:
        print(f"{day}: No qualifying entry ({bias_label} bias) - no trade")
        continue

    if direction == "LONG":
        stop_price = entry_price - STOP_MULT * entry_atr
        target_price = entry_price + TARGET_MULT * entry_atr
    else:
        stop_price = entry_price + STOP_MULT * entry_atr
        target_price = entry_price - TARGET_MULT * entry_atr

    exit_price = close_price
    exit_reason = "close"

    # Trade management runs over the FULL session, from the bar after entry
    # through the close. Intrabar high/low is used since a stop/target can
    # be touched mid-bar; if one bar spans both, the stop is assumed first.
    entry_idx = session.index.get_loc(entry_time)
    for j in range(entry_idx + 1, len(session)):
        bar = session.iloc[j]
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
    print(f"{day}: {direction} ({bias_label} bias) | "
          f"Entry = {entry_price:.2f} @ {entry_time.strftime('%H:%M')} | "
          f"Exit = {exit_price:.2f} ({exit_reason}) | ATR = {entry_atr:.2f} | "
          f"P/L = {pnl:+.2f} points")

# --- Summary ---
print("\n--- Summary ---")
print(f"Ticker: {ticker}  (interval: 1h)")
print(f"Data window: {WINDOW_START.date()} -> {WINDOW_END.date()} "
      f"({(WINDOW_END - WINDOW_START).days} calendar days)")
print(f"Expected bars/complete day: {expected_bars_per_day}")
print(f"Days tested: {days_tested}")

print("\nSelectivity funnel (per trading day, one trade/day max):")
print(f"  Complete session + HTF bias available:          {days_tested}")
print(f"  ...bias-aligned sweep+reclaim occurred at all:  {days_with_sweep_reclaim}")
print(f"  ...and VWAP-aligned (actually traded):          {len(trades)}")

print(f"\nTrades taken: {len(trades)}")
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
