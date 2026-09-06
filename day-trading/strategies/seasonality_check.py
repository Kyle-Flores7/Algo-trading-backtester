"""
CHECK: Intraday Hour-of-Day Seasonality (Seasonality Check)
=============================================================

This is NOT a strategy - there is no signal, no entry, no stop/target, no
cost model. Every script in this track so far has picked a trigger concept
first (opening range, RSI, VWAP, a liquidity sweep) and only then asked
whether it made money. This check inverts that order for one narrow
question: does any specific hour of the trading day show a real,
repeatable directional tendency at all, BEFORE any trading logic gets
built on top of an assumption like "the first hour trends" or "afternoons
mean-revert" that might just be folklore?

Logic
-----
1. **Hour buckets.** The 9:30 AM-4:00 PM ET cash session is split into
   seven fixed, non-overlapping buckets aligned to 5-minute bar
   boundaries: 09:30-10:30, 10:30-11:30, 11:30-12:30, 12:30-13:30,
   13:30-14:30, 14:30-15:30, and a final half-hour bucket 15:30-16:00
   (the session is 6.5 hours long, so the last bucket is necessarily
   shorter).

2. **Per-day, per-bucket return.** For each trading day and each bucket,
   return = (last bar's Close / first bar's Open) - 1 across that bucket's
   bars only. This gives one return observation per (day, bucket) pair -
   e.g. 49 or so observations for the 09:30-10:30 bucket on MNQ=F, one per
   trading day in the sample.

3. **Per-bucket statistics**, computed across all days' returns for that
   bucket:
   - **Average return** (reported in basis points - hundredths of a
     percent - since single-hour intraday moves are small).
   - **% of days positive / negative** (days with exactly a 0.00% return
     count toward neither - vanishingly rare with real price data, but
     the two percentages are reported separately rather than forced to
     sum to 100% for that reason).
   - **A one-sample t-test against a zero mean**: t = mean / (std / sqrt(n)),
     using the sample standard deviation (ddof=1) of that bucket's daily
     returns. This asks "is this bucket's average return distinguishable
     from pure noise centered on zero," which is the specific question a
     seasonality claim needs to survive before it's worth trading.

What was deliberately simplified
---------------------------------
- **The significance check is a manual t-stat compared to a fixed
  critical value of 2.0, not an exact p-value from a t-distribution.**
  This project has no `scipy` dependency (`requirements.txt` lists only
  `yfinance`, `pandas`, `matplotlib`), and pulling one in for a single
  threshold comparison would be a heavier dependency than this exploratory
  check warrants. 2.0 approximates the two-tailed 5% critical value for a
  t-distribution at the sample sizes here (roughly 49-60 days -> ~48-59
  degrees of freedom, where the true critical value is about 2.01-2.00) -
  close enough that the "significant" label lines up with a conventional
  p<0.05 read without computing one exactly. Anything genuinely borderline
  will sit near the t=2.0 line either way and shouldn't be trusted as a
  strong finding regardless of which side of an exact cutoff it falls on.
- **No multiple-comparisons correction.** Seven buckets are tested per
  ticker (fourteen across both). At a 5% per-test significance threshold,
  seeing one "significant" bucket by chance alone across seven independent
  tests is not a rare event (roughly 30% odds of at least one false
  positive at p=0.05 across 7 independent tests). A single significant
  bucket here is a reason to look closer, not a reason to build a
  strategy on it immediately - see the summary's closing note.
- **Overnight bars (futures) are excluded before bucketing.** Like every
  other script in this track, each calendar day is restricted to the 9:30
  AM-4:00 PM ET cash session with `between_time()` before anything else
  happens, so MNQ=F's near-24-hour trading data can't leak into an hour
  bucket that isn't actually that clock hour in the cash session.
- **Incomplete (in-progress) trading days are excluded** - a completed
  day's last 5-minute bar is 15:55 (covers 15:55-16:00); a day whose last
  bar is earlier than that is still in progress and is skipped, exactly
  as in `sweep_only.py` / `vwap_intraday.py`.

Data note: yfinance caps 5-minute history at ~60 calendar days per
request - the same window every other 5-minute script in this track uses.
"""

import sys

import pandas as pd
import yfinance as yf

# Ticker defaults to MNQ=F (Micro E-mini Nasdaq-100) but can be overridden,
# e.g. `python seasonality_check.py QQQ`.
ticker = sys.argv[1] if len(sys.argv) > 1 else "MNQ=F"

# Two-tailed ~5% critical value for a t-distribution at this sample size
# (see docstring for why this is a fixed approximation rather than an
# exact p-value computed with scipy).
T_CRITICAL = 2.0

# Hour buckets: (start, end) as between_time() bounds, both inclusive,
# chosen so each bucket's end is exactly one 5-minute bar before the next
# bucket's start - this partitions the session into non-overlapping,
# contiguous ranges rather than double-counting boundary bars.
BUCKETS = [
    ("09:30-10:30", "09:30", "10:25"),
    ("10:30-11:30", "10:30", "11:25"),
    ("11:30-12:30", "11:30", "12:25"),
    ("12:30-13:30", "12:30", "13:25"),
    ("13:30-14:30", "13:30", "14:25"),
    ("14:30-15:30", "14:30", "15:25"),
    ("15:30-16:00", "15:30", "15:55"),
]

data = yf.download(ticker, period="60d", interval="5m")
data.columns = data.columns.get_level_values(0)

# yfinance returns intraday timestamps already localized to the exchange
# timezone (America/New_York), so no tz_localize/convert needed here.

# bucket_returns[label] collects one return per trading day for that bucket.
bucket_returns = {label: [] for label, _, _ in BUCKETS}
days_tested = 0

for day, day_data in data.groupby(data.index.date):
    # Restrict to the 9:30 AM - 4:00 PM ET cash session up front so
    # overnight bars (futures) never enter an hour bucket.
    day_session = day_data.between_time("09:30", "16:00")
    if day_session.empty:
        continue

    # Skip the current/incomplete trading day - a finished session's last
    # 5-minute bar is 15:55 (covers 15:55-16:00).
    if day_session.index[-1].time() < pd.Timestamp("15:55").time():
        continue

    session = day_session.between_time("09:30", "15:55")
    days_tested += 1

    for label, start, end in BUCKETS:
        bucket = session.between_time(start, end)
        if bucket.empty:
            continue
        bucket_open = bucket["Open"].iloc[0]
        bucket_close = bucket["Close"].iloc[-1]
        bucket_returns[label].append(bucket_close / bucket_open - 1)

# --- Summary ---
print(f"Ticker: {ticker}")
print(f"Days tested: {days_tested}\n")

header = (f"{'Hour':<13}{'Avg Ret (bps)':>15}{'% Pos':>8}{'% Neg':>8}"
          f"{'N':>5}{'t-stat':>9}{'Significant?':>14}")
print(header)
print("-" * len(header))

for label, _, _ in BUCKETS:
    returns = pd.Series(bucket_returns[label])
    n = len(returns)
    if n < 2:
        print(f"{label:<13}{'n/a':>15}{'n/a':>8}{'n/a':>8}{n:>5}{'n/a':>9}{'n/a':>14}")
        continue

    mean_ret = returns.mean()
    std_ret = returns.std(ddof=1)
    pct_positive = (returns > 0).mean()
    pct_negative = (returns < 0).mean()

    if std_ret > 0:
        t_stat = mean_ret / (std_ret / (n ** 0.5))
        significant = "YES" if abs(t_stat) >= T_CRITICAL else "NO"
        t_stat_str = f"{t_stat:+.2f}"
    else:
        t_stat_str = "n/a"
        significant = "NO"

    print(f"{label:<13}{mean_ret * 10000:>+15.2f}{pct_positive:>8.0%}"
          f"{pct_negative:>8.0%}{n:>5}{t_stat_str:>9}{significant:>14}")

print("\nSignificant = |t-stat| >= 2.0 (approx. two-tailed p<0.05 at this "
      "sample size - see docstring). No multiple-comparisons correction is "
      "applied across the 7 buckets tested, so treat one significant "
      "bucket as a lead worth a second look, not a confirmed edge.")
