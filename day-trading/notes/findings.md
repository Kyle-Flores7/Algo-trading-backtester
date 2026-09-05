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

---

## Intraday-native attempt: VWAP pullback and two attempts to improve it

### Baseline - vwap_intraday.py (plain, 1.5x/2.0x) - the best result in the track

`vwap_intraday.py`. First intraday-native signal: per-day VWAP, reset at
9:30, built from that day's own price x volume - no multi-day lookback, no
ported "extreme" threshold. The first cash-session bar that closes off
VWAP sets a LONG-only or SHORT-only bias; entry is the first later bar
that pulls back to touch VWAP but closes back on the bias side (VWAP as
dynamic support/resistance). ATR 20-bar risk unit, 1.5x stop / 2.0x
target, one trade per day, 9:30-16:00 ET only.

A **$25 round-trip cost per trade** (commission + slippage for one MNQ
contract, ~12.5 points at $2/point) is now modelled on every VWAP result
below - gross P/L first, then net after costs.

| Metric | Value |
|---|---|
| Trades | 49 / 49 days |
| Total P/L (gross) | +572.36 points (+$1,144.71) |
| Total P/L (net, after $25/trade) | **-40.14 points (-$80.28)** |
| Win rate | 25/49 (51%) |
| Average win / loss | +83.68 / -63.32 points |
| Concentration | top 3 winners = **21%** of gross profit (of 25 winners) |

This is the strongest result the day-trading track has produced: nearly
break-even after realistic costs, an above-coin-flip 51% win rate, and -
critically - **evenly distributed** (21% top-3 concentration across 25
winners, no hidden outlier). It's not a confirmed edge on a 60-day
sample, but it's the first result that is both positive-ish and
trustworthy. Two attempts to push it over the line followed.

### 1. vwap_selective.py - volume-confirmation filter - worse, -$1,012.81

`vwap_selective.py`. Same VWAP signal, plus a two-bar volume filter on the
entry: the bar that touches VWAP must be on **below-average** volume (a
20-bar rolling mean - a genuine pause, not a breakdown), AND the next bar,
which must close back on the bias side, must be on **above-average**
volume (real conviction returning). Same ATR 1.5x/2.0x, same session, same
one-trade-per-day cap, same $25 cost model.

| Metric | vwap_selective | baseline |
|---|---|---|
| Trades | **19 / 49 days** | 49 / 49 |
| Total P/L (gross) | -268.91 pts (-$537.81) | +572.36 pts (+$1,144.71) |
| Total P/L (net) | **-506.41 pts (-$1,012.81)** | -40.14 pts (-$80.28) |
| Win rate | **37%** (7/19) | 51% (25/49) |
| Average win / loss | +76.69 / -67.14 pts | +83.68 / -63.32 pts |
| Concentration | top 3 = **57%** of gross profit (of 7) | top 3 = 21% (of 25) |

The filter did exactly what it was built to do *mechanically* - trade
count fell 61%, from 49 to 19. But every quality metric got worse: win
rate dropped 51% -> 37%, gross P/L flipped from +572 to -269 points, and
profit concentrated into 3 of just 7 winners (57%). **The volume rule
removed signal, not noise.** The "thin pause, then a conviction surge
reclaiming VWAP" pattern is not a marker of higher-quality setups in this
sample - the setups it kept were the bad ones.

### 2. vwap_tight_rr.py - tighter 1.0x/1.5x risk/reward - worse, -$1,118.30

`vwap_tight_rr.py`. Only the exit geometry changed: **1.0x ATR stop /
1.5x ATR target** instead of 1.5x/2.0x. Entry signal, session, cap and
cost model untouched, so trade count is identical (49/49) and the results
are directly comparable. Hypothesis: the 51%-but-negative baseline meant
trades were reaching favourable ground then giving it back before
travelling the full 2x ATR to target, so a nearer target should bank
those stalled moves as clean wins.

| Metric | vwap_tight_rr (1.0x/1.5x) | baseline (1.5x/2.0x) |
|---|---|---|
| Trades | 49 / 49 days | 49 / 49 |
| Total P/L (gross) | **+53.35 pts (+$106.70)** | +572.36 pts (+$1,144.71) |
| Total P/L (net) | **-559.15 pts (-$1,118.30)** | -40.14 pts (-$80.28) |
| Win rate | **41%** (20/49) | 51% (25/49) |
| Average win / loss | +63.38 / -41.87 pts | +83.68 / -63.32 pts |
| Concentration | top 3 = 25% of gross profit (of 20) | top 3 = 21% (of 25) |

Hypothesis rejected, and the root cause is the stop, not the target.
Moving the stop from 1.5x to 1.0x ATR puts it **inside VWAP's normal
noise band**: win rate fell 51% -> 41% as dips that the 1.5x stop absorbed
and that later recovered turned into realized losses. The nearer target
did not compensate (average win -20 pts), so gross P/L collapsed from
+572 to +53 points. **The 1.5x stop width isn't arbitrary padding - it's
what lets a legitimately good trade survive a pullback and recover.**
Tightening it converts recoverable trades into losers.

---

## Conclusion for the day-trading track

**Plain VWAP (`vwap_intraday.py`, unfiltered, 1.5x/2.0x) remains the best
and only near-viable result found across the entire track** - close to
break-even after realistic $25/trade costs (-$80.28), evenly distributed
(21% top-3 concentration, healthy), with no outlier propping it up. Both
attempts to improve it - a selectivity filter and a tighter risk/reward -
made it *meaningfully worse*, not better.

That the setup resists improvement from two different directions suggests
it sits near a **local optimum** for this signal / timeframe / sample: the
plain version is about as much as this particular VWAP-pullback structure
yields, and squeezing it further just breaks what was working.

### Directions worth considering next

- **More data / a different window.** The single most important open
  question is whether -$80 after costs is real residual signal or just
  where the noise landed on this 60-day sample. Re-run on a different
  time window (or stitch several 60-day pulls) before trusting the number
  either way.
- **Position size vs the cost-to-edge ratio.** The $25/trade cost is
  fixed per contract; the edge (if any) scales with size. Testing whether
  a larger position changes the after-cost picture is cheap to check,
  though it doesn't create edge where there is none - it only rescales an
  existing one.
- **A genuinely different structural change** rather than another filter
  or exit tweak on the current setup. Both improvement attempts so far
  have been modifications *to* the vwap_intraday.py entry/exit; the next
  idea should change the structure (e.g. a different entry trigger
  relative to VWAP, a VWAP-band / standard-deviation envelope, multiple
  entries per day, or VWAP as a trend filter for a separate signal)
  rather than tightening what's there.

---

## Correction: the $25/trade cost assumption was wrong

Every VWAP result above (`vwap_intraday.py`, `vwap_selective.py`,
`vwap_tight_rr.py`) modeled commission + slippage at a flat **$25
round-trip per MNQ contract**. That number was an unresearched guess, not
a benchmark. Checked against real broker rate cards, MNQ round-trip
commission runs **$0.58-$3.50** plus **~$1.10** in exchange/NFA fees
round-trip - call it **$5/trade all-in, conservatively**. $25 overstated
real cost by roughly **5x**.

`ROUND_TRIP_COST_USD` in `vwap_intraday.py` is now `5.0` (with a
`CONTRACTS` multiplier added alongside it for future position-size
testing - cost scales with contracts exactly like gross P/L does, so
size alone can't fix a negative edge, it only rescales it). Corrected
verdicts, using each strategy's already-recorded gross P/L and trade
count above:

| Strategy | Trades | Gross P/L | Net @ $25/trade (old) | Net @ $5/trade (corrected) | Verdict change |
|---|---|---|---|---|---|
| `vwap_intraday.py` (baseline) | 49 | +$1,144.71 | -$80.28 (NOT profitable) | **+$899.71 (PROFITABLE)** | **FLIPS to profitable** |
| `vwap_selective.py` | 19 | -$537.81 | -$1,012.81 (NOT profitable) | -$632.81 (NOT profitable) | No flip - gross is already negative, cost size can't fix that |
| `vwap_tight_rr.py` | 49 | +$106.70 | -$1,118.30 (NOT profitable) | -$138.30 (NOT profitable) | No flip - gross ($106.70) is smaller than even the corrected 49-trade cost ($245) |

**`vwap_intraday.py` is the only strategy in the whole track whose
verdict actually changes.** It was wrongly written off as a $80 loser
above; it's a **~$900 winner** on the same 49-trade sample once cost is
modeled correctly. This overturns the "near-viable, but not quite" framing
used throughout this file for the baseline VWAP result - re-read the
sections above with that in mind. `vwap_selective.py` and
`vwap_tight_rr.py` still lose money after the correction (their losses
shrink a lot, from -$1,012.81 to -$632.81 and from -$1,118.30 to
-$138.30, but neither gross P/L was large enough to clear even a $5/trade
cost), so the earlier conclusion that both modifications made the
baseline *worse* still holds.

**`orb.py`, `orb_sweep_futures.py`, and `orb_sweep_confirmed.py` never had
a cost model at all** - not $25, not any figure. Their P/L totals in this
file (net loss for `orb.py`'s three configs, +$743.75 for
`orb_sweep_futures.py`, -$1,302.50 for `orb_sweep_confirmed.py`) are pure
gross point totals with zero commission/slippage subtracted. There is
nothing to correct from $25 to $5 in those three files because $25 was
never applied there in the first place - applying a cost model to them
would be new work, not a correction, and is out of scope here.

`vwap_selective.py` and `vwap_tight_rr.py` still hardcode
`ROUND_TRIP_COST_USD = 25.0` in code (only `vwap_intraday.py`'s constant
was updated) - the numbers above were recalculated by hand from each
script's already-recorded gross P/L and trade count, not by re-running
them, since a fresh run pulls yfinance's rolling 60-day window and would
no longer match the committed 49-trade sample this file's numbers are
drawn from.

Concentration check stays mandatory for judging whatever comes next.

---

## Milestone: current best finding in the day-trading track

**Plain VWAP pullback (`vwap_intraday.py`) is the one genuine result this
track has produced so far.** Restating it post-correction, with the
realistic $5/trade cost:

| Metric | MNQ=F (`vwap_intraday.py`) | QQQ (`vwap_qqq.py`) |
|---|---|---|
| Sample | 49 trades / 49 days | 59 trades / 60 days |
| Gross P/L | +$1,144.71 | +$1,496.51 |
| Net @ $25/trade (old, wrong) | -$80.28 | +$21.51 |
| Net @ $5/trade (corrected) | **+$899.71** | **+$1,201.51** |
| Edge retained after realistic costs | ~79% of gross | ~80% of gross |
| Concentration (top 3 winners) | 21% | 23% |
| Win rate | 51% (25/49) | 46% (27/59) |

(QQQ's `ROUND_TRIP_COST_USD` is still `25.0` in code - the $1,201.51
corrected figure above is recalculated by hand from its recorded
+$1,496.51 gross / 59 trades, the same way the VWAP-family table above
was corrected.)

Why this reads as real signal and not noise or a fragile lucky result:

- **Net profitable on both instruments once cost is modeled correctly**,
  not just one - at $25/trade MNQ looked like a $80 loser and QQQ was a
  rounding-error win; at the corrected $5/trade both are comfortably
  positive, in the same ballpark (~79-80% of gross retained).
- **No outlier dependence.** Top-3 concentration is 21% (MNQ) and 23%
  (QQQ) of gross profit - healthy and evenly distributed, the opposite of
  variation 4's one-trade mirage (`orb_sweep_futures.py`, +$743.75 gross
  entirely dependent on a single day) that the concentration check caught
  earlier in this file.
- **Survived a cross-underlying check**, the same test that killed
  `orb_sweep.py` (positive on QQQ, negative on SPY - ticker-specific
  noise). VWAP pullback held up moving from MNQ=F futures to QQQ shares.
- **Resisted two independent attempts to improve it** (`vwap_selective.py`'s
  volume filter, `vwap_tight_rr.py`'s tighter risk/reward) - both made it
  worse, which is consistent with a real, already-fairly-tuned signal
  rather than one that just hasn't been optimized yet.

### Still needed before this counts as a validated strategy

This is a promising result, not a confirmed edge. It has been tested on
**one 60-day window and cross-checked on one alternate instrument** -
that is not enough to trust yet. The swing-trading library
(`docs/findings.md`) didn't accept RSI 25/75 as real until it held up
across **multiple years and multiple tickers**; this result should be
held to the same bar before it's treated as more than "promising."

Concretely, before relying on this:

- **A second, non-overlapping time window on MNQ=F.** yfinance's 5-minute
  cap is ~60 days, so this means either waiting for a new 60-day window to
  roll forward and re-running, or splicing multiple historical 60-day
  pulls end-to-end. The open question from the "Conclusion for the
  day-trading track" section above - whether this is real residual signal
  or where the noise landed on this one sample - is still open.
- **Confirmation the edge holds across different market conditions**, not
  just different tickers in the same conditions - the current MNQ and QQQ
  samples cover the same 60ish calendar days, so they're two views of the
  same market regime, not two independent tests.
- Only after the edge survives a second window and different conditions
  should position sizing, execution quality, or live-readiness be the
  next question - not before.

Concentration check stays mandatory for judging whatever comes next.

---

## The second window: 1-hour bars unlock 2-3 years of history - and the edge does not survive it

The previous section's open question was whether the VWAP-pullback result
was real or "where the noise landed on this one [60-day] sample." Getting a
second, non-overlapping window requires longer history than 5-minute bars
allow, so the actual yfinance caps were checked empirically (period
requests increased until Yahoo's API rejected them) instead of assumed:

| Interval | MNQ=F max window | QQQ max window |
|---|---|---|
| 5-minute | ~60 calendar days | ~60 calendar days |
| 15-minute | ~60 calendar days - **same cap, no gain over 5-minute** | ~60 calendar days - same cap |
| 1-hour | 872 calendar days observed (2024-04-14 -> today) | 1,061 calendar days observed (2023-10-09 -> today) |

15-minute bars turned out to be a dead end - Yahoo enforces the identical
~60-day limit on 15-minute as on 5-minute, so switching to it would have
just been a coarser cut of the same window already tested. 1-hour is the
only interval that actually unlocks new history: Yahoo's documented hard
limit for 1-hour is 730 days ("must be within the last 730 days" per its
own API error at longer requests), though `period="730d"` empirically
returned more than that - back to each ticker's earliest available 1-hour
history (MNQ=F's data starts 2024-04-14; QQQ's starts 2023-10-09).

### Overlap check against the original 5-minute sample

`vwap_intraday.py`'s original 60-day / 49-trade run was committed
2026-08-30, so that sample covers approximately 2026-07-01 to 2026-08-30.
The new 1-hour window's most recent ~60 days fall inside that same
calendar span - about **7% of the MNQ window and 6% of the QQQ window**.
The other **~93-94%** (back to April 2024 / October 2023) is calendar time
the original test never saw at all. This is a genuinely different, much
longer sample, not another look at the same two months.

### `vwap_intraday_1h.py` - same signal, adapted for 1-hour bars

Adapting `vwap_intraday.py` to 1-hour bars required almost no change to
the actual trading logic:

- **ATR/stop-target math needed no rescaling.** ATR is computed directly
  from the series it runs on, so a 1-hour bar's ATR is automatically
  proportionally larger than a 5-minute bar's (observed: MNQ ATR ~60-110
  points/bar hourly vs roughly 15-20 points/bar at 5-minute; QQQ ATR
  ~2.2-3.3 points/bar hourly vs a few tenths of a point at 5-minute). The
  1.5x stop / 2.0x target multipliers scale up right along with it with
  zero code changes - `ATR_PERIOD=20`, `STOP_MULT=1.5`, `TARGET_MULT=2.0`
  are all unchanged from the original.
- **What DID need adapting was bar-count-dependent session logic**, which
  is genuinely resolution-specific:
  - The original's "finished session's last bar is 15:55" check is a
    5-minute-only fact. Replaced with a dynamic rule: compute the modal
    number of session bars across the whole pull, and treat any day with
    fewer bars than that mode as an incomplete/in-progress session or
    holiday half day.
  - MNQ=F's 1-hour bars are aligned to the top of the hour (continuous
    near-24h futures trading), not to the 9:30 AM open, so its last
    in-session bar lands exactly at 16:00 and covers 16:00-17:00 -
    after-close settlement trading. That bar is now dropped for both
    tickers (a no-op for QQQ, which never has a bar starting at 16:00).

**Data-alignment caveat worth flagging plainly:** that same top-of-hour
alignment means MNQ=F's 1-hour session bars only run 10:00-15:00 ET (6
bars/day) - the 09:00 bar, which would be the only one covering the actual
9:30 AM open, gets excluded because its timestamp (09:00) falls before the
`between_time("09:30", ...)` cutoff. So MNQ's hourly VWAP here effectively
starts 30 minutes into the session, not at the true open. QQQ's 1-hour
bars are aligned to 9:30 and capture the true full session (7 bars,
9:30-16:00, with a runt final 30-minute bar) with no such gap. This is a
yfinance fixed-grid artifact for continuous futures data, not a strategy
design choice, and it means the two tickers' results below aren't tested
on identically-defined sessions.

### Results

| Metric | MNQ=F (1h) | QQQ (1h) |
|---|---|---|
| Data window | 2024-04-14 -> 2026-09-04 (872 days) | 2023-10-09 -> 2026-09-04 (1,061 days) |
| Days tested / trades | 595 / 517 | 723 / 609 |
| Total P/L (gross) | **-3,634.74 pts (-$7,269.48)** | **+21.77 pts (+$1,785.09)** |
| Win rate | 44% (225/517) | 49% (298/609) |
| Average win / loss | +88.92 / -85.66 pts | +2.19 / -2.13 pts |
| Concentration (top 3) | 5% of gross profit | 8% of gross profit |
| Cost @ $5/trade | $2,585.00 (517 trades) | $3,045.00 (609 trades) |
| Total P/L (net) | **-$9,854.48 (NOT profitable)** | **-$1,259.91 (NOT profitable)** |

### What this means

**The edge does not survive the second, mostly-non-overlapping window.**
MNQ=F is now a clear, evenly-distributed loser - not a fragile one hiding
behind an outlier (5% top-3 concentration is as healthy as the original
sample's 21%, it's just healthy *and losing*). QQQ is close to gross
break-even (+$1,785 over 609 trades, about $2.93/trade before cost) but
the $5/trade cost consumes that thin edge because trade frequency stayed
high (~0.84 trades/day over nearly 3 years) - the same dynamic that sank
`vwap_tight_rr.py` and `vwap_selective.py`, a real edge has to clear cost
per trade, and thin-but-frequent isn't enough.

This reframes the "Milestone" section above. The 60-day 5-minute result
(+$899.71 MNQ, +$1,201.51 QQQ net, both healthy on concentration) most
likely reflects **that specific ~2-month market regime** rather than a
timeframe-independent structural edge - exactly the risk the "still needed
before this counts as a validated strategy" checklist above called out
before this test ran. It is not proof VWAP pullback is *worthless* - bar
resolution, the MNQ session-alignment gap noted above, and regime
differences are all confounded in this one comparison - but the honest
read is that the original result has not been confirmed by the harder
test it was always going to need, and on the evidence gathered so far, it
failed that test on both instruments.

### Next direction

- The MNQ 6-bars/day alignment gap (missing the true 9:30-10:00 open) is a
  real confound - worth checking whether a MNQ run that somehow captures
  the true open changes the picture, before concluding the hourly result
  is representative of the strategy rather than of the data gap.
- QQQ's near-breakeven gross result over ~3 years, undone only by trade
  frequency vs. a flat per-trade cost, is a different failure mode than
  MNQ's outright loss - worth keeping distinct rather than averaging the
  two tickers into one verdict.
- Splitting the 1-hour sample into sub-windows (e.g., by year) would show
  whether the original 60-day result was drawn from a locally-favorable
  stretch within this longer history, rather than only comparing the two
  windows' aggregate totals.

Concentration check stays mandatory for judging whatever comes next.

---

## Four-factor confluence: setup_v1.py (HTF bias + session + VWAP + sweep) - loses on both instruments

`setup_v1.py`. The most ambitious combination attempted in this track:
FOUR conditions, each individually proven or reasoned about elsewhere in
this project, required together on 1-hour bars over each ticker's full
available history (MNQ=F 2024-04-14 -> today, QQQ 2023-10-09 -> today):

1. **HTF bias** - daily close vs 50-day SMA, prior completed bar only (same
   mechanism as `multifactor_v1.py`, but that test wrapped it around RSI at
   5-minute resolution; untested alone at this bar count/time scale).
2. **Session filter** - 9:30-11:00 AM ET entries only (foundational since
   `orb.py`).
3. **VWAP** - per-day structural anchor, identical to `vwap_intraday.py` /
   `vwap_intraday_1h.py` (the one validated real signal in the track).
4. **Liquidity sweep** - a sweep-and-reclaim of a rolling 20-bar swing
   high/low (market structure, not the opening range this time), taken
   only if the reclaim moves toward/through VWAP. Previously tested
   (`orb_sweep.py` family) fading an opening-range level, never combined
   with a VWAP anchor.

Same ATR 1.5x/2.0x stop/target, $5/trade cost, one trade/day, incomplete-day
exclusion, and modal-bar-count session logic as `vwap_intraday_1h.py`.

### Results

| Metric | MNQ=F (1h) | QQQ (1h) |
|---|---|---|
| Data window | 2024-04-14 -> 2026-09-04 (872 days) | 2023-10-09 -> 2026-09-04 (1,061 days) |
| Days tested | 595 | 723 |
| ...bias-aligned sweep+reclaim occurred at all | 146 | 109 |
| ...and VWAP-aligned (actually traded) | **146** | **109** |
| Total P/L (gross) | -364.58 pts (-$729.16) | -75.71 pts (-$6,208.19) |
| Win rate | 43% (63/146) | 39% (43/109) |
| Average win / loss | +114.52 / -91.31 pts | +2.44 / -2.78 pts |
| Concentration (top 3) | 14% of gross profit | 24% of gross profit |
| Cost @ $5/trade | $730.00 (146 trades) | $545.00 (109 trades) |
| Total P/L (net) | **-$1,459.16 (NOT profitable)** | **-$6,753.19 (NOT profitable)** |

### What this means

**The VWAP-alignment gate never actually filtered anything on either
ticker** - the "bias-aligned sweep+reclaim occurred at all" count and the
"actually traded" count are identical (146/146 MNQ, 109/109 QQQ). Every
structural sweep+reclaim in this sample already had VWAP sitting on the
far side of the swept level, so condition #4's VWAP check added zero
selectivity in practice - the trigger reduces, on this data, to "sweep +
reclaim of a 20-bar swing level," full stop. This makes sense in
retrospect: the swing level looks back ~3 trading days while VWAP is
purely today's own average, so VWAP sitting beyond a multi-day extreme
being swept is the common case, not the exception. **The four-factor
design did not actually test four independent conditions - condition #4
collapsed into condition #3 doing no extra work**, which is itself a
useful methodological finding for future confluence attempts: stacking
conditions only adds power if each one can independently veto a trade, and
this is a case where it looked like it would and didn't.

**Both instruments lose money, and neither loss is a concentration
artifact.** Top-3 concentration is 14% (MNQ) and 24% (QQQ) - both in the
healthy range this file has used throughout to distinguish real (if
losing) results from outlier mirages like `orb_sweep_futures.py`'s
one-trade +$743.75. This is an honest, broadly-distributed loss on both
tickers, not a fragile one hiding behind a lucky trade.

**Adding the HTF bias and structural-sweep gate on top of VWAP made things
worse than plain VWAP, not better** - the same direction of finding as
`vwap_selective.py`'s volume filter and `vwap_tight_rr.py`'s tighter
risk/reward, both of which also degraded the `vwap_intraday.py` baseline.
Every attempt so far to add a condition on top of the VWAP pullback signal
- volume confirmation, tighter risk/reward, and now HTF bias + swing-sweep
- has made the result worse, never better. That is a consistent enough
pattern across four independent modifications to treat "VWAP pullback
plain and alone is close to a local ceiling for this signal family" as a
stronger conclusion than any one of those attempts alone would justify.

Also worth noting: this test still inherits the unresolved question from
the 1-hour VWAP section above - the MNQ 6-bars/day alignment gap (missing
the true 9:30-10:00 open) applies here identically, since `setup_v1.py`
reuses `vwap_intraday_1h.py`'s exact session-slicing logic.

### Next direction

- Since the VWAP-alignment gate turned out to be non-binding here, a
  genuinely independent fourth condition (one that can actually veto a
  sweep+reclaim VWAP hasn't already blessed) would be needed before
  concluding four-factor confluence itself doesn't work, as opposed to
  concluding this particular fourth factor didn't add anything.
- The consistent "every add-on makes plain VWAP worse" pattern across four
  attempts (`vwap_selective.py`, `vwap_tight_rr.py`, and now `setup_v1.py`
  on both tickers) is now strong enough evidence that future work should
  default to assuming a new filter will hurt rather than help this signal,
  and treat any filter that doesn't degrade it as the surprising result
  worth double-checking.

Concentration check stays mandatory for judging whatever comes next.
