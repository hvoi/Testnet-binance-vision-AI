import argparse
import csv
import os
import time
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRADE_SUMMARY_FILE = os.path.join(BASE_DIR, "trades.csv")


def load_trade_balance(file_path: str, start_balance: float) -> tuple[list[datetime], list[float]]:
    timestamps: list[datetime] = []
    balances: list[float] = []
    balance = start_balance

    if not os.path.exists(file_path):
        return timestamps, balances

    with open(file_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            exit_timestamp = row.get("exit_timestamp") or row.get("timestamp") or ""
            if not exit_timestamp:
                continue

            try:
                pnl_value = float(row.get("pnl", "0") or "0")
            except ValueError:
                pnl_value = 0.0

            try:
                timestamp = datetime.fromisoformat(exit_timestamp)
            except ValueError:
                try:
                    timestamp = datetime.strptime(exit_timestamp, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

            balance += pnl_value
            timestamps.append(timestamp)
            balances.append(balance)

    return timestamps, balances


def plot_balance(file_path: str, start_balance: float, refresh_interval: float) -> None:
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_title("Trading Balance from trades.csv")
    ax.set_xlabel("Time")
    ax.set_ylabel("Balance, USDT")
    line, = ax.plot([], [], marker="o", linestyle="-")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate()

    last_mtime = 0.0
    while True:
        if not plt.fignum_exists(fig.number):
            break

        if os.path.exists(file_path):
            mtime = os.path.getmtime(file_path)
            if mtime != last_mtime:
                last_mtime = mtime
                timestamps, balances = load_trade_balance(file_path, start_balance)
                if timestamps:
                    line.set_data(timestamps, balances)
                    ax.relim()
                    ax.autoscale_view()
                    ax.set_xlim(timestamps[0], timestamps[-1])
                    ax.set_ylim(min(balances) * 0.98, max(balances) * 1.02)
                    ax.set_title("Trading Balance from trades.csv")
                else:
                    line.set_data([], [])
                    ax.set_title("trades.csv is empty or has no PnL data")
        else:
            ax.clear()
            ax.set_title("trades.csv not found")
            ax.set_xlabel("Time")
            ax.set_ylabel("Balance, USDT")

        fig.canvas.draw()
        plt.pause(refresh_interval)

    plt.ioff()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize balance from trades.csv")
    parser.add_argument("--file", default=TRADE_SUMMARY_FILE, help="Path to trades.csv")
    parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds")
    parser.add_argument("--start-balance", type=float, default=0.0, help="Starting USDT balance")
    args = parser.parse_args()

    print(f"Loading data from {args.file}")
    print("Close window to stop updates")
    plot_balance(args.file, args.start_balance, args.interval)


if __name__ == "__main__":
    main()
