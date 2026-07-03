import subprocess
import json
import shlex
from pathlib import Path

BASE = Path(__file__).parent
NEWS = BASE / 'news_history.csv'
PRICE = BASE / 'historical_prices.csv'


def run_backtest_env(env):
    cmd = ["python", "-c", "from backtest import run_backtest; run_backtest('news_history.csv','historical_prices.csv', starting_usdt=10000.0)"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    out = result.stdout + '\n' + result.stderr
    return out


def parse_summary(output):
    lines = output.splitlines()
    summary = {
        'Balance': None,
        'Trades': None,
        'Winrate': None,
        'Reason': ''
    }
    for line in lines:
        if line.startswith('Final USDT balance:'):
            try:
                summary['Balance'] = float(line.split(':', 1)[1].strip())
            except:
                pass
        if line.startswith('Trades executed:'):
            try:
                summary['Trades'] = int(line.split(':', 1)[1].strip())
            except:
                pass
        if line.startswith('Winrate:'):
            try:
                value = line.split(':', 1)[1].strip().split('%', 1)[0]
                summary['Winrate'] = float(value)
            except:
                pass
    if 'Skipped signals due to trend/SMA' in output or 'Skipped due to trend' in output:
        summary['Reason'] += 'Filtered by SMA; '
    if 'commission' in output.lower() or 'stoploss' in output.lower() or 'floating pnl' in output.lower():
        summary['Reason'] += 'Commissions/Stoploss; '
    return summary


def batch_sma_tests(values):
    print('\n=== SMA sweep ===')
    results = []
    for v in values:
        env = dict(**subprocess.os.environ)
        env['SMA_PERIOD'] = str(v)
        out = run_backtest_env(env)
        summary = parse_summary(out)
        print(f'SMA={v} -> {summary["Balance"]} | {summary["Trades"]} | {summary["Winrate"]} | {summary["Reason"]}')
        results.append((v, summary))
    return results


def batch_takeprofit_tests(values):
    print('\n=== Take-profit sweep ===')
    results = []
    for v in values:
        env = dict(**subprocess.os.environ)
        env['TAKE_PROFIT_PERCENT'] = str(v)
        out = run_backtest_env(env)
        summary = parse_summary(out)
        print(f'TAKEPROFIT={v} -> {summary["Balance"]} | {summary["Trades"]} | {summary["Winrate"]} | {summary["Reason"]}')
        results.append((v, summary))
    return results


def batch_stoploss_tests(values):
    print('\n=== Stop-loss sweep ===')
    results = []
    for v in values:
        env = dict(**subprocess.os.environ)
        env['STOP_LOSS_PERCENT'] = str(v)
        out = run_backtest_env(env)
        summary = parse_summary(out)
        print(f'STOPLOSS={v} -> {summary["Balance"]} | {summary["Trades"]} | {summary["Winrate"]} | {summary["Reason"]}')
        results.append((v, summary))
    return results


def batch_confidence_tests(required_values, window_values):
    print('\n=== Buy confidence sweep ===')
    results = []
    for req in required_values:
        for win in window_values:
            env = dict(**subprocess.os.environ)
            env['BUY_CONFIDENCE_REQUIRED'] = str(req)
            env['BUY_CONFIDENCE_WINDOW'] = str(win)
            out = run_backtest_env(env)
            summary = parse_summary(out)
            print(f'CONFIDENCE={req}/{win} -> {summary["Balance"]} | {summary["Trades"]} | {summary["Winrate"]} | {summary["Reason"]}')
            results.append(((req, win), summary))
    return results


def batch_sma_zero_test():
    print('\n=== SMA disabled test ===')
    env = dict(**subprocess.os.environ)
    env['SMA_PERIOD'] = '0'
    out = run_backtest_env(env)
    summary = parse_summary(out)
    print(f'SMA=0 -> {summary["Balance"]} | {summary["Trades"]} | {summary["Winrate"]} | {summary["Reason"]}')
    return summary


def batch_grid_search(sma_vals, sl_vals, tp_vals, top_n=3):
    print('\n=== Deep grid search (SMA + SL + TP) ===')
    results = []
    for sma in sma_vals:
        for sl in sl_vals:
            for tp in tp_vals:
                env = dict(**subprocess.os.environ)
                env['SMA_PERIOD'] = str(sma)
                env['STOP_LOSS_PERCENT'] = str(sl)
                env['TAKE_PROFIT_PERCENT'] = str(tp)
                out = run_backtest_env(env)
                summary = parse_summary(out)
                result = {
                    'SMA': sma,
                    'SL': sl,
                    'TP': tp,
                    'Balance': summary['Balance'],
                    'Trades': summary['Trades'],
                    'Winrate': summary['Winrate'],
                    'Reason': summary['Reason'],
                }
                results.append(result)
                print(f"SMA={sma} SL={sl} TP={tp} -> {summary['Balance']} | {summary['Trades']} | {summary['Winrate']} | {summary['Reason']}")
    results = [r for r in results if r['Balance'] is not None]
    results.sort(key=lambda r: (r['Balance'], r['Winrate']), reverse=True)
    print('\n=== Top ' + str(top_n) + ' grid results ===')
    for rank, row in enumerate(results[:top_n], start=1):
        print(f"{rank}. SMA={row['SMA']} SL={row['SL']} TP={row['TP']} -> {row['Balance']} | {row['Trades']} | {row['Winrate']} | {row['Reason']}")
    return results[:top_n]


if __name__ == '__main__':
    sma_vals = [10, 14, 20, 30]
    sl_vals = [0.005, 0.01, 0.02]
    tp_vals = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03]
    batch_sma_tests(sma_vals)
    batch_stoploss_tests(sl_vals)
    batch_takeprofit_tests(tp_vals)
    batch_confidence_tests([1, 2, 3], [15, 30])
    batch_sma_zero_test()
    batch_grid_search(sma_vals, sl_vals, tp_vals, top_n=3)
    
    print('\n=== Smart backtester scenarios ===')
    out = subprocess.run(["python", "smart_backtester.py"], capture_output=True, text=True)
    print(out.stdout)
