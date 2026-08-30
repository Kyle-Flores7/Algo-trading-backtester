"""
STRATEGY: Multi-Factor Day Trade - v1 (Session + Trend + RSI)
============================================================

Concept:
Every day-trading variation tried so far has rested on ONE trigger
(a breakout, a liquidity sweep, or an RSI extreme) and none produced a
real edge on 5-minute MNQ=F data - see day-trading/notes/findings.md. The
RSI intraday result (rsi_intraday.py) was the cleanest: a true break-even
null, evenly distributed, no hidden outlier. That leaves an open question -
was the RSI signal itself worthless intraday, or was it fine but fired in
the wrong CONTEXT (wrong time of day, against the larger trend)?

This strategy tests that question directly. It keeps the one signal we
actually trust - RSI Mean-Reversion at 25/75, 14-period, the best
swing-trading signal in docs/findings.md - completely unchanged, and wraps
it in two context filters that have NEVER been tested in the day-trading
track before. An entry requires ALL THREE of the following to be true:

  1. SESSION FILTER - the bar is inside 9:30-11:00 AM ET.
     Earlier scripts either used only the 9:30-9:45 opening range or
     allowed entries any time in the whole 6.5-hour session. This picks
     the middle ground: the first 90 minutes, which is where the bulk of
     the day's volume and directional movement actually happens, without
     being as knife-edge as "the first 15 minutes."

  2. HIGHER-TIMEFRAME TREND FILTER - the trade direction agrees with the
     daily trend. Daily MNQ=F data is pulled SEPARATELY and a 50-day SMA
     computed on it. LONG entries are only allowed when the daily close is
     above its 50-day SMA (uptrend); SHORT entries only when it's below
     (downtrend). To avoid lookahead, "the daily close" means the most
     recent COMPLETED daily bar - i.e. the prior session's close - not the
     close of the day being traded (which wouldn't be known at 10 AM in
     real life).

  3. RSI EXTREME on 5-minute bars - identical to rsi_intraday.py: RSI(14)
     computed continuously on the 5-minute series, LONG when RSI < 25,
     SHORT when RSI > 75. This is the only actual entry trigger; filters
     1 and 2 just decide whether a given RSI extreme is allowed to become
     a trade.

Everything else is carried over unchanged from rsi_intraday.py so the only
difference under test is the two new filters:

  - Risk unit is the recent 20-bar ATR: 1.5x ATR stop / 2x ATR target,
    against / in favor of the trade.
  - Exit priority: whichever of stop / target / 4:00 PM ET close comes
    first. No overnight positions.
  - If one 5-minute bar's range spans both stop and target, the stop is
    assumed to hit first (conservative - 5-minute OHLC can't show the
    intrabar order).
  - One trade per day maximum: the first RSI extreme inside the 9:30-11:00
    window whose direction agrees with the daily trend opens the position;
    after it closes, the day is done. No re-entry.
  - Futures overnight-session filtering: MNQ trades nearly 24 hours, so
    each calendar date is restricted to the 9:30 AM - 4:00 PM ET cash
    session before anything else, so overnight bars can't trigger entries
    or corrupt the completeness check.
  - Same incomplete-day exclusion as the other scripts: if a calendar
    date's last cash-session bar is earlier than 15:55, the day is still
    in progress and is skipped.

Note the entry SCAN only runs over 9:30-11:00 AM, but trade MANAGEMENT
(the stop/target walk) continues through the rest of the session to the
4:00 PM close, exactly like a real trade that's opened in the morning and
managed into the afternoon.

Selectivity reporting:
Because the whole point is to see how much the two filters cut down the
raw RSI signal, the summary reports a funnel: how many tested days had an
RSI extreme anywhere in the cash session, how many had one inside the
9:30-11:00 window, and how many of those were also trend-aligned and
actually traded.

This is intraday, not daily, data - each day is tested independently
rather than as one continuous equity curve. backtest.py's run_backtest()
assumes one row per day and can't be reused here, so P/L is tracked
manually, one trading day at a time.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request; the daily series for the trend filter is pulled over a longer
window so the 50-day SMA is defined across the whole intraday range.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100). Dollar P/L assumes
# MNQ's $2 per index point (0.25-point tick = $0.50/tick -> $2/point).
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"
POINT_VALUE = 2.0  # USD per index point, MNQ=F

# Signal / filter / risk parameters
RSI_PERIOD = 14
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0
TREND_SMA = 50            # daily bars
SESSION_START = "09:30"
SESSION_END = "11:00"     # entry-scan window end (management runs later)

# Concentration check: how many of the biggest winners to measure against
# gross profit.
TOP_N = 3

# --- 5-minute intraday data (entry trigger + risk) ---
data = yf.download(ticker, period="60d", interval="5m")
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

# RSI(14) on 5-minute closes - identical math to
# strategies/rsi_mean_reversion.py, just on 5-minute bars. Computed on the
# full series (overnight included) so it's continuous; the session filter
# decides which readings can trade.
delta = data["Close"].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)
avg_gain = gain.rolling(window=RSI_PERIOD).mean()
avg_loss = loss.rolling(window=RSI_PERIOD).mean()
rs = avg_gain / avg_loss
data["RSI"] = 100 - (100 / (1 + rs))

# ATR(20) on 5-minute bars - the risk unit, same as rsi_intraday.py.
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

# --- Daily data (higher-timeframe trend filter) ---
# Pulled separately over a longer window so the 50-day SMA is defined
# across the whole 60-day intraday range.
daily = yf.download(ticker, period="1y", interval="1d")
daily.columns = daily.columns.get_level_values(0)
daily["SMA50"] = daily["Close"].rolling(window=TREND_SMA).mean()

# Trend reading for each date = was the PRIOR completed daily close above
# its 50-day SMA. .shift(1) pushes each day's own close/SMA comparison
# forward one day, so the trade day uses only information that existed
# before it opened (no lookahead).
daily_trend_up = (daily["Close"] > daily["SMA50"]).shift(1)
trend_up_by_date = {ts.date(): val for ts, val in daily_trend_up.items()}

trades = []
days_tested = 0
days_with_rsi_signal = 0           # RSI extreme anywhere in the cash session
days_with_signal_in_window = 0     # ...also inside 9:30-11:00 AM
# (days actually traded == len(trades))

for day, day_data in data.groupby(data.index.date):
    # Restrict to the 9:30 AM - 4:00 PM ET cash session up front so
    # overnight bars never trigger an entry or break the completeness
    # check below.
    day_session = day_data.between_time("09:30", "16:00")
    if day_session.empty:
        continue

    # Skip the current/incomplete trading day - a finished session's last
    # 5-minute bar is 15:55 (covers 15:55-16:00).
    if day_session.index[-1].time() < pd.Timestamp("15:55").time():
        print(f"{day}: Skipped - incomplete session (in progress)")
        continue

    # Need a prior-day trend reading to apply filter 2 at all.
    trend_up = trend_up_by_date.get(day)
    if trend_up is None or pd.isna(trend_up):
        print(f"{day}: Skipped - no prior-day trend reading available")
        continue

    days_tested += 1
    trend_up = bool(trend_up)

    # Full cash session, used for the signal funnel and for trade
    # management after entry.
    full_session = day_session.between_time("09:30", "15:55")
    close_price = full_session["Close"].iloc[-1]

    # Funnel step 1: did an RSI extreme (either direction) occur anywhere
    # in the cash session today?
    session_rsi = full_session["RSI"]
    if ((session_rsi < RSI_OVERSOLD) | (session_rsi > RSI_OVERBOUGHT)).any():
        days_with_rsi_signal += 1

    # Entry scan window: 9:30-11:00 AM only.
    entry_window = day_session.between_time(SESSION_START, SESSION_END)

    direction = None
    entry_price = None
    entry_time = None
    entry_atr = None
    window_had_signal = False

    for i in range(len(entry_window)):
        row = entry_window.iloc[i]
        rsi = row["RSI"]
        atr = row["ATR"]
        if pd.isna(rsi) or pd.isna(atr):
            continue

        if rsi < RSI_OVERSOLD:
            candidate = "LONG"
        elif rsi > RSI_OVERBOUGHT:
            candidate = "SHORT"
        else:
            continue

        window_had_signal = True

        # Filter 2: direction must agree with the daily trend. A
        # non-aligned extreme is skipped, and the scan continues looking
        # for a later aligned one within the window.
        if candidate == "LONG" and not trend_up:
            continue
        if candidate == "SHORT" and trend_up:
            continue

        # All three filters satisfied.
        direction = candidate
        entry_price = row["Close"]
        entry_time = entry_window.index[i]
        entry_atr = atr
        break

    if window_had_signal:
        days_with_signal_in_window += 1

    if direction is None:
        trend_label = "uptrend" if trend_up else "downtrend"
        print(f"{day}: No qualifying entry ({trend_label}) - no trade")
        continue

    if direction == "LONG":
        stop_price = entry_price - STOP_MULT * entry_atr
        target_price = entry_price + TARGET_MULT * entry_atr
    else:
        stop_price = entry_price + STOP_MULT * entry_atr
        target_price = entry_price - TARGET_MULT * entry_atr

    exit_price = close_price
    exit_reason = "close"

    # Trade management runs over the FULL session, from the bar after
    # entry through the 4:00 PM close. Intrabar high/low is used since a
    # stop/target can be touched mid-bar; if one bar spans both, the stop
    # is assumed first (conservative).
    entry_idx = full_session.index.get_loc(entry_time)
    for j in range(entry_idx + 1, len(full_session)):
        bar = full_session.iloc[j]
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
    trend_label = "uptrend" if trend_up else "downtrend"
    print(f"{day}: {direction} ({trend_label}) | "
          f"Entry = {entry_price:.2f} @ {entry_time.strftime('%H:%M')} | "
          f"Exit = {exit_price:.2f} ({exit_reason}) | ATR = {entry_atr:.2f} | "
          f"P/L = {pnl:+.2f} points")

# --- Summary ---
print("\n--- Summary ---")
print(f"Ticker: {ticker}")
print(f"Days tested: {days_tested}")

# Signal funnel: how selective the combined filter actually is.
print("\nRSI signal funnel (per trading day, one trade/day max):")
print(f"  RSI(14) extreme anywhere in the cash session:  {days_with_rsi_signal}"
      f" / {days_tested}")
print(f"  ...also inside the 9:30-11:00 AM window:        "
      f"{days_with_signal_in_window}")
print(f"  ...and trend-aligned (actually traded):         {len(trades)}")

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
