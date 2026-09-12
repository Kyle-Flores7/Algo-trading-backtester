"""
STRATEGY: RSI Mean-Reversion - Intraday, Tight Thresholds (RSI Intraday Tight)
===============================================================================

Concept:
`rsi_intraday.py` ported the swing library's RSI 25/75 thresholds down to
5-minute bars and found a specific problem, not just a losing result:
RSI(14) touched below 25 or above 75 on **every single tested day (49/49)**
- see day-trading/notes/findings.md, "multifactor v1" section. On daily
bars, a 25/75 reading is genuinely rare and that rarity is what makes it
mean something ("price is stretched"). At 5-minute resolution the same
thresholds are hit constantly, because ~70 minutes of one-directional
drift is enough to pin RSI to an extreme - so the signal fired on every
day, indistinguishable from noise.

This script asks the direct follow-up question: **if 25/75 isn't rare
enough at this resolution, how tight do the thresholds have to get before
they ARE rare/selective again?** RSI(14) < 10 for longs, RSI(14) > 90 for
shorts - the most extreme conventional RSI thresholds - instead of 25/75.
Everything else is unchanged from `rsi_intraday.py`: same signal walk, same
risk model, same session handling.

What changed from rsi_intraday.py
----------------------------------
- **RSI_OVERSOLD = 10, RSI_OVERBOUGHT = 90** (was 25/75). This is the only
  change to the trading logic itself.
- **Ticker-aware POINT_VALUE.** `rsi_intraday.py` hardcodes `POINT_VALUE =
  2.0` (MNQ's multiplier) regardless of the ticker argument - a bug already
  found and fixed in `vwap_intraday.py` (see findings.md's cost-model
  correction section). This script uses the same corrected pattern so a
  `QQQ` argument reports QQQ dollars correctly: $82/pt for QQQ (matching
  the MNQ-notional-matched 82-share position convention used throughout
  this track, e.g. `vwap_qqq.py` / `sweep_only.py`), $2/pt for MNQ=F, 1.0
  otherwise.
- **$5/trade round-trip cost model added.** `rsi_intraday.py` has no cost
  model at all (pure gross points). This script adds the same corrected
  $5/trade all-in commission+fees estimate used by every other current
  script in the track (see findings.md's $25->$5 correction), reporting
  gross P/L first and net P/L after cost second.

Everything else - one trade per day maximum, ATR(20) 1.5x stop / 2.0x
target as the risk unit, exit priority (stop / target / 4:00 PM ET close,
stop assumed first if a bar spans both), the 9:30 AM-4:00 PM ET cash
session restriction, incomplete-day exclusion, and RSI computed
continuously across the whole series but only acted on during the cash
session - is identical to `rsi_intraday.py`. See that file's docstring for
the full reasoning behind those choices.

Why this test matters
----------------------
If 10/90 still fires on most days, that would show the "extremes are
common at 5-minute resolution" finding isn't just a property of 25/75 -
it would take genuinely rare thresholds (or a different tool entirely) to
recover the "rare and informative" property RSI has on daily bars. If
10/90 fires on only a small fraction of days, that's the first sign this
specific problem is fixable by tightening the threshold alone, and the
resulting (much smaller) trade sample's win rate / P/L / concentration
would be the next thing worth trusting or distrusting.

This is intraday, not daily, data - each day is tested independently
rather than as one continuous equity curve. backtest.py's run_backtest()
assumes one row per day and can't be reused here, so P/L is tracked
manually.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100) but can be overridden,
# e.g. `python rsi_intraday_tight.py QQQ`.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"
if ticker == "QQQ":
    POINT_VALUE = 82.0
elif ticker == "MNQ=F":
    POINT_VALUE = 2.0
else:
    POINT_VALUE = 1.0  # unscaled fallback for any other ticker

# RSI / ATR / risk parameters. Only RSI_OVERSOLD/RSI_OVERBOUGHT differ from
# rsi_intraday.py (25/75 -> 10/90); everything else is unchanged.
RSI_PERIOD = 14
RSI_OVERSOLD = 10
RSI_OVERBOUGHT = 90
ATR_PERIOD = 20
STOP_MULT = 1.5
TARGET_MULT = 2.0

# Realistic trading friction - same corrected $5/trade figure as the rest
# of the track (see findings.md's cost-model correction).
ROUND_TRIP_COST_USD = 5.0
CONTRACTS = 1

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
# Identical math to rsi_intraday.py: bar-to-bar change, split into gains
# and losses, take rolling averages, convert to the 0-100 scale. Computed
# on the full series (overnight bars included) so RSI is continuous; the
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
# |low - prev close|. ATR is the 20-bar rolling average of that - the risk
# unit used in place of an opening-range size, unchanged from
# rsi_intraday.py.
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
days_with_signal = 0  # any day where the tight RSI threshold fired at all

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

    # Tradeable bars: the whole cash session through the 15:55 bar. Same
    # as rsi_intraday.py - an RSI extreme on the very first bar is a valid
    # signal, no opening range to skip past.
    session = day_session.between_time("09:30", "15:55")
    close_price = session["Close"].iloc[-1]

    direction = None
    entry_price = None
    entry_idx = None
    entry_atr = None

    # Walk forward bar by bar; take the first bar whose RSI is in the
    # (tight) oversold or overbought zone (and whose RSI/ATR are both
    # available).
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
        print(f"{day}: No RSI<{RSI_OVERSOLD}/>{RSI_OVERBOUGHT} extreme "
              f"during the session - no trade")
        continue

    days_with_signal += 1

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

print(f"\nSelectivity check (is RSI<{RSI_OVERSOLD}/>{RSI_OVERBOUGHT} "
      f"actually rare, unlike 25/75's 49/49-day result?):")
print(f"  Days with a tight-RSI signal: {days_with_signal}/{days_tested} "
      f"({days_with_signal / days_tested:.0%})" if days_tested else
      "  Days with a tight-RSI signal: 0/0")

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
