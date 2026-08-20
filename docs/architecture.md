# Architecture

## Project structure

```
backtest.py            shared backtesting helper
compare_strategies.py  runs all strategies on one ticker, prints comparison table
pull_data.py           standalone: downloads a price chart PNG (unrelated to backtesting)
strategies/*.py        one standalone script per strategy
results/*.txt          saved stdout from past compare_strategies.py runs
future-strategies/     notes on ideas not yet built (e.g. CRT — see roadmap.md)
venv/                  local virtualenv (not committed)
```

## How the pieces interact

- Each script in `strategies/` downloads its own ticker/period via `yfinance`, computes an indicator, sets a `Signal` column (`1`/`-1`/`0`), and calls `backtest.run_backtest(data, strategy_name)` to get return/drawdown metrics. Strategy scripts reach `backtest.py` via `sys.path.append` since `strategies/` is not a package.
- `compare_strategies.py` does **not** import from `strategies/` — it reimplements each strategy's signal logic inline for one shared ticker/period, then prints a summary table. Strategy files and `compare_strategies.py` can drift out of sync if one is updated without the other.
- `results/*.txt` files are manually saved captures of `compare_strategies.py` output; nothing regenerates them automatically.
- `pull_data.py` is unrelated to the backtesting flow — it just plots and saves a 6-month price chart.

## Known limitations

- **Duplicated signal logic**: strategy logic exists in two places (`strategies/*.py` and inline in `compare_strategies.py`), so changes must be applied twice.
- **No shared strategy interface**: strategies are standalone scripts, not modules with a common function/class signature — `compare_strategies.py` can't just loop over `strategies/`.
- **Hardcoded ticker/period**: each script has `ticker`/`period` as module-level variables rather than parameters or CLI args.
- **No automated results tracking**: `results/*.txt` are manual snapshots, not reproducible/versioned experiment records.
- **No tests**: correctness of indicator math and backtest logic is unverified by any test suite.
