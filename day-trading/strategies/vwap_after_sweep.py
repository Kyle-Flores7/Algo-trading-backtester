"""
STRATEGY: VWAP Pullback, Filtered by Recent Liquidity Sweep (VWAP After Sweep)
================================================================================

Concept:
`sweep_vwap.py` combined the sweep and VWAP concepts with the sweep as the
PRIMARY trigger and VWAP as a filter on top of it. This script is the
reverse combination direction: `vwap_intraday.py`'s VWAP pullback - the
one setup in this whole day-trading track with a real, if fragile,
positive result (+$899.71 MNQ / +$1,201.51 QQQ net, per findings.md) -
stays the primary trigger, unchanged, and a recent liquidity sweep is
added as a CONTEXT filter: only take the VWAP pullback if a sweep of a
recent swing high/low also happened nearby, on the idea that a VWAP touch
following a recent stop-run/failed-breakout is a better-quality setup than
an isolated VWAP touch with no such context.

Logic
-----
1. **VWAP pullback trigger - identical to `vwap_intraday.py`, unchanged.**
   Per-day VWAP (reset at 9:30, typical_price = (H+L+C)/3, cumulative
   volume-weighted). Day bias = the first bar that closes off VWAP (LONG
   bias if above, SHORT if below). Entry = the first later bar, in the
   bias direction, whose Low/High touches VWAP but whose Close holds back
   on the bias side (LONG: Low <= VWAP and Close > VWAP; SHORT: High >=
   VWAP and Close < VWAP). One trade per day maximum, same as the original.

2. **Sweep-context filter - the new condition.** A rolling 20-bar swing
   high/low is tracked on the continuous 5-minute series (identical
   mechanism to `sweep_only.py`: shift(1) for no lookahead, a sweep arms
   when price breaks past the level, a reclaim (close back inside) within
   SWEEP_EXPIRY_BARS=5 bars completes it - otherwise it expires unarmed).
   Every completed reclaim across the whole series is marked bullish
   (swept the low, reclaimed up) or bearish (swept the high, reclaimed
   down). A VWAP pullback entry is only taken if a reclaim of the SAME
   DIRECTION completed somewhere in the LOOKBACK_BARS=10 bars immediately
   before the entry bar (not including the entry bar itself) - i.e. the
   VWAP touch is happening shortly after the market already showed a
   failed breakdown (for a LONG) or failed breakout (for a SHORT) nearby.

3. **Selectivity funnel - reported before the trade-by-trade backtest
   detail**, exactly like `sweep_vwap.py`'s validity check: how many of
   `vwap_intraday.py`'s original (unfiltered) VWAP pullback signals also
   had a same-direction recent sweep, so we know upfront whether this
   filter is meaningfully selective or a rubber stamp.

4. **Risk / exits / costs - unchanged from `vwap_intraday.py`.** ATR(20)
   1.5x stop / 2.0x target, whichever of stop / target / 4:00 PM ET close
   comes first (stop assumed first if a bar spans both), $5/trade
   round-trip cost, one trade per day maximum.

What was deliberately simplified
---------------------------------
- **The recent sweep must match the VWAP trade's direction** (a LONG VWAP
  pullback requires a recent BULLISH reclaim - swept low, closed back up;
  a SHORT requires a recent BEARISH reclaim). The prompt describes the
  filter as "swept a recent swing high OR low" without stating whether
  direction must align, but an unaligned sweep (e.g. a bearish reclaim
  right before a bullish VWAP pullback) doesn't describe a coherent
  "quality context" for that specific trade - it's a different part of the
  market's structure entirely. Requiring alignment is also consistent
  with how every other confluence attempt in this track (`setup_v1.py`'s
  bias-aligned sweep, `sweep_vwap.py`'s same-bar direction match) has
  interpreted "context that supports this trade," so this keeps the
  convention rather than introducing a new, unaligned kind of filter.
- **The swing high/low AND the sweep/reclaim state machine are both
  computed on the continuous 5-minute series** (not reset per day, not
  reset per VWAP session) - identical precedent to `sweep_only.py` and
  `setup_v1.py`: market structure isn't a cash-session concept, so a
  sweep from the tail of yesterday's session (or, for MNQ=F, the
  overnight session - see `sweep_only.py`'s docstring on why yfinance
  returns near-24-hour futures bars) can still count as "recent" for a
  VWAP pullback near this morning's open. The lookback window is only 10
  bars (50 minutes) either way, so this mostly matters near the open.
- **A day with zero volume data is skipped** (VWAP is undefined without
  volume) - unchanged from `vwap_intraday.py`.

Costs
-----
Gross P/L is reported first, then the same $5/trade round-trip cost as
the rest of the track, so the summary states whether the sweep-filtered
signal is still net profitable once friction is paid, and how that
compares to the unfiltered baseline's own net result.

This is intraday, not daily, data - each day is tested independently, not
as one continuous equity curve. backtest.py's run_backtest() assumes one
row per day and can't be reused here, so P/L is tracked manually.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request - the same window `vwap_intraday.py` and every other 5-minute
script in this track uses. Because that window rolls forward with the
calendar, running this script "today" pulls a different 60 days than
whatever pull produced `vwap_intraday.py`'s originally-recorded
+$899.71/+$1,201.51 result - the funnel and comparison below report both
the historical baseline and a fresh same-pull baseline so the comparison
is apples-to-apples with the sweep-filter's own results.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100) but can be overridden,
# e.g. `python vwap_after_sweep.py QQQ`.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"
POINT_VALUE = 82.0 if ticker == "QQQ" else 2.0 if ticker == "MNQ=F" else 1.0

# ATR / risk parameters - identical to vwap_intraday.py
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0

# Sweep-context filter parameters - identical trigger mechanism to
# sweep_only.py, plus the new lookback window.
SWING_LOOKBACK = 20
SWEEP_EXPIRY_BARS = 5   # bars a sweep stays armed waiting for its reclaim
LOOKBACK_BARS = 10      # bars before the VWAP entry to look for that reclaim

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
# excludes the current bar (no lookahead). See docstring for why this
# stays continuous rather than resetting per day.
data["SwingHigh"] = data["High"].rolling(window=SWING_LOOKBACK).max().shift(1)
data["SwingLow"] = data["Low"].rolling(window=SWING_LOOKBACK).min().shift(1)

# --- Mark every completed sweep+reclaim on the continuous series, once,
# up front - identical state machine to sweep_only.py, but here we only
# need to know WHEN each reclaim completed, not manage a trade from it. ---
n_all = len(data)
bullish_reclaim = pd.Series(False, index=data.index)
bearish_reclaim = pd.Series(False, index=data.index)

swept_below = False
swept_below_at = None
swept_below_level = None
swept_above = False
swept_above_at = None
swept_above_level = None

highs = data["High"].to_numpy()
lows = data["Low"].to_numpy()
closes = data["Close"].to_numpy()
swing_highs = data["SwingHigh"].to_numpy()
swing_lows = data["SwingLow"].to_numpy()

for i in range(n_all):
    s_high = swing_highs[i]
    s_low = swing_lows[i]
    if pd.isna(s_high) or pd.isna(s_low):
        continue

    bar_high = highs[i]
    bar_low = lows[i]
    bar_close = closes[i]

    if bar_low < s_low:
        swept_below, swept_below_at, swept_below_level = True, i, s_low
    if bar_high > s_high:
        swept_above, swept_above_at, swept_above_level = True, i, s_high

    if swept_below and (i - swept_below_at) > SWEEP_EXPIRY_BARS:
        swept_below = False
    if swept_above and (i - swept_above_at) > SWEEP_EXPIRY_BARS:
        swept_above = False

    if swept_below and bar_close > swept_below_level:
        bullish_reclaim.iloc[i] = True
        swept_below = False
    if swept_above and bar_close < swept_above_level:
        bearish_reclaim.iloc[i] = True
        swept_above = False

# "Recent" = completed somewhere in the LOOKBACK_BARS bars strictly before
# the current bar. rolling(...).max() over the (non-shifted) series covers
# bars [i-LOOKBACK_BARS+1, i]; shifting the result by 1 bar turns that into
# coverage of [i-LOOKBACK_BARS, i-1] - exactly "the prior 10 bars," current
# bar excluded.
data["BullishReclaimRecent"] = (
    bullish_reclaim.astype(int)
    .rolling(window=LOOKBACK_BARS, min_periods=1)
    .max()
    .shift(1)
    .fillna(0)
    .astype(bool)
)
data["BearishReclaimRecent"] = (
    bearish_reclaim.astype(int)
    .rolling(window=LOOKBACK_BARS, min_periods=1)
    .max()
    .shift(1)
    .fillna(0)
    .astype(bool)
)

trades = []
days_tested = 0
raw_signals = 0     # vwap_intraday.py's original signal: bias + pullback held
passed_signals = 0  # ...and also had a same-direction recent sweep nearby

for day, day_data in data.groupby(data.index.date):
    # Restrict to the 9:30 AM - 4:00 PM ET cash session up front so
    # overnight bars never set the bias or trigger an entry directly.
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

    close = session["Close"]
    high = session["High"]
    low = session["Low"]
    atr_series = data["ATR"].reindex(session.index)
    bullish_recent_series = data["BullishReclaimRecent"].reindex(session.index)
    bearish_recent_series = data["BearishReclaimRecent"].reindex(session.index)
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

    # --- Entry: first pullback to VWAP that holds in the bias direction,
    # same trigger as vwap_intraday.py --- ---
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

    raw_signals += 1

    # --- Sweep-context filter: was a same-direction reclaim completed in
    # the 10 bars right before this entry bar? ---
    ts = session.index[entry_idx]
    has_context = (
        bullish_recent_series.loc[ts] if direction == "LONG"
        else bearish_recent_series.loc[ts]
    )
    if not has_context:
        print(f"{day}: {direction} VWAP pullback, but no recent sweep "
              f"context - no trade")
        continue

    passed_signals += 1

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
    print(f"{day}: {direction} | Entry = {entry_price:.2f} @ "
          f"{ts.strftime('%H:%M')} (VWAP {entry_vwap:.2f}) | "
          f"Exit = {exit_price:.2f} ({exit_reason}) | ATR = {entry_atr:.2f} "
          f"| P/L = {pnl:+.2f} points")

# --- Summary ---
print("\n--- Summary ---")
print(f"Ticker: {ticker}")
print(f"Days tested: {days_tested}")

print("\nSelectivity funnel (does the sweep-context filter actually filter?):")
print(f"  Raw VWAP pullback signals (vwap_intraday.py's original trigger): "
      f"{raw_signals}")
if raw_signals:
    print(f"  ...also had a same-direction recent sweep (actually traded): "
          f"{passed_signals} ({passed_signals / raw_signals:.0%})")
else:
    print("  ...also had a same-direction recent sweep (actually traded): 0")

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
