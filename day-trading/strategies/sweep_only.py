"""
STRATEGY: Liquidity Sweep - Standalone (Sweep Only)
====================================================

Concept:
Every prior test of the liquidity-sweep idea in this project has combined
it with at least one other condition:
  - orb_sweep.py / orb_sweep_confirmed.py / orb_sweep_futures.py fade a
    sweep of the OPENING RANGE (9:30-9:45), always inside that specific
    session window, with an opening-range-width stop/target.
  - setup_v1.py sweeps a rolling 20-bar swing high/low (the same structural
    level used here) but only inside a 9:30-11:00 entry window, gated on a
    daily 50-SMA higher-timeframe bias AND a VWAP-alignment filter on top.
Across all of those, we have never isolated the raw claim "a sweep of a
recent swing level, followed by a close back inside it, is itself an edge."
This script strips every other condition away - no session filter (scans
the entire 9:30 AM-4:00 PM ET cash session, not just the open), no trend/
bias filter (either direction is considered on every bar, every day), no
VWAP, no RSI - so we can finally see whether the sweep-and-reclaim pattern
means anything on its own before it gets combined with anything else again.

Logic
-----
1. **Swing level.** Rolling 20-bar high/low computed on the continuous
   5-minute series (same approach as setup_v1.py's SwingHigh/SwingLow -
   see "What was deliberately simplified" below for why this is continuous
   rather than reset per day), shifted by 1 bar so the current bar is
   compared only against the PRIOR 20 bars (no lookahead).

2. **Sweep.** A bar's Low trades below the rolling 20-bar low ("sweeps" it)
   or a bar's High trades above the rolling 20-bar high. Both directions
   are tracked independently and can be "armed" at the same time.

3. **Reclaim -> entry.** LONG: after a below-sweep, the first later bar (or
   the same bar) that CLOSES back above the swept low, within
   SWEEP_EXPIRY_BARS bars of the sweep, triggers a LONG entry at that
   close. SHORT is the mirror image: after an above-sweep, a close back
   below the swept high within the expiry window triggers a SHORT entry.
   If the expiry window passes with no reclaim, that armed sweep is
   discarded - price would have to sweep the level again to re-arm it.

4. **Multiple trades per day.** Since there is no session-window
   restriction this time, one trade per SIGNAL is taken (not one per day):
   once a trade's stop/target/close exits, scanning resumes on the very
   next bar for a fresh sweep+reclaim, for the rest of the session. Only
   one position is open at a time - no new entry is considered while a
   trade is still being managed.

5. **Risk / exits - unchanged plumbing from vwap_intraday.py.** Risk unit
   is the recent 20-bar ATR: 1.5x ATR stop against the trade, 2x ATR
   target in favor. Exit priority is whichever of stop / target / 4:00 PM
   ET close comes first; if one 5-minute bar's range spans both stop and
   target, the stop is assumed to hit first (conservative - 5-minute OHLC
   can't show the intrabar order).

What was deliberately simplified
---------------------------------
- **"Within the next few bars"** (from the sweep concept as worded) is
  implemented as a hard SWEEP_EXPIRY_BARS = 5 bar (25-minute) window
  between the sweep and its reclaim. Without a bound, an old, once-swept
  level could get "reclaimed" hours later by an unrelated move and be
  counted as a signal that has nothing to do with the original sweep -
  5 bars keeps the pattern a tight, structural failed-breakout/breakdown
  rather than an open-ended flag.
- **The swing high/low is computed on the continuous 5-minute series**. For
  MNQ=F this series is not the cash session; yfinance returns near-24-hour
  futures bars (see pull check below), so the rolling 20-bar window can
  include the overnight session, exactly like setup_v1.py's SwingHigh/
  SwingLow on its 1-hour series. This isn't a bug worth engineering around
  here: a swing structure level is a market-structure concept, not a
  cash-session concept, and futures traders do not reset it at 9:30. For
  QQQ, which yfinance only returns cash-session bars for, this reduces to
  a plain intraday rolling structure level. ATR is computed the same way
  (continuous series), matching every other script in this track.
- **Sweep/reclaim state resets each new trading day** (the state MACHINE,
  not the swing levels themselves) - an armed-but-unreclaimed sweep from
  the end of one day does not carry into the next day's scan.

Costs
-----
Gross P/L is reported first, then a flat $5 round-trip cost per contract
(the corrected, real-broker-rate-card figure - see findings.md) is
subtracted so the summary shows a before/after and states whether the
raw signal is still net profitable once friction is paid - and, since
signals can fire many times a day here, friction has many more chances to
matter than in any prior single-trade-per-day script in this track.

This is intraday, not daily, data - each day is tested independently, not
as one continuous equity curve. backtest.py's run_backtest() assumes one
row per day and can't be reused here, so P/L is tracked manually.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request - the same window every other 5-minute script in this track uses.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100) but can be overridden,
# e.g. `python sweep_only.py QQQ`.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"

# Dollar multiplier per ticker - MNQ is $2/index point; QQQ uses the same
# MNQ-notional-matched 82-share position setup_v1.py / vwap_intraday_1h.py
# used, so the dollar comparison stays apples-to-apples with the futures
# baseline.
if ticker == "QQQ":
    POINT_VALUE = 82.0
elif ticker == "MNQ=F":
    POINT_VALUE = 2.0
else:
    POINT_VALUE = 1.0  # unscaled fallback for any other ticker

# Signal / risk parameters
SWING_LOOKBACK = 20     # bars, for the rolling swept swing high/low
SWEEP_EXPIRY_BARS = 5   # bars a sweep stays "armed" waiting for a reclaim
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0

# Realistic trading friction - same corrected $5/trade figure as every
# other script in this track (see findings.md's cost-model correction).
ROUND_TRIP_COST_USD = 5.0
CONTRACTS = 1

# Concentration check: how many of the biggest winners to measure against
# gross profit.
TOP_N = 3

data = yf.download(ticker, period="60d", interval="5m")
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

# ATR(20) on the continuous 5-minute series - same True Range formula used
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

# Rolling 20-bar swing high/low on the same continuous series - shift(1)
# excludes the current bar so a bar is never compared against a window
# that includes itself (no lookahead). See docstring for why this is left
# continuous (can span day boundaries / overnight bars) rather than reset
# per day.
data["SwingHigh"] = data["High"].rolling(window=SWING_LOOKBACK).max().shift(1)
data["SwingLow"] = data["Low"].rolling(window=SWING_LOOKBACK).min().shift(1)

trades = []
days_tested = 0

for day, day_data in data.groupby(data.index.date):
    # Restrict to the 9:30 AM - 4:00 PM ET cash session up front so
    # overnight bars (futures) never trigger an entry or exit directly -
    # they can still shape the swing levels/ATR feeding INTO the session,
    # per the docstring.
    day_session = day_data.between_time("09:30", "16:00")
    if day_session.empty:
        continue

    # Skip the current/incomplete trading day - a finished session's last
    # 5-minute bar is 15:55 (covers 15:55-16:00).
    if day_session.index[-1].time() < pd.Timestamp("15:55").time():
        print(f"{day}: Skipped - incomplete session (in progress)")
        continue

    session = day_session.between_time("09:30", "15:55")

    days_tested += 1

    high = session["High"]
    low = session["Low"]
    close = session["Close"]
    swing_high_series = data["SwingHigh"].reindex(session.index)
    swing_low_series = data["SwingLow"].reindex(session.index)
    atr_series = data["ATR"].reindex(session.index)
    close_price = close.iloc[-1]

    n = len(session)
    day_trade_count = 0

    swept_below = False
    swept_below_at = None
    swept_below_level = None
    swept_above = False
    swept_above_at = None
    swept_above_level = None

    idx = 0
    while idx < n:
        ts = session.index[idx]
        s_high = swing_high_series.loc[ts]
        s_low = swing_low_series.loc[ts]
        atr = atr_series.loc[ts]

        if pd.isna(s_high) or pd.isna(s_low) or pd.isna(atr):
            idx += 1
            continue

        bar_high = high.loc[ts]
        bar_low = low.loc[ts]
        bar_close = close.loc[ts]

        if bar_low < s_low:
            swept_below, swept_below_at, swept_below_level = True, idx, s_low
        if bar_high > s_high:
            swept_above, swept_above_at, swept_above_level = True, idx, s_high

        if swept_below and (idx - swept_below_at) > SWEEP_EXPIRY_BARS:
            swept_below = False
        if swept_above and (idx - swept_above_at) > SWEEP_EXPIRY_BARS:
            swept_above = False

        direction = None
        if swept_below and bar_close > swept_below_level:
            direction = "LONG"
        elif swept_above and bar_close < swept_above_level:
            direction = "SHORT"

        if direction is None:
            idx += 1
            continue

        # Signal fires - consume both armed sweeps and enter.
        swept_below = False
        swept_above = False

        entry_price = bar_close
        entry_atr = atr
        entry_time = ts

        if direction == "LONG":
            stop_price = entry_price - STOP_MULT * entry_atr
            target_price = entry_price + TARGET_MULT * entry_atr
        else:
            stop_price = entry_price + STOP_MULT * entry_atr
            target_price = entry_price - TARGET_MULT * entry_atr

        exit_price = close_price
        exit_reason = "close"
        exit_idx = n - 1

        # Manage forward bar-by-bar using intrabar high/low. If one bar
        # spans both stop and target, the stop is assumed first.
        for j in range(idx + 1, n):
            bar = session.iloc[j]
            if direction == "LONG":
                if bar["Low"] <= stop_price:
                    exit_price, exit_reason, exit_idx = stop_price, "stop", j
                    break
                elif bar["High"] >= target_price:
                    exit_price, exit_reason, exit_idx = target_price, "target", j
                    break
            else:
                if bar["High"] >= stop_price:
                    exit_price, exit_reason, exit_idx = stop_price, "stop", j
                    break
                elif bar["Low"] <= target_price:
                    exit_price, exit_reason, exit_idx = target_price, "target", j
                    break

        if direction == "LONG":
            pnl = exit_price - entry_price
        else:
            pnl = entry_price - exit_price

        trades.append(pnl)
        day_trade_count += 1
        print(f"{day}: {direction} | Entry = {entry_price:.2f} @ "
              f"{entry_time.strftime('%H:%M')} | Exit = {exit_price:.2f} "
              f"({exit_reason}) | ATR = {entry_atr:.2f} | P/L = {pnl:+.2f} points")

        # Resume scanning flat, from the bar after this trade's exit.
        idx = exit_idx + 1

    if day_trade_count == 0:
        print(f"{day}: No sweep-and-reclaim signal - no trade")

# --- Summary ---
print("\n--- Summary ---")
print(f"Ticker: {ticker}")
print(f"Days tested: {days_tested}")
print(f"Trades taken: {len(trades)}")
if days_tested:
    print(f"Average trades/day: {len(trades) / days_tested:.2f}")

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
        n_top = min(TOP_N, len(winners))
        top_n_share = sum(winners[:n_top]) / gross_profit
        print(f"Concentration: top {n_top} winner(s) = {top_n_share:.0%} of "
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
