"""
SHARED BACKTESTING HELPER
===========================

This module contains reusable functions for evaluating trading strategies.
Every strategy file should calculate its own "Signal" column, then hand its
data to run_backtest() here to get consistent, comparable performance metrics.

This avoids repeating the same return/drawdown math in every strategy file.
"""

def run_backtest(data, strategy_name="Strategy"):
    """
    Takes a DataFrame that already has 'Close' and 'Signal' columns,
    calculates performance, prints results, and returns the key numbers.
    """

    # Daily % change in price
    data["Daily_Return"] = data["Close"].pct_change()

    # Strategy's return = market return * yesterday's signal
    # (shift(1) because you can't act on today's signal until today's close)
    data["Strategy_Return"] = data["Daily_Return"] * data["Signal"].shift(1)

    # Total compounded return over the whole period
    strategy_total_return = (1 + data["Strategy_Return"]).prod() - 1
    buyhold_total_return = (1 + data["Daily_Return"]).prod() - 1

    # Max drawdown: worst peak-to-trough decline
    cumulative = (1 + data["Strategy_Return"]).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()

    print(f"\n--- {strategy_name} ---")
    print(f"Strategy Total Return: {strategy_total_return:.2%}")
    print(f"Buy & Hold Total Return: {buyhold_total_return:.2%}")
    print(f"Max Drawdown: {max_drawdown:.2%}")

    return {
        "strategy_return": strategy_total_return,
        "buyhold_return": buyhold_total_return,
        "max_drawdown": max_drawdown,
    }