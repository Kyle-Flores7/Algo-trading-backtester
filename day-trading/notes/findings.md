# Day-Trading Findings

Results and conclusions from the day-trading / intraday track, kept
separate from `fundamentals.md` (which is concept notes only). Mirrors the
role `docs/findings.md` plays for the swing-trading library.

Every strategy's own reasoning also lives in its docstring in
`day-trading/strategies/*.py`. This file is the running scoreboard and the
honest narrative of what has and hasn't worked.

Data caveat throughout: yfinance caps intraday history at ~60 calendar
days (1-minute) / 60 days (5-minute), so every result below is a small
sample from one recent market window. Treat these as directional reads,
not durable statistics. Dollar figures use MNQ's $2/point multiplier.

---

## The investigation so far: 6 single-signal variations

### 1. Plain ORB breakout (QQQ, 5-min) - lost in all 3 risk configs

`orb.py`. Textbook opening-range breakout: mark the 9:30-9:45 AM range,
go long on a break above the high / short on a break below the low, first
break of the day wins.

Three risk-management configs were tested in sequence:

| Config | Stop / target | Result (QQQ) |
|---|---|---|
| a | none - exit at 4:00 PM close only | net loss |
| b | 1x range stop / 2x range target | net loss |
| c | 1.5x range stop / 2x range target | net loss |

Widening the stop from 1x to 1.5x (commit `cc7cea2`) reduced the bleed
from premature stop-outs but did not flip the strategy positive. Adding a
stop/target at all didn't rescue it either. **Conclusion: the raw
first-breakout signal has no edge on QQQ 5-minute data - price breaking
the opening range is not, by itself, predictive of continuation.**

### 2. Sweep-and-reverse ORB (QQQ, 5-min) - fragile +$28.60

`orb_sweep.py`. Instead of trading the breakout, fade it: wait for price
to poke past the opening-range edge (a "sweep" of resting stop orders)
and then CLOSE back inside the range, and take that failed breakout as a
reversal signal. 1.5x range stop / 2x range target.

Result: **+$28.60 total** on QQQ. Technically positive, but small enough
across the sample that it reads as noise, not edge. Flagged as fragile at
the time - a couple of trades either way would erase it.

### 3. Same sweep-and-reverse logic on SPY - failed, -$16.70

`orb_sweep.py` was parameterized to accept a ticker (commit `2c189d9`) so
the exact same logic could be run on SPY as a cross-underlying check.

Result: **-$16.70 total** on SPY. The barely-positive QQQ number did not
survive the move to a correlated-but-different underlying. This is the
first clear sign that the sweep-and-reverse edge was ticker-specific
noise rather than a real structural effect.

### 4. Sweep-and-reverse on real MNQ=F futures data - +$743.75, but it's one trade

`orb_sweep_futures.py`. Moved off the QQQ proxy onto actual MNQ=F
(Micro E-mini Nasdaq-100) 5-minute data, with proper futures handling:
overnight-session filtering so only the 9:30 AM-4:00 PM ET cash session
feeds the opening range and the trade walk.

Headline result: **+$743.75 total** - by far the best number seen in the
track, and initially looked like the breakthrough.

Then the concentration check: **the entire profit depended on a single
outlier trade.** Remove that one day and the strategy is underwater over
the rest of the sample. A "profitable" strategy whose P/L is one lucky
day is not a profitable strategy - it's a losing strategy with a good
anecdote. This is exactly the failure mode the concentration check exists
to catch, and it caught it.

### 5. Sweep-and-reverse + confirmation filter (MNQ=F) - worse, -$1,302.50

`orb_sweep_confirmed.py`. Hypothesis: the sweep-and-reverse entries
include too many "fakeout of the fakeout" trades (price closes back
inside the range for one bar, then immediately fails again). Fix: treat
the close-back-inside bar as a SIGNAL, not an entry - require the NEXT
bar to continue in the same direction before entering, confirming
follow-through.

Result: **-$1,302.50 total** - materially worse than the unfiltered
version, and with *higher* concentration (an even smaller number of
trades carrying the result). The confirmation bar pushed entries to a
worse average price on the genuine reversals without filtering out enough
bad trades to compensate. **Hypothesis disproven: adding a
confirmation filter to a signal that has no underlying edge just adds
lag and cost.**

### 6. RSI Mean-Reversion adapted to intraday (MNQ=F, 5-min) - true null, -$49.64

`rsi_intraday.py`. Switched signal families entirely: took the one swing
strategy with real confirmed edge - RSI Mean-Reversion at 25/75, 14-period
(see `docs/findings.md`) - and dropped it onto 5-minute MNQ=F bars. RSI(14)
computed continuously on the 5-minute series; act on RSI < 25 (long) /
RSI > 75 (short) only during the cash session; one trade per day; risk
unit is the recent 20-bar ATR (1.5x stop / 2x target) instead of the
opening-range size, since this setup isn't anchored to the session open.

Result over 49 trading days:

| Metric | Value |
|---|---|
| Total P/L | **-24.82 points (-$49.64)** |
| Win rate | 24/49 (49%) |
| Average win | +78.39 points |
| Average loss | -76.25 points |
| Concentration | top 3 winners = **21%** of gross profit |

This is the most *honest* result in the track: essentially break-even,
near-symmetric win/loss size, coin-flip hit rate - and critically, the
P/L is **evenly distributed** (top 3 winners only 21% of gross profit,
across 24 winners). Unlike variation 4, there is no hidden outlier
propping it up. It's a trustworthy "no edge here," not a fragile winner
in disguise.

---

## Honest conclusion

**Simple single-signal mechanical entries have not produced real edge on
5-minute MNQ data, across 6 tested variations spanning 3 signal types:**

- **Breakout** (plain ORB, 3 risk configs) - lost on QQQ.
- **Liquidity sweep / fade** (sweep-and-reverse, +confirmation) - noise on
  QQQ, failed on SPY, one-trade mirage on MNQ, actively worse with a
  confirmation filter.
- **Momentum mean-reversion** (RSI 25/75, our best swing signal) - clean
  null on MNQ.

The sweep-and-reverse work also produced a methodological lesson worth
keeping: **always run the concentration check before believing a positive
result.** Variation 4 would have been logged as a winner without it.

Single-trigger approaches have now been ruled out fairly thoroughly. The
issue doesn't appear to be a poorly tuned signal - it's that no single
5-minute trigger, on its own, carries enough information to beat costs on
this instrument.

---

## Next direction: multi-factor confirmation

Stop looking for the one magic trigger. Instead, require SEVERAL
independent conditions to line up before taking a trade - the premise
being that any one signal is too weak alone, but a confluence of them
might filter down to a genuinely higher-probability subset of setups.

Candidate factors to combine (not take individually):

- **Session timing** - only trade specific high-participation windows
  (e.g. the first 30-60 min after 9:30 AM ET), not any time of day.
- **Liquidity sweep** - the sweep-and-reverse pattern from variations 2-5,
  demoted from "the strategy" to "one required condition."
- **Trend alignment** - only take longs when a higher-timeframe trend
  filter (e.g. a moving average on 15-min or hourly bars) is up, and
  shorts when it's down. The swing-side RSI+trend-filter experiment
  (`docs/findings.md`) found trend filtering *hurt* a standalone signal -
  the bet here is that it behaves differently as a gate on a confluence
  setup rather than as a solo modifier.
- **RSI** - demoted from variation 6's sole trigger to a supporting
  condition (e.g. "sweep happened AND RSI confirms exhaustion").

The goal is fewer, better trades: a strategy that says "no trade" most
days and only fires when timing + sweep + trend + momentum all agree.
Whether that confluence actually exists in the data, or just overfits the
60-day sample, is the open question the next strategy needs to answer -
and the concentration check stays mandatory for judging it.

---

## Follow-up: multi-factor v1 (session + trend + RSI) - worse, -$933.83

`multifactor_v1.py`. First test of the multi-factor direction above. Kept
the RSI 25/75 14-period signal completely unchanged and required TWO
context filters to also be true before entering:

1. **Session filter** - entry only inside 9:30-11:00 AM ET (the highest-
   volume window, wider than the opening range but not the whole day).
2. **Higher-timeframe trend filter** - daily MNQ=F data pulled separately,
   50-day SMA; longs only when the prior completed daily close is above
   it, shorts only when below. Prior day's close (not the trade day's) to
   avoid lookahead.

Everything else carried over from `rsi_intraday.py` unchanged: ATR-based
1.5x/2x stop/target, one trade per day, incomplete-day exclusion, futures
overnight-session filtering. Entry scan ran 9:30-11:00; trade management
continued to the 4:00 PM close.

Result over 49 trading days:

| Metric | Value |
|---|---|
| Total P/L | **-466.91 points (-$933.83)** |
| Win rate | 4/14 (29%) |
| Average win | +80.72 points |
| Average loss | -78.98 points |
| Concentration | top 3 winners = **78%** of gross profit (of 4 winners) |

Selectivity funnel (how much the filters cut the raw signal):

| Stage | Days |
|---|---|
| RSI(14) extreme anywhere in the cash session | **49 / 49** |
| ...also inside the 9:30-11:00 AM window | 32 |
| ...and trend-aligned -> actually traded | 14 |

### What this test showed

**1. Worse than plain RSI intraday, not better.** -$933.83 vs the
standalone RSI intraday null of -$49.64. The surviving 14-trade subset had
a *lower* win rate (29% vs 49%), and the P/L now leans on 3 trades (78%
concentration) - the exact fragility the concentration check exists to
flag. So this is a fragile loser, worse on every axis than the honest
null it was trying to improve.

**2. The "context was the missing ingredient" hypothesis is not
supported.** Adding session timing + trend alignment as gates did not turn
the RSI signal into an edge. The filters are genuinely selective (49
candidate days cut to 14, a 71% reduction), but selective in a way that
didn't concentrate *good* trades - just fewer trades.

**3. The important finding - RSI 25/75 is not a rare event on 5-minute
bars.** Every single tested day (49/49) had RSI(14) touch below 25 or
above 75 somewhere in the cash session. On daily bars in the swing
library, a 25/75 reading means price is genuinely stretched and it happens
infrequently - that rarity is *what makes the signal mean something*. At
5-minute resolution the same thresholds are hit constantly, because
70 minutes of one-directional drift is enough to pin RSI to an extreme.
The number 25/75 was ported down from daily bars, but the *meaning* it
carried up there (stretched, infrequent, mean-reversion likely) did not
come with it.

### Revised conclusion

The problem may not be "single signals need more confirmation" - that
framing led to multifactor_v1, which failed. The problem may be **RSI
specifically is the wrong tool at this timeframe.** Its core assumption -
that extremes are rare and therefore informative - breaks down at high
resolution, where extremes are common and therefore closer to noise.
Adding filters on top of a signal whose base assumption is broken can't
fix it.

More broadly, this casts doubt on the whole approach of taking a
daily-timeframe concept (RSI mean-reversion, or arguably even the
opening-range breakout logic) and porting it down to 5-minute bars and
expecting the same behaviour. Concepts don't automatically survive a
change of timeframe.

### Next direction

Look for a genuinely **intraday-native** signal - something whose logic is
built around intraday market structure from the start, not a daily concept
scaled down. Candidates worth researching before coding anything:

- Volume-based signals (relative volume vs the same time-of-day average,
  volume spikes on the break) - volume is inherently an intraday concept
  and we haven't used it at all yet.
- VWAP and VWAP-relative position - a genuinely intraday reference level,
  unlike a daily SMA.
- Time-of-day patterns in their own right (open drive, lunch-hour chop,
  the last-hour move) rather than as a filter bolted onto something else.
- Opening-range interaction measured more carefully than the plain
  breakout / sweep binary already tried.

The multi-factor confluence idea isn't dead, but it should be built out of
intraday-native components, not a daily signal plus filters. Concentration
check stays mandatory for judging whatever comes next.
