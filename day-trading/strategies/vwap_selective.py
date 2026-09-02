"""
STRATEGY: VWAP Pullback - Volume-Confirmed (VWAP Selective)
=========================================================

A more selective variation of vwap_intraday.py.

vwap_intraday.py takes a trade on essentially every day - 49 trades over
49 days in the 60-day sample. Its entry is a single 5-minute bar that both
touches VWAP and closes back on the bias side. That fires almost any time
price wobbles around VWAP, whether the wobble is a real pause-and-resume
or just noise on the way through.

This version keeps the exact same VWAP support/resistance concept and adds
a two-bar volume filter to demand that the pullback actually *looks* like
a pause followed by conviction, not a drift-through:

  - **Pullback bar** (the bar that touches / crosses VWAP): must trade on
    BELOW-average volume. A genuine pause - participants stepping back and
    letting price ease into the level - shows up as thin volume. Heavy
    volume into VWAP is a breakdown / breakout attempt, not a pause, so
    those are rejected.

  - **Confirmation bar** (the very next bar, which must close back on the
    bias side): must trade on ABOVE-average volume. Real conviction
    returning - the side that was in control stepping back in at the level
    - shows up as a volume surge on the bar that reclaims VWAP.

"Average" is a 20-bar rolling mean of 5-minute volume, computed on the
continuous series exactly like the 20-bar ATR. Both volume conditions must
hold or the setup is skipped and the walk-forward continues looking for
the next pullback bar.

Everything else is identical to vwap_intraday.py:
  - Per-day VWAP, reset at 9:30, typical_price = (H+L+C)/3.
  - First cash-session bar closing off VWAP sets the day's bias
    (above -> LONG-only, below -> SHORT-only).
  - 20-bar ATR risk unit: 1.5x ATR stop, 2x ATR target, whichever of
    stop / target / 16:00 ET close comes first. Stop assumed first if one
    bar spans both. No overnight positions. One trade per day maximum.
  - 9:30 AM - 4:00 PM ET cash session only; incomplete final day skipped;
    zero-volume days skipped.
  - Flat $25 round-trip cost per trade (commission + slippage, one MNQ
    contract). Gross P/L reported first, then net after costs.

The summary prints trade count next to vwap_intraday.py's 49-trade
baseline so the drop in frequency is visible directly.

This is intraday, not daily, data - each day is tested independently, not
as one continuous equity curve, so backtest.py's run_backtest() is not
reused and P/L is tracked manually.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request. VWAP and the volume filter both need volume; if a day's bars
carry no volume, that day is skipped.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100). Dollar P/L assumes
# MNQ's $2 per index point (0.25-point tick = $0.50/tick -> $2/point).
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"
POINT_VALUE = 2.0  # USD per index point, MNQ=F

# ATR / risk parameters (shared with vwap_intraday.py / rsi_intraday.py)
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0

# Volume confirmation: rolling window for the "average volume" baseline the
# pullback bar must be under and the confirmation bar must be over. Same
# 20-bar window as the ATR, computed on the continuous 5-minute series.
VOLUME_MA_PERIOD = 20

# Realistic trading friction: commission + slippage for ONE MNQ contract,
# charged once per completed round-trip trade (enter + exit). $25 is a
# reasonable all-in estimate - roughly $1-2 commission per side plus a
# tick or two of slippage per side (0.25-pt tick = $0.50 on MNQ). At
# $2/point this is 12.5 points a trade.
ROUND_TRIP_COST_USD = 25.0

# vwap_intraday.py's trade count in the same 60-day window, for a direct
# frequency comparison in the summary.
BASELINE_TRADES = 49
BASELINE_DAYS = 49

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

# 20-bar rolling average volume on the same continuous series - the
# baseline for the "below-average pullback / above-average confirmation"
# filter. shift(1) is NOT applied: the average includes the current bar,
# matching how ATR is used here, and the filter only asks whether this
# bar is light or heavy relative to its own neighbourhood.
data["VolMA"] = data["Volume"].rolling(window=VOLUME_MA_PERIOD).mean()

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
    vol_ma_series = data["VolMA"].reindex(session.index)
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

    # --- Entry: volume-confirmed pullback to VWAP in the bias direction ---
    # Walk forward. For each bar that touches/crosses VWAP on BELOW-average
    # volume (the pause), check the very next bar: it must close back on
    # the bias side AND trade on ABOVE-average volume (conviction). Entry
    # is that confirmation bar's close.
    direction = None
    entry_price = None
    entry_idx = None
    entry_atr = None
    entry_vwap = None
    pullback_vol = pullback_vol_ma = None
    confirm_vol = confirm_vol_ma = None

    for i in range(bias_idx + 1, len(session) - 1):
        v = vwap.iloc[i]
        pb_vol = volume.iloc[i]
        pb_vol_ma = vol_ma_series.iloc[i]
        if pd.isna(v) or pd.isna(pb_vol_ma):
            continue

        # Pullback bar: traded to VWAP...
        if bias == "LONG":
            touched_vwap = low.iloc[i] <= v
        else:
            touched_vwap = high.iloc[i] >= v
        if not touched_vwap:
            continue
        # ...on a genuine pause (thin volume). Heavy volume into VWAP is a
        # breakdown attempt, not a pause - reject it.
        if pb_vol >= pb_vol_ma:
            continue

        # Confirmation bar: the very next bar.
        c = i + 1
        vc = vwap.iloc[c]
        atr = atr_series.iloc[c]
        cf_vol = volume.iloc[c]
        cf_vol_ma = vol_ma_series.iloc[c]
        if pd.isna(vc) or pd.isna(atr) or pd.isna(cf_vol_ma):
            continue

        if bias == "LONG":
            closed_back = close.iloc[c] > vc
        else:
            closed_back = close.iloc[c] < vc
        if not closed_back:
            continue
        # Conviction returning shows up as a volume surge on the reclaim.
        if cf_vol <= cf_vol_ma:
            continue

        direction = bias
        entry_price = close.iloc[c]
        entry_idx = c
        entry_atr = atr
        entry_vwap = vc
        pullback_vol, pullback_vol_ma = pb_vol, pb_vol_ma
        confirm_vol, confirm_vol_ma = cf_vol, cf_vol_ma
        break

    if direction is None:
        print(f"{day}: {bias} bias, but no volume-confirmed VWAP pullback "
              f"- no trade")
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
    print(f"{day}: {direction} | pullback vol {pullback_vol:,.0f} "
          f"(< avg {pullback_vol_ma:,.0f}) -> confirm vol {confirm_vol:,.0f} "
          f"(> avg {confirm_vol_ma:,.0f}) | Entry = {entry_price:.2f} "
          f"(VWAP {entry_vwap:.2f}) | Exit = {exit_price:.2f} ({exit_reason}) | "
          f"ATR = {entry_atr:.2f} | P/L = {pnl:+.2f} points")

# --- Summary ---
print("\n--- Summary ---")
print(f"Ticker: {ticker}")
print(f"Days tested: {days_tested}")
print(f"Trades taken: {len(trades)}  "
      f"(vwap_intraday.py baseline: {BASELINE_TRADES} trades / "
      f"{BASELINE_DAYS} days)")
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
    print(f"{'':<22}{'Before costs':>16}{'After costs':>16}")
    print(f"{'Total P/L (points)':<22}{gross_points:>+16.2f}{net_points:>+16.2f}")
    print(f"{'Total P/L (USD)':<22}{gross_usd:>+16,.2f}{net_usd:>+16,.2f}")
    print(f"{'Net profitable?':<22}{'YES' if gross_usd > 0 else 'NO':>16}"
          f"{'YES' if net_usd > 0 else 'NO':>16}")
