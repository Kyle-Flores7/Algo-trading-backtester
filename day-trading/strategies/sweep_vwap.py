"""
STRATEGY: Liquidity Sweep + VWAP Confirmation (Sweep VWAP)
===========================================================

Concept:
`setup_v1.py` already tried pairing the sweep concept with VWAP, and the
result was a methodological dead end: the VWAP-alignment gate there
checked whether VWAP sat beyond the SWEPT LEVEL (a multi-day swing
high/low), and on that sample it did on effectively every single
qualifying sweep (146/146 MNQ, 109/109 QQQ) - the filter never actually
had a chance to veto anything, because a multi-day swing extreme being on
the far side of today's own VWAP is close to a geometric certainty, not a
market condition. That test could not tell us whether "VWAP confirmation"
helps, because it was never really being tested.

This script fixes the comparison by testing VWAP as a genuine PRICE-VS-
VWAP-AT-THE-RECLAIM-BAR filter instead of a level-vs-level one: does the
close that reclaims the swept level ALSO happen to be on the correct side
of today's VWAP at that exact moment? That is a real, frequently-false
condition (today's VWAP moves bar to bar and has no structural reason to
sit on one side or the other of a 20-bar swing level), so it can actually
filter something. Everything else is unchanged from `sweep_only.py` - same
20-bar swing sweep+reclaim trigger, same full-session scan (no 9:30-11:00
restriction), same multiple-trades-per-day handling, same ATR-based
1.5x/2.0x risk - so any difference in the results is attributable to the
VWAP filter alone, not to some other simplification changing at the same
time.

Logic
-----
1. **Sweep + reclaim trigger - identical to `sweep_only.py`.** Rolling
   20-bar swing high/low (continuous series, shift(1), no lookahead); a
   bar's Low/High breaking past it arms a sweep; a later close back inside
   the level within SWEEP_EXPIRY_BARS (5 bars / 25 minutes) is a raw
   sweep+reclaim signal, LONG or SHORT. See `sweep_only.py`'s docstring
   for the full reasoning behind these choices - none of it changed here.

2. **VWAP confirmation - the new, real filter.** VWAP is computed exactly
   like every other VWAP script in this track: reset at 9:30 each day,
   typical_price = (High+Low+Close)/3, cumulative volume-weighted. A raw
   sweep+reclaim signal is only taken as a trade if the RECLAIM BAR'S
   CLOSE is on the correct side of VWAP at that same bar:
     - LONG (reclaimed above swept low): only taken if Close > VWAP too.
     - SHORT (reclaimed above swept high): only taken if Close < VWAP too.
   A raw signal that fails this check is discarded outright (not queued,
   not retried) - the sweep is consumed either way, so a rejected signal
   requires a brand-new sweep to re-arm, same as an expired one.

3. **Selectivity funnel - reported before the trade-by-trade backtest
   detail, exactly to confirm this filter is real** (unlike setup_v1.py's).
   Every raw sweep+reclaim is counted whether or not it passes the VWAP
   check, so the summary can show what fraction actually got filtered
   out - if that fraction were still ~100% pass, this would be repeating
   setup_v1.py's mistake instead of fixing it.

4. **Risk / exits / costs / multiple-trades-per-day - unchanged from
   `sweep_only.py`.** ATR(20) 1.5x stop / 2.0x target, whichever of stop /
   target / 4:00 PM ET close comes first (stop assumed first if a bar
   spans both), $5/trade round-trip cost, one position open at a time,
   scanning resumes the bar after an exit for the rest of the session.

What was deliberately simplified
---------------------------------
- **VWAP is computed on the cash session only** (reset at 9:30, unlike the
  swing high/low and ATR, which stay on the continuous series per
  `sweep_only.py`'s precedent) - this is not a new choice, it is how VWAP
  is computed in every VWAP script in this track (`vwap_intraday.py`
  onward): VWAP is explicitly a today-only average, not a multi-day
  structure level, so resetting it at the open is the correct behavior,
  not an inconsistency with the swing/ATR series being continuous.
- **A day with zero volume data is skipped** (VWAP is undefined without
  volume) - same handling as every other VWAP script.

Costs
-----
Gross P/L is reported first, then the same $5/trade round-trip cost as
the rest of the track, so the summary states whether the VWAP-filtered
signal is still net profitable once friction is paid.

This is intraday, not daily, data - each day is tested independently, not
as one continuous equity curve. backtest.py's run_backtest() assumes one
row per day and can't be reused here, so P/L is tracked manually.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request - the same window `sweep_only.py` and every other 5-minute script
in this track uses.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100) but can be overridden,
# e.g. `python sweep_vwap.py QQQ`.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"

# Dollar multiplier per ticker - MNQ is $2/index point; QQQ uses the same
# MNQ-notional-matched 82-share position setup_v1.py / sweep_only.py used,
# so the dollar comparison stays apples-to-apples with the futures baseline.
if ticker == "QQQ":
    POINT_VALUE = 82.0
elif ticker == "MNQ=F":
    POINT_VALUE = 2.0
else:
    POINT_VALUE = 1.0  # unscaled fallback for any other ticker

# Signal / risk parameters - identical to sweep_only.py
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
# that includes itself (no lookahead). See sweep_only.py's docstring for
# why this is left continuous (can span day boundaries / overnight bars)
# rather than reset per day.
data["SwingHigh"] = data["High"].rolling(window=SWING_LOOKBACK).max().shift(1)
data["SwingLow"] = data["Low"].rolling(window=SWING_LOOKBACK).min().shift(1)

trades = []
days_tested = 0
raw_signals = 0    # sweep+reclaim happened, regardless of VWAP
passed_signals = 0  # ...and also VWAP-confirmed (== len(trades))

for day, day_data in data.groupby(data.index.date):
    # Restrict to the 9:30 AM - 4:00 PM ET cash session up front so
    # overnight bars (futures) never trigger an entry or exit directly -
    # they can still shape the swing levels/ATR feeding INTO the session,
    # per sweep_only.py's docstring.
    day_session = day_data.between_time("09:30", "16:00")
    if day_session.empty:
        continue

    # Skip the current/incomplete trading day - a finished session's last
    # 5-minute bar is 15:55 (covers 15:55-16:00).
    if day_session.index[-1].time() < pd.Timestamp("15:55").time():
        print(f"{day}: Skipped - incomplete session (in progress)")
        continue

    session = day_session.between_time("09:30", "15:55")

    # --- VWAP for this day only, reset at 9:30 ---
    typical_price = (session["High"] + session["Low"] + session["Close"]) / 3
    volume = session["Volume"]
    cum_volume = volume.cumsum()
    if cum_volume.iloc[-1] == 0:
        print(f"{day}: Skipped - no volume data for VWAP")
        continue
    vwap = (typical_price * volume).cumsum() / cum_volume

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
        v = vwap.loc[ts]

        if pd.isna(s_high) or pd.isna(s_low) or pd.isna(atr) or pd.isna(v):
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

        raw_direction = None
        if swept_below and bar_close > swept_below_level:
            raw_direction = "LONG"
        elif swept_above and bar_close < swept_above_level:
            raw_direction = "SHORT"

        if raw_direction is None:
            idx += 1
            continue

        # A raw sweep+reclaim happened - consume both armed sweeps either
        # way (accepted or rejected), so a rejected signal needs a fresh
        # sweep to re-arm rather than re-testing the same reclaim forever.
        raw_signals += 1
        swept_below = False
        swept_above = False

        passes_vwap = (
            (raw_direction == "LONG" and bar_close > v)
            or (raw_direction == "SHORT" and bar_close < v)
        )

        if not passes_vwap:
            idx += 1
            continue

        passed_signals += 1
        direction = raw_direction

        entry_price = bar_close
        entry_atr = atr
        entry_time = ts
        entry_vwap = v

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
              f"{entry_time.strftime('%H:%M')} (VWAP {entry_vwap:.2f}) | "
              f"Exit = {exit_price:.2f} ({exit_reason}) | ATR = {entry_atr:.2f} "
              f"| P/L = {pnl:+.2f} points")

        # Resume scanning flat, from the bar after this trade's exit.
        idx = exit_idx + 1

    if day_trade_count == 0:
        print(f"{day}: No VWAP-confirmed sweep+reclaim signal - no trade")

# --- Summary ---
print("\n--- Summary ---")
print(f"Ticker: {ticker}")
print(f"Days tested: {days_tested}")

print("\nSelectivity funnel (VWAP as a real filter, not a rubber stamp):")
print(f"  Raw sweep+reclaim signals (any direction):      {raw_signals}")
if raw_signals:
    print(f"  ...passed VWAP confirmation (actually traded):  {passed_signals} "
          f"({passed_signals / raw_signals:.0%})")
else:
    print("  ...passed VWAP confirmation (actually traded):  0")

print(f"\nTrades taken: {len(trades)}")
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
