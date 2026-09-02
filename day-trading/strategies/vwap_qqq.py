"""
STRATEGY: VWAP Pullback - QQQ cross-underlying check (VWAP QQQ)
============================================================

vwap_intraday.py's EXACT logic, run on QQQ instead of MNQ=F. Nothing about
the signal, risk model, session handling or cost model changes - this is
purely a "does the VWAP-pullback edge exist on a different Nasdaq-100
vehicle, or was it MNQ-specific?" robustness check, the same kind of test
that moved `orb_sweep.py` from QQQ to SPy and found its edge was
ticker-specific noise (see findings.md, variation 3).

Identical to vwap_intraday.py:
  - Per-day VWAP reset at 9:30, typical_price = (H+L+C)/3.
  - First cash-session bar closing off VWAP sets LONG-only / SHORT-only
    bias; entry on the first later bar that touches VWAP and closes back
    on the bias side.
  - 20-bar ATR risk unit, 1.5x ATR stop / 2.0x ATR target. Exit is
    whichever of stop / target / 16:00 ET close comes first; stop assumed
    first if one bar spans both. One trade per day. No overnight hold.
  - 9:30 AM - 4:00 PM ET session only; incomplete final day skipped;
    zero-volume days skipped.
  - Flat $25 round-trip cost per trade. Gross P/L first, then net.

The one thing that CANNOT be identical: the dollar multiplier. MNQ is a
futures contract worth $2 per index point; QQQ is a ~$708 ETF share. To
keep the dollar comparison honest, position size here is matched to one
MNQ contract's notional / sensitivity rather than "1 share":

    MNQ:  ~29,090 index x $2/pt        = ~$58,200 notional
    QQQ:  ~$708/share                  -> ~82 shares for the same notional
    QQQ tracks NDX / ~41, so a 1.00 move in QQQ is ~41 index points,
    which is ~$82 of MNQ P/L  ->  $82 per QQQ point at 82 shares.

So P/L in QQQ *points* is directly comparable to MNQ points once scaled by
$82/point, and the same $25 round-trip cost applies to the same-sized
position. Win rate, trade count and concentration are instrument-agnostic
and compare directly with no scaling.

Baseline to beat (vwap_intraday.py on MNQ=F, same 60-day window):
  +572.36 pts gross / -$80.28 after costs, 51% win rate, 49 trades,
  21% top-3 concentration.

This is intraday, not daily, data - each day is tested independently, so
backtest.py's run_backtest() is not reused and P/L is tracked manually.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request. VWAP needs volume; zero-volume days are skipped.
"""

import sys

import pandas as pd
import yfinance as yf

# Defaults to QQQ. Dollar P/L uses an MNQ-notional-matched position (see
# module docstring): ~82 QQQ shares, so $82 per 1.00 move in QQQ, which
# lines up with MNQ's $2 per index point at the current ~41x QQQ:NDX ratio.
ticker = sys.argv[1] if len(sys.argv) > 1 else "QQQ"
QQQ_SHARES = 82
POINT_VALUE = float(QQQ_SHARES)  # USD per QQQ point at an MNQ-matched size

# ATR / risk parameters - identical to vwap_intraday.py.
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0

# Realistic trading friction: commission + slippage, charged once per
# completed round-trip trade. Same $25 figure as the MNQ run so the
# after-cost comparison is like-for-like on an equally sized position.
ROUND_TRIP_COST_USD = 25.0

# vwap_intraday.py's MNQ result in the same 60-day window, for a direct
# comparison in the summary.
BASELINE_GROSS_POINTS = 572.36
BASELINE_NET_POINTS = -40.14
BASELINE_WIN_RATE = 0.51
BASELINE_TRADES = 49
BASELINE_CONCENTRATION = 0.21

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
    # overnight / extended-hours bars never set the bias or trigger an entry.
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
print(f"Ticker: {ticker}  (position: {QQQ_SHARES} shares, "
      f"${POINT_VALUE:.0f}/point - MNQ-notional matched)")
print(f"Days tested: {days_tested}")
print(f"Trades taken: {len(trades)}  (MNQ baseline: {BASELINE_TRADES})")
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
    concentration = None
    if gross_profit > 0:
        n = min(TOP_N, len(winners))
        concentration = sum(winners[:n]) / gross_profit
        print(f"Concentration: top {n} winner(s) = {concentration:.0%} of "
              f"gross profit ({gross_profit:.2f} points across "
              f"{len(winners)} winning trade(s))")

    # --- Commission + slippage adjustment ---
    cost_points = ROUND_TRIP_COST_USD / POINT_VALUE
    total_cost_usd = len(trades) * ROUND_TRIP_COST_USD

    gross_points = total_pnl
    gross_usd = total_pnl * POINT_VALUE
    net_points = gross_points - len(trades) * cost_points
    net_usd = gross_usd - total_cost_usd

    print("\n--- Cost adjustment (commission + slippage) ---")
    print(f"Assumed round-trip cost: ${ROUND_TRIP_COST_USD:,.2f} per trade "
          f"({cost_points:.4f} QQQ points)")
    print(f"Total cost: {len(trades)} trades x ${ROUND_TRIP_COST_USD:,.2f} "
          f"= ${total_cost_usd:,.2f}")
    print()
    print(f"{'':<20}{'QQQ':>16}{'MNQ=F baseline':>18}")
    print(f"{'P/L USD (gross)':<20}{gross_usd:>+16,.2f}"
          f"{BASELINE_GROSS_POINTS * 2.0:>+18,.2f}")
    print(f"{'P/L USD (net)':<20}{net_usd:>+16,.2f}"
          f"{BASELINE_NET_POINTS * 2.0:>+18,.2f}")
    print(f"{'Win rate':<20}{win_rate:>15.0%}{BASELINE_WIN_RATE:>17.0%} ")
    print(f"{'Trades':<20}{len(trades):>16d}{BASELINE_TRADES:>18d}")
    if concentration is not None:
        print(f"{'Concentration':<20}{concentration:>15.0%}"
              f"{BASELINE_CONCENTRATION:>17.0%} ")
    print(f"{'Net profitable?':<20}{'YES' if net_usd > 0 else 'NO':>16}"
          f"{'NO':>18}")
