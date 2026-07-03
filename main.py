import argparse
import asyncio

from backtester import run_backtest
from live_trader import run_testnet_trade
from smart_backtester import run_ai_trading
from telegram_notifications import send_telegram_notification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a trading strategy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest_parser = subparsers.add_parser("backtest", help="Run a backtest on historical data")
    backtest_parser.add_argument("-s", "--start_date", type=str, required=True, help="Start date for the backtest")
    backtest_parser.add_argument("-e", "--end_date", type=str, required=True, help="End date for the backtest")

    live_trade_parser = subparsers.add_parser("live-trade", help="Run a testnet trade using real-time data")
    live_trade_parser.add_argument("-s", "--symbol", type=str, required=True, help="Symbol to trade on the testnet (e.g. BTCUSDT)")
    live_trade_parser.add_argument("-i", "--interval", type=int, default=5, help="Interval in seconds between cycles (default: 5)")
    live_trade_parser.add_argument("--dry_run", action="store_true", help="Run in simulation mode without placing real orders")

    ai_trading_parser = subparsers.add_parser("ai-trading", help="Run AI trading with machine learning algorithms")
    ai_trading_parser.add_argument("-i", "--input_file", type=str, required=True, help="Input file containing historical data for training")
    ai_trading_parser.add_argument("-o", "--output_file", type=str, required=True, help="Output file to save the trained model")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "backtest":
        run_backtest()

    elif args.command == "ai-trading":
        run_ai_trading()

    elif args.command == "live-trade":
        interval = args.interval
        if interval < 1:
            print(f"Warning: Specified interval {interval} is less than 1, setting to 1 second.")
            interval = 1

        mode_status = "SIMULATION (Dry Run)" if args.dry_run else "REAL ORDERS"
        send_telegram_notification(
            f"🚀 <b>Trading bot started successfully!</b>\n"
            f"<b>Mode:</b> {mode_status}\n"
            f"<b>Symbol:</b> {args.symbol}\n"
            f"<b>Polling interval:</b> {interval} sec."
        )

        asyncio.run(run_testnet_trade(interval, args.dry_run))


if __name__ == "__main__":
    main()