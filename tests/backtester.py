import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def generate_test_candles(count: int = 100, start_price: float = 100.0) -> List[Dict[str, float]]:
    """Generate a synthetic candle dataset with alternating volatility and flat periods."""
    candles: List[Dict[str, float]] = []
    price = start_price

    for index in range(count):
        flat_zone = (index // 10) % 2 == 1
        spike = random.random() < 0.08
        base_volatility = 0.7 if flat_zone else 2.7

        # Simulate direction changes with occasional spikes and flat stretches.
        change = random.uniform(-1.0, 1.0) * base_volatility
        if spike:
            change *= random.choice([3.0, 4.5, 6.0])

        price = max(1.0, price + change)
        open_price = max(0.1, price + random.uniform(-0.8, 0.8))
        close_price = max(0.1, price)
        high_price = max(open_price, close_price) + random.uniform(0.1, 2.0)
        low_price = min(open_price, close_price) - random.uniform(0.1, 2.0)
        low_price = max(0.1, low_price)

        candles.append({
            "open": round(open_price, 4),
            "high": round(high_price, 4),
            "low": round(low_price, 4),
            "close": round(close_price, 4),
        })

    return candles


@dataclass
class GridBacktester:
    starting_balance: float = 1000.0
    grid_step: float = 0.015
    base_size: float = 0.05
    max_levels: int = 6
    take_profit: float = 0.02
    balance: float = field(init=False)
    position_qty: float = field(init=False, default=0.0)
    average_entry: float = field(init=False, default=0.0)
    open_cost: float = field(init=False, default=0.0)
    trades: int = field(init=False, default=0)
    wins: int = field(init=False, default=0)
    equity_history: List[float] = field(init=False, default_factory=list)
    peak_equity: float = field(init=False, default=0.0)
    worst_drawdown: float = field(init=False, default=0.0)
    trade_results: List[float] = field(init=False, default_factory=list)
    current_grid_level: int = field(init=False, default=1)

    def __post_init__(self) -> None:
        self.balance = float(self.starting_balance)
        self.peak_equity = self.balance
        self.equity_history = [self.balance]

    def _current_equity(self, price: float) -> float:
        if self.position_qty <= 0.0:
            return self.balance
        unrealized = (price - self.average_entry) * self.position_qty
        return self.balance + unrealized

    def _record_equity(self, price: float) -> None:
        equity = self._current_equity(price)
        self.equity_history.append(equity)
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = 0.0
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - equity) / self.peak_equity
        self.worst_drawdown = max(self.worst_drawdown, drawdown)

    def _buy_grid_level(self, price: float) -> None:
        if self.current_grid_level > self.max_levels:
            return
        cost = self.base_size * price
        if cost > self.balance:
            return

        self.balance -= cost
        new_total_cost = self.open_cost + cost
        new_quantity = self.position_qty + self.base_size
        self.average_entry = new_total_cost / new_quantity
        self.open_cost = new_total_cost
        self.position_qty = new_quantity
        self.current_grid_level += 1

    def _close_position(self, price: float) -> None:
        if self.position_qty <= 0.0:
            return

        proceeds = self.position_qty * price
        profit = proceeds - self.open_cost
        self.balance += proceeds
        self.trade_results.append(profit)
        self.trades += 1
        if profit > 0:
            self.wins += 1

        self.position_qty = 0.0
        self.average_entry = 0.0
        self.open_cost = 0.0
        self.current_grid_level = 1

    def run(self, candles: List[Dict[str, float]]) -> Dict[str, float]:
        if not candles:
            raise ValueError("Candles list must contain at least one candle.")

        anchor_price = candles[0]["close"]

        for candle in candles:
            close_price = candle["close"]
            price_target = anchor_price * (1 - self.grid_step * self.current_grid_level)
            if self.position_qty <= 0.0 and close_price <= price_target:
                self._buy_grid_level(close_price)

            if self.position_qty > 0.0:
                take_profit_price = self.average_entry * (1 + self.take_profit)
                if close_price >= take_profit_price:
                    self._close_position(close_price)
                    anchor_price = close_price

            self._record_equity(close_price)

        if self.position_qty > 0.0:
            self._close_position(candles[-1]["close"])
            self._record_equity(candles[-1]["close"])

        return {
            "final_balance": round(self.balance, 2),
            "total_trades": self.trades,
            "win_rate": round((self.wins / self.trades) * 100, 2) if self.trades > 0 else 0.0,
            "max_drawdown": round(self.worst_drawdown * 100, 2),
        }

    def report(self, summary: Optional[Dict[str, float]] = None) -> None:
        if summary is None:
            summary = {
                "final_balance": round(self.balance, 2),
                "total_trades": self.trades,
                "win_rate": round((self.wins / self.trades) * 100, 2) if self.trades > 0 else 0.0,
                "max_drawdown": round(self.worst_drawdown * 100, 2),
            }

        print("\n=== Backtest Report ===")
        print(f"Final Balance: {summary['final_balance']} USDT")
        print(f"Total Trades: {summary['total_trades']}")
        print(f"Win Rate: {summary['win_rate']} %")
        print(f"Max Drawdown: {summary['max_drawdown']} %")
        print("=======================\n")


def run_backtest() -> None:
    candles = generate_test_candles(100)
    bot = GridBacktester()
    result = bot.run(candles)
    bot.report(result)
