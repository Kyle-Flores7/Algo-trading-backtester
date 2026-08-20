# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A research/backtesting sandbox for technical-analysis trading strategies — not a live trading bot. No order execution, no broker integration, no automation. Do not introduce any of these unless explicitly requested.

## Running the project

No test suite, linter, or `requirements.txt` — this is a plain-script project run against `venv/`.

```bash
source venv/bin/activate
python strategies/<name>.py       # run one strategy standalone
python compare_strategies.py      # run all strategies, print comparison table
```

## Architecture

- **`backtest.py`** — shared `run_backtest(data, strategy_name)`. Every strategy produces a `Signal` column (`1`/`-1`/`0`) and calls this instead of reimplementing return/drawdown math.
- **`strategies/*.py`** — standalone, independently runnable scripts, not a plugin/class architecture.
- **`compare_strategies.py`** — currently duplicates each strategy's signal logic inline rather than importing from `strategies/`. Keep both in sync when changing signal logic.
- Some strategies use stateful signals (`ffill()` carries a signal forward between trigger days) — preserve each strategy's intended signal behavior when editing.

## Working conventions

- Explain Python and software-engineering concepts in beginner-friendly language.
- Prefer simple, readable, modular code over unnecessary abstraction.
- Inspect only files relevant to the current task; don't modify unrelated files.
- Preserve existing working behavior unless a change is intentionally requested.
- Explain major architectural changes before implementing them.
- Long-term/reference knowledge belongs in `/docs`, not in this file.
