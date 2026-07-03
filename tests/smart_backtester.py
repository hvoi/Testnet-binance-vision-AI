import asyncio
import random
from dataclasses import dataclass, field
from typing import Dict, List

from news_parser import generate_test_news


def generate_price_path(count: int = 5, start_price: float = 100.0) -> List[float]:
    prices: List[float] = [round(start_price, 2)]
    for _ in range(1, count):
        change = random.uniform(-0.03, 0.04)
        next_price = max(1.0, prices[-1] * (1 + change))
        prices.append(round(next_price, 2))
    return prices


@dataclass
class NewsDrivenBacktester:
    starting_balance: float = 1000.0
    balance: float = field(init=False)
    position_qty: float = field(init=False, default=0.0)
    average_entry: float = field(init=False, default=0.0)
    invested_cost: float = field(init=False, default=0.0)
    logs: List[Dict[str, str]] = field(init=False, default_factory=list)
    trades: int = field(init=False, default=0)
    win_trades: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.balance = float(self.starting_balance)

    def open_position(self, price: float) -> str:
        amount = round(self.balance * 0.10, 2)
        if amount < 0.01 or price <= 0:
            return "Insufficient funds to open position"

        qty = round(amount / price, 8)
        self.position_qty += qty
        self.invested_cost += amount
        self.average_entry = self.invested_cost / self.position_qty if self.position_qty > 0 else 0.0
        self.balance -= amount
        return f"Opened Buy position for {amount} USDT at price {price}"

    def close_all_positions(self, price: float) -> str:
        if self.position_qty <= 0.0:
            return "No positions open"

        proceeds = round(self.position_qty * price, 2)
        profit = round(proceeds - self.invested_cost, 2)
        self.balance += proceeds
        self.position_qty = 0.0
        self.average_entry = 0.0
        self.invested_cost = 0.0
        self.trades += 1
        if profit > 0:
            self.win_trades += 1
        return f"Closed Sell position at price {price}, P/L: {profit} USDT"

    def no_action(self) -> str:
        return "Neutral — no action"

    def run(self) -> Dict[str, float]:
        news_items = asyncio.run(generate_test_news())
        prices = generate_price_path(len(news_items))

        print("\n=== AI-driven trading simulation ===")
        for index, news_item in enumerate(news_items):
            news = news_item["news"]
            sentiment = news_item["sentiment"]
            price = prices[index]

            if sentiment in ["EXCLUSIVE_POSITIVE", "POSITIVE", "ПОЗИТИВ"]:
                action = self.open_position(price)
            elif sentiment in ["EXCLUSIVE_NEGATIVE", "NEGATIVE", "НЕГАТИВ"]:
                action = self.close_all_positions(price)
            else:
                action = self.no_action()

            self.logs.append({
                "news": news,
                "sentiment": sentiment,
                "price": f"{price}",
                "action": action,
                "balance": f"{round(self.balance, 2)}"
            })

            print(f"\nNews: {news}")
            print(f"Sentiment: {sentiment}")
            print(f"Price: {price} USDT")
            print(f"Action: {action}")
            print(f"Balance: {round(self.balance, 2)} USDT")

        if self.position_qty > 0.0:
            final_price = prices[-1]
            action = self.close_all_positions(final_price)
            self.logs.append({
                "news": "Closing position upon simulation end",
                "sentiment": "Termination",
                "price": f"{final_price}",
                "action": action,
                "balance": f"{round(self.balance, 2)}"
            })
            print(f"\n{action}")
            print(f"Final balance after termination: {round(self.balance, 2)} USDT")

        summary = {
            "final_balance": round(self.balance, 2),
            "total_trades": self.trades,
            "win_rate": round((self.win_trades / self.trades) * 100, 2) if self.trades > 0 else 0.0,
        }

        print("\n=== Simulation result ===")
        print(f"Final balance: {summary['final_balance']} USDT")
        print(f"Total trades: {summary['total_trades']}")
        print(f"Winrate: {summary['win_rate']} %")
        print("==========================\n")

        return summary


def run_ai_trading() -> None:
    bot = NewsDrivenBacktester()
    bot.run()
