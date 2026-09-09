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

# LEADING CANDIDATE (not yet validated) - VWAP pullback filtered by a recent liquidity sweep, on MNQ=F

**This section is deliberately separate from everything below it.** The
rest of this file is the honest scoreboard of strategies that were tested
and rejected (or that stalled as "thin / fragile / ticker-dependent").
This one entry is the single exception: the strongest finding the
day-trading track has produced, promoted here so it does not get lost in
the narrative of what didn't work. It is **not** a confirmed edge - see
the caveats and the pending validation step below.

## What it is

`vwap_after_sweep.py`, on **MNQ=F specifically**. `vwap_intraday.py`'s
plain VWAP pullback (per-day VWAP reset at 9:30, first bar closing off
VWAP sets the day's LONG/SHORT bias, entry on the first later bar that
touches VWAP and closes back on the bias side, 1.5x ATR stop / 2.0x ATR
target, one trade per day, $5/trade round-trip cost) stays the unchanged
primary trigger. The added filter: only take the pullback if a
same-direction liquidity sweep of a 20-bar swing high/low completed
(swept and reclaimed) somewhere in the 10 bars immediately before the
entry bar.

## Why it's the leading candidate

- **It improves on plain VWAP, not just thins it.** On the sensitivity
  pull, unfiltered MNQ net was +$828.92 (50 trades); the filter lifts
  that to +$1,513.17 at the original 10-bar lookback / 5-bar expiry -
  win rate 50% -> 64%, and the gain comes from *which* trades are taken,
  not bigger wins (average win/loss per trade barely moves).
- **It survived a parameter sensitivity check - the first filter in the
  entire investigation to do so without collapsing or reversing sign.**
  Varying lookback / expiry one step tighter and one step wider around
  10/5, all on the same pull vs. the same unfiltered baseline:

  | lookback / expiry | Net P/L vs unfiltered | Win rate | Concentration (top 3) |
  |---|---|---|---|
  | 5 / 3 (tighter) | **+65%** | 68% (13/19) | 35% |
  | 10 / 5 (original) | **+83%** | 64% (16/25) | 30% |
  | 15 / 7 (wider) | **+63%** | 61% (17/28) | 28% |

  Every window beats unfiltered by 60%+ and lifts win rate to 61-68%.
  10/5 is the top of a plateau, not a lone spike. Concentration stays in
  the plausible, broadly-distributed range this file has used throughout
  to tell real results apart from one-trade mirages (e.g.
  `orb_sweep_futures.py`'s 100% single-trade +$743.75) - it is not
  outlier-driven.
- Every other add-on tried on the VWAP pullback (`vwap_selective.py`'s
  volume filter, `vwap_tight_rr.py`'s tighter R:R, `setup_v1.py`'s
  HTF-bias + swing-sweep gate) made it *worse*. This is the only one
  that made it better and then held up under perturbation.

## Caveats - state these every time this result is cited

1. **Not confirmed on QQQ. This is an MNQ-specific finding, not a
   general Nasdaq-100 finding.** The identical filter *hurts* QQQ at all
   three parameter windows - and monotonically worse as it tightens
   (15/7: +$286.57, 10/5: +$63.67, 5/3: -$807.76, flips negative), every
   one below QQQ's unfiltered +$539.94. The MNQ-helps / QQQ-hurts split
   is itself robust to the window sizes, so it is a real property of the
   filter on this data, not noise - but it means the edge cannot yet be
   called instrument-general.
2. **Still only one market regime.** Tested on two 60-day pulls
   (the original `vwap_after_sweep.py` run and the later sensitivity
   run), but both are recent and overlapping - two views of the same
   market conditions, not two independent tests. yfinance's ~60-day
   5-minute cap makes a genuinely non-overlapping window impossible from
   that source.

## Verdict and the pending validation step

**This is the leading candidate for a real MNQ day-trading setup** - the
best result in the track and the only filter to pass a sensitivity check.
It is **not** validated. Final validation is pending the **Databento
historical data pull planned for Tuesday (2026-09-09)**.

Once that data is available, the specific next test is: **re-run
`vwap_after_sweep.py`'s exact logic - 10-bar lookback / 5-bar expiry,
1.5x / 2.0x ATR stop/target, $5/trade cost, one trade per day - against a
genuinely independent multi-year window** to confirm the MNQ edge holds
beyond this one recent 60-day period. Until that passes, treat this as
promising, not proven.

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

## Liquidity sweep, tested alone for the first time: sweep_only.py - ticker-dependent, thin either way

`sweep_only.py`. Every earlier sweep test bundled the pattern with something
else: `orb_sweep.py` and its variants fade a sweep of the OPENING RANGE
specifically, and `setup_v1.py`'s sweep of a rolling 20-bar swing high/low
was gated behind an HTF bias, a 9:30-11:00 session filter, and VWAP
alignment all at once. This is the first time the raw claim - "a sweep of
a recent swing level followed by a close back inside it is itself an edge"
- has been tested with nothing else layered on top: no session filter (the
full 9:30 AM-4:00 PM ET session is scanned, not just the open), no trend/
bias filter (either direction considered on every bar), no VWAP, no RSI.
Because there's no session restriction this time, multiple trades/day are
allowed - one trade per signal, not one per day - with a reclaim required
within 5 bars (25 minutes) of the sweep or the setup expires unfilled.
Same ATR 1.5x/2.0x stop/target and $5/trade cost as the rest of the track,
5-minute bars, 60-day yfinance window.

### Results

| Metric | MNQ=F (5m) | QQQ (5m) |
|---|---|---|
| Data window | 2026-06-29 -> 2026-09-04 | 2026-06-11 -> 2026-09-04 |
| Days tested | 49 | 60 |
| Trades taken | 262 | 274 |
| Average trades/day | 5.35 | 4.57 |
| Total P/L (gross) | -791.93 pts (-$1,583.85) | +19.06 pts (+$1,562.56) |
| Win rate | 40% (105/262) | 45% (122/274) |
| Average win / loss | +86.14 / -65.14 pts | +2.24 / -1.77 pts |
| Concentration (top 3) | 5% of gross profit | 6% of gross profit |
| Cost @ $5/trade | $1,310.00 (262 trades) | $1,370.00 (274 trades) |
| Total P/L (net) | **-$2,893.85 (NOT profitable)** | **+$192.56 (profitable, barely)** |

### What this means

**The raw sweep pattern is not a reliable edge by itself, and the two
tickers disagree about which direction it's wrong in.** MNQ loses money
decisively (-$2,893.85 over 262 trades); QQQ is nominally net profitable
but by $192.56 on $1,370 of trading costs - closer to noise than to a
result, the kind of margin that would flip with one different week of
data. Neither number resembles the original VWAP pullback finding
(`vwap_intraday.py`, the track's one real result to date): that one was
profitable on both its first ticker AND (barely) survived a switch to
QQQ. This one is inconsistent between tickers, which is a materially
weaker signal than "positive but small on both."

**Both results are honestly distributed, not concentration artifacts** -
5% (MNQ) and 6% (QQQ) top-3 concentration are both in the healthy range
this file uses to flag real results vs. outlier mirages like
`orb_sweep_futures.py`'s one-trade +$743.75. MNQ's loss is a broad, steady
bleed across 262 trades, not a couple of bad ones; QQQ's marginal gain is
similarly spread, not propped up by a lucky trade.

**Removing every filter did not reveal a hidden edge - it revealed there
probably isn't one to hide.** `setup_v1.py` already showed that stacking
HTF bias + VWAP alignment on top of this same sweep concept made things
worse on both tickers; this result shows that stripping everything away
down to the bare sweep+reclaim doesn't make things better either. Combined
with `vwap_selective.py`, `vwap_tight_rr.py`, and `setup_v1.py` all making
plain VWAP pullback worse, the emerging picture across this whole track is
that the sweep concept specifically - fading a swing-level breach, at any
level of added structure or in isolation - has not yet produced one
provably-real result at any resolution tried, while VWAP pullback alone
remains the sole survivor.

**Trading five-plus times a day makes cost drag matter far more than
anywhere else in this track.** $1,310-$1,370 in round-trip costs against
gross P/L of -$791.93/+$19.06 points is a much bigger share of the
outcome than any one-trade-per-day script has faced - a useful reminder
that signal frequency and cost sensitivity move together, and any future
high-frequency-per-day setup needs to clear a materially higher gross bar
before costs to have a chance of surviving them.

### Next direction

- MNQ/QQQ disagreement on sign is now the headline uncertainty for this
  signal family - a third instrument or a longer/rolled sample would help
  tell "sweep-alone is a coin flip" apart from "sweep-alone quietly favors
  equities over futures at this size," which this two-ticker, 60-day
  sample can't distinguish.
- The 5-bar reclaim-expiry window was a judgment call (see the script's
  docstring), not something derived from the data - worth revisiting if
  this concept gets picked up again, since a tighter or looser expiry
  could plausibly move either ticker's result meaningfully at this trade
  frequency.

Concentration check stays mandatory for judging whatever comes next.

---

## VWAP pullback, filtered by a recent sweep: vwap_after_sweep.py - helps MNQ, hurts QQQ

`vwap_after_sweep.py`. `sweep_vwap.py` tested sweep-as-trigger with VWAP as
the filter; this is the reverse combination - `vwap_intraday.py`'s VWAP
pullback (this track's one real result) stays the unchanged primary
trigger, and a same-direction liquidity sweep completed in the 10 bars
before the VWAP entry becomes the added context filter, using the same
20-bar swing sweep+reclaim mechanism as `sweep_only.py` (5-bar reclaim
expiry).

**Data-window caveat up front:** yfinance's 60-day window rolls forward
with the calendar, so re-running `vwap_intraday.py` today does not
reproduce its originally-recorded +$899.71 (MNQ) / +$1,201.51 (QQQ)
results from a different pull - both are reported below, plus a
same-pull unfiltered baseline recomputed fresh alongside this test, so
the filter's effect is measured apples-to-apples against data from the
same 60 days as `vwap_after_sweep.py`'s own run. (Separately: running
`vwap_intraday.py` with a `QQQ` argument used to hardcode
`POINT_VALUE = 2.0` regardless of ticker - a pre-existing bug the QQQ
figures in this section were hand-corrected around. **That bug is now
fixed** - `vwap_intraday.py` and `vwap_qqq.py` both derive `POINT_VALUE`
from the ticker argument ($82/pt for `QQQ`, $2/pt for `MNQ=F`, 1.0
otherwise), matching the idiom `sweep_only.py` / `vwap_after_sweep.py`
already used. `vwap_qqq.py`'s default-`QQQ` output is unchanged by the
fix (it already resolved to 82.0 for QQQ); only the non-default ticker
path was wrong. `vwap_qqq.py`'s separate hardcoded `$25` cost constant is
untouched and still hand-corrected where this file uses its numbers.)

### Selectivity funnel (validity check, before any P/L)

| | MNQ=F | QQQ |
|---|---|---|
| Raw VWAP pullback signals (vwap_intraday.py's trigger) | 49 | 59 |
| ...also had a same-direction recent sweep (traded) | **24 (49%)** | **35 (59%)** |

Meaningfully selective on both tickers - not the ~100% pass-through that
made `setup_v1.py`'s VWAP gate a non-filter, and not so restrictive that
almost nothing survives either.

### Results

| Metric | MNQ=F (49 raw -> 24 traded) | QQQ (59 raw -> 35 traded) |
|---|---|---|
| Total P/L (gross) | +762.06 pts (+$1,524.12) | +2.43 pts (+$199.21) |
| Win rate | 62% (15/24) | 43% (15/35) |
| Average win / loss | +86.98 / -60.30 pts | +2.65 / -1.87 pts |
| Concentration (top 3) | 31% of gross profit | 36% of gross profit |
| Cost @ $5/trade | $120.00 (24 trades) | $175.00 (35 trades) |
| Total P/L (net) | **+$1,404.12 (PROFITABLE)** | **+$24.21 (profitable, razor-thin)** |

**Baselines for comparison, same pull as the run above (not the
historical figures - see caveat):**

| | MNQ=F unfiltered (49 trades) | QQQ unfiltered (59 trades) |
|---|---|---|
| Total P/L (gross) | +482.44 pts (+$964.87) | +5.13 pts (+$420.66, hand-corrected to $82/pt) |
| Total P/L (net) | +$719.87 | +$125.66 |

**Historical baselines as originally recorded** (different 60-day pull):
MNQ +$899.71 net / 49 trades; QQQ +$1,201.51 net / 59 trades.

### What this means

**On MNQ, the filter is a clear improvement, not just a smaller/noisier
version of the same trade.** Same-pull unfiltered net was +$719.87 across
49 trades; filtering to the 24 (49%) that also had a recent same-direction
sweep nearly DOUBLES net P/L to +$1,404.12, while win rate jumps from 49%
to 62% and average win/loss per trade is essentially unchanged (so the
gain is coming from which trades get taken, not from bigger wins). This is
the first filter tried anywhere in this track - on either combination
direction - that clearly makes the VWAP pullback's own instrument better,
not worse or merely thinner.

**On QQQ, the filter goes the other way.** Same-pull unfiltered net was
already thin (+$125.66 across 59 trades); filtering to 35 (59%) trades
drops net to +$24.21 - still technically profitable, but by a margin that
is functionally noise (one different trade either way flips the sign).
Win rate barely moves (42% -> 43%).

**Concentration rose on both (22%->31% MNQ, 22%->36% QQQ)**, an expected
side effect of fewer surviving trades concentrating a fixed amount of
profit among fewer winners, and QQQ's 36% is the highest concentration
this track has called "not yet a mirage" - worth treating QQQ's positive
result here as fragile rather than confirmed, given both the thin dollar
margin and the elevated concentration pointing the same direction.

**This is the mirror image of `sweep_vwap.py`'s finding, not a repeat of
it.** There, a real (not rubber-stamp) VWAP filter on the sweep trigger
shrank MNQ's loss but flipped QQQ from a small win to a loss - filtering
helped the loser and hurt the winner. Here, a real sweep-context filter on
the VWAP trigger roughly doubles the strong performer (MNQ) and guts the
already-marginal one (QQQ) - filtering helped the winner and hurt the
already-weaker one. Combined, the two tests say the same underlying thing
two different ways: **combining these two concepts does not produce one
consistent effect across MNQ and QQQ** - which of the two dominates
depends on which one is the primary trigger and which is the filter, not
on some fixed "sweep+VWAP confluence is good/bad" rule.

### Next direction

- MNQ's result here is the single best net-$-per-trade improvement any
  filter has produced in this track and is worth a second look - does it
  hold if LOOKBACK_BARS or SWEEP_EXPIRY_BARS are varied, or is this
  particular pairing of window sizes doing the work?
- QQQ's razor-thin, high-concentration result should not be treated as
  "also profitable" without a fresh out-of-sample pull confirming it -
  as-is it reads more like the unfiltered edge getting thinned out by
  selection than like a real improvement.

Concentration check stays mandatory for judging whatever comes next.

---

## Follow-up: is vwap_after_sweep.py's MNQ improvement specific to the 10/5 window? - no, it holds across 5/3 and 15/7

Direct answer to the section above's first "next direction" bullet. The
sweep-context filter's `LOOKBACK_BARS` / `SWEEP_EXPIRY_BARS` were varied
one step tighter (**5 / 3**) and one step wider (**15 / 7**) around the
original **10 / 5**, on both tickers, on a single fresh pull. Because
yfinance's 60-day window has rolled forward well past the section above's
pull, everything here is recomputed on this new pull - including a
same-pull unfiltered baseline (`vwap_intraday.py`, now ticker-aware, so
its QQQ dollars are correct without hand-correction) - so all six filtered
runs and the two baselines are apples-to-apples with each other, but *not*
with the point totals in the section above.

### Same-pull unfiltered baselines (`vwap_intraday.py`, this pull)

| | MNQ=F | QQQ |
|---|---|---|
| Trades | 50 | 59 |
| Net P/L (after $5/trade) | **+$828.92** | **+$539.94** |
| Win rate | 50% (25/50) | 44% (26/59) |

### MNQ=F - filter helps at every window size

| lookback / expiry | raw -> traded | Net P/L ($5/trade) | vs unfiltered | Win rate | Concentration |
|---|---|---|---|---|---|
| 5 / 3 (tighter) | 50 -> 19 (38%) | **+$1,365.40** | +65% | 68% (13/19) | 35% |
| 10 / 5 (original) | 50 -> 25 (50%) | **+$1,513.17** | +83% | 64% (16/25) | 30% |
| 15 / 7 (wider) | 50 -> 28 (56%) | **+$1,349.86** | +63% | 61% (17/28) | 28% |

All three beat the same-pull unfiltered MNQ net (+$828.92) by a wide
margin and lift win rate from 50% to 61-68%. 10/5 is the best of the
three, but only just - it's the top of a plateau, not a lone spike, with
both neighbors landing within ~$165 of it. **The MNQ improvement is a
property of the sweep-context filter across a range of reasonable window
sizes, not an artifact of the exact 10/5 pair.** The improvement *shape*
also reproduces on this fresh pull (unfiltered +$828.92 -> 10/5 filtered
+$1,513.17, ~+83%), though not the section-above pull's exact "doubling."
Concentration rises as the window tightens (28% -> 30% -> 35%) on a
shrinking winner count (17 -> 16 -> 13); the tight 5/3 setting is where
that starts to look fragile.

### QQQ - filter hurts at every window size, monotonically worse as it tightens

| lookback / expiry | raw -> traded | Net P/L ($5/trade) | vs unfiltered | Win rate | Concentration |
|---|---|---|---|---|---|
| 5 / 3 (tighter) | 59 -> 29 (49%) | **-$807.76** | flips negative | 38% (11/29) | 48% |
| 10 / 5 (original) | 59 -> 36 (61%) | **+$63.67** | much thinner | 44% (16/36) | 36% |
| 15 / 7 (wider) | 59 -> 40 (68%) | **+$286.57** | thinner | 45% (18/40) | 32% |

Every variant lands below the unfiltered QQQ net (+$539.94), and the
filter does *more* damage the more selective it gets: 15/7 -> +$286.57,
10/5 -> +$63.67, 5/3 -> -$807.76 (firmly negative, concentration 48% on
just 11 winners). This is the exact opposite of MNQ, where tightening
toward ~10/5 helps.

### What this means

**The MNQ-helps / QQQ-hurts split from the section above is robust to the
lookback/expiry window sizes - it is not a product of the specific 10/5
tuning.** 10/5 is a reasonable near-optimal choice for MNQ across both
pulls tested, but the qualitative result (filter roughly doubles MNQ,
degrades QQQ) does not depend on it. This is still two 60-day windows on
two correlated Nasdaq-100 vehicles, so it is not yet a validated edge -
but "the effect survives a 2x/0.5x perturbation of both its parameters on
both tickers" is a stronger position than the single 10/5 result alone.

### Next direction

- The MNQ result has now survived a parameter-sensitivity check but still
  needs a genuinely non-overlapping time window (a later calendar pull, or
  spliced historical 60-day pulls) before it counts as more than
  "promising on two views of one market regime" - same bar the milestone
  section set for plain `vwap_intraday.py`.
- QQQ can be set aside for this filter: negative or noise-thin at every
  window size tested, with concentration climbing into mirage territory
  (48% at 5/3) as it tightens.

Concentration check stays mandatory for judging whatever comes next.

---

## Hour-of-day seasonality check: seasonality_check.py - no bucket clears the bar, on either ticker

`seasonality_check.py`. Every strategy in this track so far picked a
trigger concept first and only then asked whether it made money. This is
the opposite: a pure statistical check, no signal, no stop/target, no
cost model, just the question "does any specific hour of the trading day
show a real, repeatable directional tendency at all" - the kind of thing
that would need to be true before an hour-of-day strategy is worth
designing in the first place.

Method: the 9:30 AM-4:00 PM ET cash session split into seven fixed,
non-overlapping buckets (six full hours + a final 15:30-16:00 half-hour),
one return per (day, bucket) as last-close/first-open - 1, then a
one-sample t-test against zero mean per bucket across all tested days
(t-stat vs. a fixed 2.0 critical value, an approximation used because this
project has no scipy dependency - see the script's docstring). MNQ=F and
QQQ, 5-minute bars, 60-day yfinance window.

### Results

**MNQ=F (49 days tested):**

| Hour | Avg return (bps) | % positive | % negative | t-stat | Significant? |
|---|---|---|---|---|---|
| 09:30-10:30 | -3.36 | 51% | 49% | -0.37 | NO |
| 10:30-11:30 | +3.71 | 57% | 43% | +0.65 | NO |
| 11:30-12:30 | +3.78 | 55% | 45% | +0.73 | NO |
| 12:30-13:30 | +1.37 | 51% | 49% | +0.38 | NO |
| 13:30-14:30 | -4.42 | 43% | 57% | -1.48 | NO |
| 14:30-15:30 | +0.88 | 61% | 39% | +0.28 | NO |
| 15:30-16:00 | -4.70 | 43% | 57% | -1.25 | NO |

**QQQ (60 days tested):**

| Hour | Avg return (bps) | % positive | % negative | t-stat | Significant? |
|---|---|---|---|---|---|
| 09:30-10:30 | -3.03 | 50% | 50% | -0.36 | NO |
| 10:30-11:30 | +1.29 | 53% | 47% | +0.24 | NO |
| 11:30-12:30 | +5.00 | 55% | 45% | +1.11 | NO |
| 12:30-13:30 | +1.02 | 52% | 48% | +0.26 | NO |
| 13:30-14:30 | -4.75 | 43% | 57% | -1.54 | NO |
| 14:30-15:30 | -1.38 | 52% | 48% | -0.42 | NO |
| 15:30-16:00 | -4.54 | 43% | 55% | -1.26 | NO |

### What this means

**No bucket clears the significance bar on either ticker - not one out of
fourteen tests.** Every t-stat stays well under the 2.0 threshold (largest
magnitude is -1.54, QQQ's 13:30-14:30). This is a clean, boring, and
useful negative result: at 5-minute resolution over this 49-60 day window,
there is no hour of the day where price moves in a consistent direction
often enough, or by enough, to distinguish it from noise centered on
zero - on EITHER instrument.

**The closest thing to a pattern - 13:30-14:30 and 15:30-16:00 both
negative on both tickers - is exactly the kind of near-miss the docstring
warned about.** With 7 buckets tested per ticker (14 total) at an
approximate 5% per-test threshold, seeing a couple of the largest-
magnitude t-stats land in the same two buckets on both tickers is
suggestive, but with none of them actually crossing 2.0, and no multiple-
comparisons correction applied, this is not evidence of a real
early-afternoon/late-day effect - it's exactly what mild, unremarkable
noise looks like across enough independent looks. Treating it as a lead
rather than a finding is deliberate: **it would need to independently
replicate on a fresh data pull, not just get eyeballed off this one
table, before it's worth acting on.**

**This changes what "no result found" means for every trigger this track
has already tried.** Nothing here found a session or hour with an inherent
directional lean - which means every prior null or losing result in this
track (`orb_sweep.py`, `multifactor_v1.py`, `sweep_only.py`, `setup_v1.py`,
etc.) cannot be explained away as "the session filter was fighting a
seasonality effect nobody accounted for." The signal designs that lost
money lost on their own terms, not because they fought some hidden
time-of-day headwind.

### Next direction

- Since no bucket cleared significance, there is no seasonality edge on
  this data to build a strategy around right now - this check's honest
  conclusion is "don't," not "which hour."
- If this is revisited, the highest-value next step is checking whether
  the 13:30-14:30 / 15:30-16:00 negative lean replicates on a rolled-
  forward data pull (a genuinely new out-of-sample window, not a re-slice
  of the same 60 days), since that is the only way to tell a real early
  effect apart from this window's particular noise.

Concentration check stays mandatory for judging whatever comes next.

---

## Sweep + a VWAP filter that actually filters: sweep_vwap.py - real this time, still not a win

`sweep_vwap.py`. `setup_v1.py`'s VWAP-alignment gate never actually bound
(146/146 MNQ and 109/109 QQQ raw sweep+reclaims passed it), because it
compared the SWEPT LEVEL to VWAP - a multi-day swing extreme sitting
beyond today's own average is close to a geometric certainty, not a real
condition. This script fixes that by testing VWAP the way every other
VWAP script in this track does: is the RECLAIM BAR'S CLOSE on the correct
side of VWAP at that moment. Everything else - the 20-bar swing
sweep+reclaim trigger, the 5-bar reclaim expiry, the full-session scan, ATR
1.5x/2.0x risk, $5/trade cost, multiple trades/day - is identical to
`sweep_only.py`, so any change in the result is attributable to the VWAP
filter alone.

### Results

| Metric | MNQ=F (5m) | QQQ (5m) |
|---|---|---|
| Raw sweep+reclaim signals | 567 | 591 |
| ...passed VWAP confirmation | **69 (12%)** | **82 (14%)** |
| Trades taken | 69 | 82 |
| Total P/L (gross) | -158.73 pts (-$317.46) | -2.82 pts (-$231.64) |
| Win rate | 39% (27/69) | 44% (36/82) |
| Average win / loss | +59.77 / -45.45 pts | +1.53 / -1.34 pts |
| Concentration (top 3) | 24% of gross profit | 19% of gross profit |
| Cost @ $5/trade | $345.00 (69 trades) | $410.00 (82 trades) |
| Total P/L (net) | **-$662.46 (NOT profitable)** | **-$641.64 (NOT profitable)** |

**For comparison, `sweep_only.py`'s unfiltered baseline:** MNQ -$2,893.85
net (262 trades), QQQ +$192.56 net (274 trades).

### What this means

**The filter is real this time - confirmed before looking at any P/L.**
12%/14% pass rates are the opposite of `setup_v1.py`'s ~100%: roughly
seven out of eight raw sweep+reclaims now get rejected because the
reclaim bar's close is on the wrong side of VWAP at that instant. This is
the comparison `setup_v1.py` should have been, and it settles that its
null result was a broken test, not evidence VWAP confirmation doesn't
matter.

**Having a real filter this time doesn't produce a winner.** MNQ's net
loss shrinks by about 77% (-$2,893.85 -> -$662.46) - fewer trades means
less cost drag and, apparently, somewhat better selection - but it is
still a loss. QQQ moves the other way: its barely-positive unfiltered
result (+$192.56) flips to a loss (-$641.64) once VWAP confirmation cuts
its trade count from 274 to 82. A filter that helps one ticker and hurts
the other, on top of `sweep_only.py`'s own MNQ/QQQ sign disagreement, is
now two consecutive results where this signal family behaves
inconsistently across instruments rather than converging on a clear
answer either way.

**Concentration rose on both tickers (5%->24% MNQ, 6%->19% QQQ) but
stays in a plausible range** for a much smaller trade count (69 and 82 vs
262 and 274) - a handful of the surviving winners naturally carry more
weight of the total, and neither is close to the single-trade-driven
mirage seen elsewhere in this track (`orb_sweep_futures.py`'s one trade at
100%). Worth watching if this signal is refined further, since a smaller
sample is inherently more sensitive to a few large trades.

**Taken together with `setup_v1.py` and `sweep_only.py`, this is now the
third sweep-family test to fail to produce a clean win**, and the second
to show the two tickers disagreeing about which direction the signal is
even wrong in. The sweep concept has yet to survive a fair trial in any
form tried so far - alone, gated behind a real VWAP filter, or (in
`setup_v1.py`) gated behind a filter that turned out not to bind. VWAP
pullback alone (`vwap_intraday.py`) remains the only member of this whole
day-trading track with a real, if fragile, positive result.

### Next direction

- With both the raw sweep and the VWAP-confirmed sweep disagreeing on
  sign by ticker, further tuning of THIS specific structural sweep
  (20-bar lookback, 5-bar expiry) has diminishing odds of paying off
  without new evidence pointing at why MNQ and QQQ behave oppositely
  under it - that disagreement, not the point/dollar totals, is the
  open question this family leaves behind.
- If the sweep concept is revisited again, testing whether the pass rate
  and P/L are sensitive to the 5-bar expiry or 20-bar lookback (rather
  than assuming the current numbers are the ceiling for this trigger)
  would be more informative than adding a fifth condition on top.

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
