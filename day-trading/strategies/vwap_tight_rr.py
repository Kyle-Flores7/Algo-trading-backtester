"""
STRATEGY: VWAP Pullback - Tighter Risk/Reward (VWAP Tight RR)
===========================================================

Same signal as vwap_intraday.py - per-day VWAP, first bar closing off VWAP
sets the bias, entry on the first pullback bar that touches VWAP and closes
back on the bias side. The ONLY change is the exit geometry:

    vwap_intraday.py :  1.5x ATR stop  /  2.0x ATR target   (R:R 1 : 1.33)
    this file        :  1.0x ATR stop  /  1.5x ATR target   (R:R 1 : 1.5)

Why try it
----------
vwap_intraday.py wins 51% of trades but still finishes at -$80.29 after
the $25/trade cost model. A 51% win rate with a 1.33 reward-to-risk target
should be comfortably profitable before costs and roughly break-even after
- so the fact that it barely clears zero gross suggests trades are moving
in favour, then giving the gain back before price travels the full 2x ATR
to the target. Many "winners" are really just 4:00 PM time-stop exits
banking a fraction of the intended move.

Pulling the target in to 1.5x ATR asks for less follow-through, so a move
that stalls halfway can still register as a clean target hit instead of
decaying into a small time-stop win or a scratch. Tightening the stop to
1.0x ATR keeps the per-trade risk unit smaller to match. Net effect on the
ratio: 1 : 1.5 is actually a slightly BETTER reward-to-risk than the
original 1 : 1.33, while requiring less favourable travel to get paid.

The trade-off: a 1.0x ATR stop sits closer to entry, so normal noise
around VWAP will stop some trades out that the 1.5x stop would have let
recover. Whether the easier target outweighs the tighter stop is the
whole question - hence this backtest.

Everything else is identical to vwap_intraday.py:
  - Per-day VWAP reset at 9:30, typical_price = (H+L+C)/3.
  - First cash-session bar closing off VWAP sets LONG-only / SHORT-only
    bias; entry on the first pullback bar that touches VWAP and closes
    back on the bias side.
  - 20-bar ATR risk unit. Exit is whichever of stop / target / 16:00 ET
    close comes first. Stop assumed first if one bar spans both. No
    overnight positions. One trade per day maximum.
  - 9:30 AM - 4:00 PM ET cash session only; incomplete final day skipped;
    zero-volume days skipped.
  - Flat $25 round-trip cost per trade (commission + slippage, one MNQ
    contract). Gross P/L reported first, then net after costs.

The summary prints every metric next to vwap_intraday.py's 1.5x/2x
baseline (+572.36 pts gross, -40.14 after costs, 51% win rate, 49 trades)
so the effect of the ratio change is visible directly.

This is intraday, not daily, data - each day is tested independently, not
as one continuous equity curve, so backtest.py's run_backtest() is not
reused and P/L is tracked manually.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request. VWAP needs volume; if a day's bars carry no volume, that day is
skipped.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100). Dollar P/L assumes
# MNQ's $2 per index point (0.25-point tick = $0.50/tick -> $2/point).
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"
POINT_VALUE = 2.0  # USD per index point, MNQ=F

# ATR / risk parameters. Tighter geometry than vwap_intraday.py's 1.5 / 2.0:
# a closer stop and a nearer target that needs less follow-through to hit.
ATR_PERIOD = 20
STOP_MULT = 1.0
TARGET_MULT = 1.5

# Realistic trading friction: commission + slippage for ONE MNQ contract,
# charged once per completed round-trip trade (enter + exit). $25 is a
# reasonable all-in estimate - roughly $1-2 commission per side plus a
# tick or two of slippage per side (0.25-pt tick = $0.50 on MNQ). At
# $2/point this is 12.5 points a trade.
ROUND_TRIP_COST_USD = 25.0

# vwap_intraday.py's 1.5x/2x result in the same 60-day window, for a direct
# comparison in the summary.
BASELINE_GROSS_POINTS = 572.36
BASELINE_NET_POINTS = -40.14
BASELINE_WIN_RATE = 0.51
BASELINE_TRADES = 49

# Concentration check: how many of the biggest winners to measure against
# gross profit.
TOP_N = 3

data = yf.download(ticker, period="60d", interval="5m")
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

# ATR(20) on the continuous 5-minute series - the risk unit, same as
# vwap_intraday.py. True Range = the largest of this bar's high-low,
# |high - prev close|, |low - prev close|.
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

trades = []
days_tested = 0

for day, day_data in data.groupby(data.index.date):
    # Restrict to the 9:30 AM - 4:00 PM ET cash session up front so
    # overnight bars never set the bias or trigger an entry.
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
print(f"Ticker: {ticker}")
print(f"Risk/reward: {STOP_MULT}x ATR stop / {TARGET_MULT}x ATR target "
      f"(vwap_intraday.py baseline: 1.5x / 2.0x)")
print(f"Days tested: {days_tested}")
print(f"Trades taken: {len(trades)}  (baseline: {BASELINE_TRADES})")
if trades:
    total_pnl = sum(trades)
    winners = sorted([p for p in trades if p > 0], reverse=True)
    losers = [p for p in trades if p < 0]
    win_rate = len(winners) / len(trades)

    print(f"Total P/L: {total_pnl:+.2f} points  "
          f"(${total_pnl * POINT_VALUE:+,.2f} at ${POINT_VALUE:.0f}/point)")
    print(f"Win rate: {len(winners)}/{len(trades)} ({win_rate:.0%})")
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
    # Everything above is gross (frictionless). Subtract a flat round-trip
    # cost per trade to see what is actually left.
    cost_points = ROUND_TRIP_COST_USD / POINT_VALUE
    total_cost_usd = len(trades) * ROUND_TRIP_COST_USD

    gross_points = total_pnl
    gross_usd = total_pnl * POINT_VALUE
    net_points = gross_points - len(trades) * cost_points
    net_usd = gross_usd - total_cost_usd

    print("\n--- Cost adjustment (commission + slippage) ---")
    print(f"Assumed round-trip cost: ${ROUND_TRIP_COST_USD:,.2f} per trade "
          f"({cost_points:.2f} points)")
    print(f"Total cost: {len(trades)} trades x ${ROUND_TRIP_COST_USD:,.2f} "
          f"= ${total_cost_usd:,.2f}")
    print()
    print(f"{'':<22}{'1.0x / 1.5x':>16}{'1.5x / 2.0x base':>18}")
    print(f"{'P/L pts (gross)':<22}{gross_points:>+16.2f}"
          f"{BASELINE_GROSS_POINTS:>+18.2f}")
    print(f"{'P/L pts (net)':<22}{net_points:>+16.2f}"
          f"{BASELINE_NET_POINTS:>+18.2f}")
    print(f"{'P/L USD (gross)':<22}{gross_usd:>+16,.2f}"
          f"{BASELINE_GROSS_POINTS * POINT_VALUE:>+18,.2f}")
    print(f"{'P/L USD (net)':<22}{net_usd:>+16,.2f}"
          f"{BASELINE_NET_POINTS * POINT_VALUE:>+18,.2f}")
    print(f"{'Win rate':<22}{win_rate:>15.0%}{BASELINE_WIN_RATE:>17.0%} ")
    print(f"{'Trades':<22}{len(trades):>16d}{BASELINE_TRADES:>18d}")
    print(f"{'Net profitable?':<22}{'YES' if net_usd > 0 else 'NO':>16}"
          f"{'NO':>18}")
