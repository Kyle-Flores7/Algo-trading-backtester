"""
STRATEGY: RSI Mean-Reversion - Intraday (RSI Intraday)
=====================================================

Concept:
This takes the one swing strategy we have real confidence in - RSI
Mean-Reversion at 25/75 thresholds, 14-period (see
strategies/rsi_mean_reversion.py and docs/findings.md) - and drops it onto
intraday 5-minute MNQ=F (Micro E-mini Nasdaq-100 futures) data instead of
daily bars.

The signal idea is unchanged from the swing version:
- RSI measures how "overbought" or "oversold" price is on a 0-100 scale,
  based on recent momentum.
- RSI < 25 -> price has fallen hard recently, "oversold," bet on a bounce
  -> go LONG.
- RSI > 75 -> price has run up hard recently, "overbought," bet on a
  pullback -> go SHORT.

The only change to the signal is the bar size: RSI(14) is computed on
5-minute bars rather than daily closes, so "recent momentum" now means the
last ~70 minutes of trading rather than the last 14 days. RSI is calculated
continuously across the whole downloaded series (the same way the swing
strategy runs it on one unbroken daily series), but signals are only ACTED
ON during the New York cash session, 9:30 AM - 4:00 PM ET. Overnight and
pre-market bars still feed the RSI calculation but never trigger a trade,
and no position is ever carried past 4:00 PM ET.

Why this is structurally different from the ORB family
-----------------------------------------------------
The orb*.py scripts (orb.py, orb_sweep.py, orb_sweep_futures.py,
orb_sweep_confirmed.py) are all BREAKOUT / session-open strategies:

- They are anchored to the opening range - the first three 5-minute bars
  (9:30-9:45 AM ET). Nothing can happen until that range is drawn, and the
  entire trade thesis is about price interacting with those specific
  levels (breaking them, or sweeping and reversing them).
- They can only trigger in the post-open window, and there is exactly one
  setup per day that either fires or doesn't.
- Their risk unit is the opening range size (high - low) - a measure of
  how much this instrument moved during the open specifically.

RSI Intraday is none of those things:

- It is NOT breakout-based. It is a mean-reversion / fade strategy - it
  bets AGAINST the recent move, not with a breakout of it.
- It is NOT tied to the session open. An RSI extreme can occur at 9:35, at
  noon, or at 3:45 PM - any 5-minute bar in the session is a candidate
  entry. There is no "opening range" concept here at all.
- Because it is not anchored to the session open, the opening-range size
  is not a meaningful risk unit. Instead the risk unit is the recent
  20-bar Average True Range (ATR) - a rolling measure of how much the
  instrument is moving RIGHT NOW, wherever in the day we happen to be:
    * Stop-loss:     1.5x ATR against the trade
    * Profit target: 2x ATR in favor of the trade  (1:1.5 risk/reward -
      note this differs from the ORB family's 1.5x / 2x-of-range, which
      works out to 1:1.33; here the multiples are applied to ATR instead)
  This mirrors the SPIRIT of how orb_sweep_futures.py uses the opening
  range as its risk unit (a natural, self-scaling measure of current
  volatility) while swapping in a measure that isn't pinned to the open.

What is kept the same as the ORB scripts
----------------------------------------
- One trade per day maximum. The first session bar with RSI < 25 or
  RSI > 75 opens the position; after it closes (stop, target, or the
  4:00 PM ET bell) the day is done - no re-entry. This keeps each day a
  single clean sample, same as the ORB family.
- Exit priority: whichever of stop / target / end-of-day (4:00 PM ET)
  comes first closes the trade. No overnight positions, ever.
- If one 5-minute bar's high/low spans both the stop and the target
  (a wide or gappy bar), the stop is assumed to hit first - the
  conservative assumption, since 5-minute OHLC can't tell us the
  intrabar order.
- Futures overnight-session filtering: MNQ trades nearly 24 hours, so
  yfinance's calendar-date groups contain overnight bars. Each day is
  restricted to the 9:30 AM - 4:00 PM ET cash session with between_time()
  before the trade walk and the incomplete-day check, so overnight bars
  never trigger entries or corrupt the "is this day finished" test.
- Same incomplete-day exclusion as the other scripts: a finished cash
  session's last 5-minute bar is 15:55 (covering 15:55-16:00); if the
  last bar of a calendar date is earlier than that, the day is still in
  progress and is skipped (no real end-of-day exit price yet).

This is intraday, not daily, data - each day is tested independently
rather than as one continuous equity curve like the swing strategies in
strategies/. backtest.py's run_backtest() assumes one row per day and
can't be reused here, so P/L is tracked manually, one trading day at a
time.

Data note: yfinance caps 5-minute history at 60 calendar days per request.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100). Dollar P/L below
# assumes MNQ's contract multiplier of $2 per index point (0.25-point tick
# = $0.50/tick -> $2/point); override the ticker only for a points-only
# comparison, e.g. `python rsi_intraday.py NQ=F`.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"
POINT_VALUE = 2.0  # USD per index point, MNQ=F

# RSI / ATR / risk parameters
RSI_PERIOD = 14
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0

# Concentration check: how many of the biggest winners to measure against
# gross profit (a small handful carrying most of the P/L is a fragility
# warning).
TOP_N = 3

data = yf.download(ticker, period="60d", interval="5m")

# Flatten multi-level columns from yfinance (e.g. "Close"/"MNQ=F" stacked)
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

# --- RSI(14) on 5-minute bars ---
# Identical math to strategies/rsi_mean_reversion.py, just on 5-minute
# closes instead of daily closes: bar-to-bar change, split into gains and
# losses, take rolling averages, convert to the 0-100 scale. Computed on
# the full series (overnight bars included) so RSI is continuous; the
# session filter later decides which readings we actually trade on.
delta = data["Close"].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)
avg_gain = gain.rolling(window=RSI_PERIOD).mean()
avg_loss = loss.rolling(window=RSI_PERIOD).mean()
rs = avg_gain / avg_loss
data["RSI"] = 100 - (100 / (1 + rs))

# --- ATR(20) on 5-minute bars ---
# True Range = the largest of: this bar's high-low, |high - prev close|,
# |low - prev close|. ATR is the 20-bar rolling average of that - a
# self-scaling read on how much the instrument is moving lately, used here
# as the risk unit in place of the ORB family's opening-range size.
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
    # overnight bars never trigger an entry or break the completeness
    # check below.
    day_session = day_data.between_time("09:30", "16:00")
    if day_session.empty:
        continue

    # Skip the current/incomplete trading day - its last bar hasn't
    # reached the close yet, so there's no real end-of-day exit price to
    # measure against. A finished session's last 5-minute bar is 15:55.
    if day_session.index[-1].time() < pd.Timestamp("15:55").time():
        print(f"{day}: Skipped - incomplete session (in progress)")
        continue

    days_tested += 1

    # Tradeable bars: the whole cash session through the 15:55 bar. Unlike
    # the ORB scripts there's no opening range to skip past - an RSI
    # extreme on the very first bar is a valid signal.
    session = day_session.between_time("09:30", "15:55")
    close_price = session["Close"].iloc[-1]

    direction = None
    entry_price = None
    entry_idx = None
    entry_atr = None

    # Walk forward bar by bar; take the first bar whose RSI is in the
    # oversold or overbought zone (and whose RSI/ATR are both available).
    for i in range(len(session)):
        row = session.iloc[i]
        rsi = row["RSI"]
        atr = row["ATR"]
        if pd.isna(rsi) or pd.isna(atr):
            continue
        if rsi < RSI_OVERSOLD:
            direction = "LONG"
        elif rsi > RSI_OVERBOUGHT:
            direction = "SHORT"
        else:
            continue
        entry_price = row["Close"]
        entry_idx = i
        entry_atr = atr
        break

    if direction is None:
        print(f"{day}: No RSI extreme during the session - no trade")
        continue

    if direction == "LONG":
        stop_price = entry_price - STOP_MULT * entry_atr
        target_price = entry_price + TARGET_MULT * entry_atr
    else:
        stop_price = entry_price + STOP_MULT * entry_atr
        target_price = entry_price - TARGET_MULT * entry_atr

    exit_price = close_price
    exit_reason = "close"

    # Check each bar after entry for a stop or target hit, using intrabar
    # high/low (not just closes) since either can be touched mid-bar. If a
    # single bar spans both, the stop is assumed first (conservative).
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
    print(f"{day}: {direction} | Entry = {entry_price:.2f} | "
          f"Exit = {exit_price:.2f} ({exit_reason}) | ATR = {entry_atr:.2f} | "
          f"P/L = {pnl:+.2f} points")

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

    # Concentration check: what share of gross profit comes from just the
    # top few winners. A high number means the strategy's edge rests on a
    # handful of trades and is more fragile than the totals suggest.
    gross_profit = sum(winners)
    if gross_profit > 0:
        n = min(TOP_N, len(winners))
        top_n_share = sum(winners[:n]) / gross_profit
        print(f"Concentration: top {n} winner(s) = {top_n_share:.0%} of "
              f"gross profit ({gross_profit:.2f} points across "
              f"{len(winners)} winning trade(s))")
