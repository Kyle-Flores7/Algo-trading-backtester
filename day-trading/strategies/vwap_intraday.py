"""
STRATEGY: VWAP Pullback - Intraday (VWAP Intraday)
=================================================

Concept:
Every day-trading strategy tried so far borrowed its core idea from the
swing-trading library: opening-range breakout, RSI mean-reversion, moving-
average trend. The RSI intraday work (rsi_intraday.py, multifactor_v1.py)
ended on a specific finding - RSI's 25/75 thresholds mean "rare and
stretched" on daily bars, but on 5-minute bars price hits them almost
every day, so the signal's meaning did not survive the timeframe
conversion (see day-trading/notes/findings.md). The lesson: stop porting
daily concepts down, and use a signal that is intraday-native from the
start.

VWAP (Volume-Weighted Average Price) is that signal.

Why VWAP is structurally different from everything tested so far
--------------------------------------------------------------
- **It resets every day.** VWAP starts fresh at 9:30 AM and is built up
  bar by bar from THAT day's own trades. There is no multi-day lookback,
  no rolling window carried across sessions. RSI(14), SMA(50), MACD all
  need N prior periods of history and describe where price sits in a
  multi-day context; VWAP describes where price sits relative to the
  average trade *of today only*.
- **It uses volume, not just price.** Every prior signal in both the swing
  and day-trading tracks is computed from OHLC alone. VWAP weights each
  bar by how much actually traded there, so it tracks the price level
  where the bulk of the day's business was done - the level big
  participants benchmark their fills against. That is a genuinely
  intraday market-structure concept, not a chart pattern.
- **It has no tunable "extreme" threshold to misfire.** RSI needed a
  25/75 cutoff whose meaning broke at 5-minute resolution. VWAP has no
  such parameter - "price is above VWAP" or "below VWAP" is just which
  side of today's volume-weighted average you're on, and that means the
  same thing at any bar size.

Logic
-----
1. **VWAP per day.** For each trading day, using 5-minute MNQ=F bars:
       typical_price = (High + Low + Close) / 3
       VWAP_t = cumsum(typical_price * volume) / cumsum(volume)
   reset at 9:30 AM each day - no carryover between sessions.

2. **Day bias.** The first cash-session bar that closes off VWAP sets the
   day's bias: close above VWAP -> LONG-only bias (buyers in control),
   close below -> SHORT-only bias. Only setups in the bias direction are
   considered for the rest of the day.

3. **Entry - first pullback to VWAP that holds.** VWAP is treated as
   dynamic support (LONG bias) or resistance (SHORT bias). Walking forward
   from the bias bar, the first bar that:
     - LONG bias:  trades DOWN to touch/cross VWAP (Low <= VWAP) but
       CLOSES back above it (Close > VWAP)  -> LONG entry at that close.
     - SHORT bias: trades UP to touch/cross VWAP (High >= VWAP) but
       CLOSES back below it (Close < VWAP)  -> SHORT entry at that close.
   The idea: price left VWAP, came back to test it, and the test held -
   the side that was in control reasserted itself at the level everyone
   is watching.

4. **Risk / exits - unchanged from rsi_intraday.py.** Risk unit is the
   recent 20-bar ATR: 1.5x ATR stop against the trade, 2x ATR target in
   favor. Exit priority is whichever of stop / target / 4:00 PM ET close
   comes first. No overnight positions. If one 5-minute bar's range spans
   both stop and target, the stop is assumed to hit first (conservative -
   5-minute OHLC can't show the intrabar order). One trade per day maximum
   - after the position closes, the day is done, no re-entry.

Carried over from the other day-trading scripts unchanged:
- Session restriction to 9:30 AM - 4:00 PM ET (futures trade nearly 24h,
  so each calendar date is sliced to the cash session before anything
  else, so overnight bars can't set the bias or trigger an entry).
- Incomplete-day exclusion: if a calendar date's last cash-session bar is
  earlier than 15:55, the day is still in progress and is skipped.

This is intraday, not daily, data - each day is tested independently, not
as one continuous equity curve. backtest.py's run_backtest() assumes one
row per day and can't be reused here, so P/L is tracked manually.

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

# ATR / risk parameters (shared with rsi_intraday.py)
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0

# Concentration check: how many of the biggest winners to measure against
# gross profit.
TOP_N = 3

data = yf.download(ticker, period="60d", interval="5m")
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

# ATR(20) on the continuous 5-minute series - the risk unit, same as
# rsi_intraday.py. True Range = the largest of this bar's high-low,
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
