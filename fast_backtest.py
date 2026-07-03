import pandas as pd
import os
import csv
from datetime import datetime
from decimal import Decimal, getcontext

from live_trader import (
    BREAK_EVEN_TRIGGER,
    BREAK_EVEN_OFFSET,
    TAKE_PROFIT_PERCENT,
    TRAILING_DROP_PERCENT,
    STOP_LOSS_PERCENT,
    TAKER_FEE_RATE
)

getcontext().prec = 18


def load_history_data(file_path):
    """Load data from CSV and prepare it for backtesting."""
    if not os.path.exists(file_path):
        print(f"❌ File {file_path} not found.")
        return None
    
    df = pd.read_csv(file_path)
    if 'close' in df.columns:
        df = df.rename(columns={'close': 'price'})
    return df


def run_fast_backtest(data, start_balance=1000.0):
    """Execute fast backtesting logic on candles data."""
    balance = Decimal(str(start_balance))
    position = None
    trade_history = []
    
    print(f"🚀 Starting backtest on {len(data)} candles...")

    for _, row in data.iterrows():
        current_price = Decimal(str(row['price']))
        timestamp = row['timestamp']
        
        if position:
            entry_price = position['entry_price']
            qty = position['qty']
            
            if current_price > position['max_price']:
                position['max_price'] = current_price
            
            change = (current_price - entry_price) / entry_price
            drawback = (position['max_price'] - current_price) / position['max_price']
            
            # Break-even check
            if not position.get('is_break_even') and change >= Decimal(str(BREAK_EVEN_TRIGGER)):
                new_sl = entry_price * (Decimal('1') + Decimal(str(BREAK_EVEN_OFFSET)))
                position['stop_loss'] = new_sl
                position['is_break_even'] = True

            # Take profit trailing check
            if change >= Decimal(str(TAKE_PROFIT_PERCENT)) and drawback >= Decimal(str(TRAILING_DROP_PERCENT)):
                balance += (qty * current_price) * (Decimal('1') - Decimal(str(TAKER_FEE_RATE)))
                trade_history.append({'exit': timestamp, 'pnl': (current_price - entry_price) * qty, 'reason': 'TP_TRAIL'})
                position = None
                continue

            # Stop loss check
            if current_price <= position['stop_loss']:
                balance += (qty * current_price) * (Decimal('1') - Decimal(str(TAKER_FEE_RATE)))
                pnl = (current_price - entry_price) * qty
                trade_history.append({'exit': timestamp, 'pnl': pnl, 'reason': 'SL_OR_BE'})
                position = None
                continue

        else:
            qty = (balance * Decimal('0.1')) / current_price
            fee = (qty * current_price) * Decimal(str(TAKER_FEE_RATE))
            balance -= (qty * current_price) + fee
            
            position = {
                'entry_price': current_price,
                'qty': qty,
                'stop_loss': current_price * (Decimal('1') - Decimal(str(STOP_LOSS_PERCENT))),
                'max_price': current_price,
                'is_break_even': False,
                'entry_time': timestamp
            }

    return trade_history, balance


def save_results(history):
    """Save backtest results to CSV file compatible with plot_balance.py."""
    with open("backtest_results.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["exit_timestamp", "pnl", "exit_reason"])
        for trade in history:
            writer.writerow([trade['exit'], f"{trade['pnl']:.2f}", trade['reason']])


if __name__ == "__main__":
    history_data = load_history_data("BTCUSDT_1h.csv")
    if history_data is not None:
        results, final_bal = run_fast_backtest(history_data)
        save_results(results)
        print(f"✅ Backtest completed. Final balance: {final_bal:.2f} USDT. Trades: {len(results)}")
        print("📊 Now run: python plot_balance.py --file backtest_results.csv")