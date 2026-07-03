import asyncio
import csv
import json
import logging
import os
import random
import time
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Any, Dict

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None
import httpx
from ai_service import evaluate_sentiment
from news_parser import NewsParser
from notifier import TelegramNotifier

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LiveTrader")

notifier = TelegramNotifier()

# Global configuration constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRADE_PERCENT = 0.05  # 5% of balance
MIN_USDT_ORDER = 10.0
MAX_POSITION_PERCENT = 0.10
MAX_POSITION_USDT = 5000.0  # Risk limit
COOLDOWN_SECONDS = 300  # 5-minute cooldown
BUY_CONFIDENCE_REQUIRED = 2
BUY_CONFIDENCE_WINDOW = 60
SMA_PERIOD = 10

# News importance filter
MIN_IMPORTANCE = 3

# Risk management parameters
HARD_STOP_LOSS_PERCENT = 0.050  # 5.0%
STOP_LOSS_PERCENT = 0.030       # 3.0%
TAKE_PROFIT_PERCENT = 0.050     # 5.0%
TRAILING_DROP_PERCENT = 0.005   # 0.5%

# Break-even protection
BREAK_EVEN_TRIGGER = 0.020     # 2.0%
BREAK_EVEN_OFFSET = 0.002      # 0.2%

# Leverage lock
LEVERAGE = 1

# Fees
TAKER_FEE_RATE = 0.0005

# Slippage protection
SLIPPAGE_BUFFER = 0.002
SLIPPAGE_PANIC = 0.010
SLIPPAGE_DELAY_HIGH_IMPACT = 1.0

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
TRADE_LOG_FILE = os.path.join(DATA_DIR, "trade_history.csv")
TRADE_SUMMARY_FILE = os.path.join(DATA_DIR, "trades.csv")
RECOMMENDATION_FILE = os.path.join(DATA_DIR, "ai_recommendation.json")


def update_ai_recommendation(
    verdict: str, importance: int, recommendation: str, news_title: str
) -> None:
    """Save current AI recommendation to JSON for dashboard."""
    recommendation_payload = {
        "timestamp": datetime.now().isoformat(),
        "news_title": news_title,
        "verdict": verdict,
        "importance": importance,
        "recommendation": recommendation if recommendation else "Market observation. No active signals."
    }
    try:
        with open(RECOMMENDATION_FILE, "w", encoding="utf-8") as f:
            json.dump(recommendation_payload, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving ai_recommendation.json: {e}")


API_MAX_RETRIES = 5
API_BASE_DELAY_SECONDS = 2.0
API_MAX_DELAY_SECONDS = 30.0


class DryRunBinanceClient:
    def __init__(self) -> None:
        self.balances = {
            "USDT": {"free": "69547.22", "locked": "0.0"},
            "BTC": {"free": "0.0", "locked": "0.0"},
        }
        self.price = Decimal("59562.81")
        self._leverage_cache: Dict[str, int] = {}

    def get_asset_balance(self, asset: str) -> Dict[str, str]:
        return self.balances.get(asset, {"free": "0.0", "locked": "0.0"})

    def futures_change_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Dry-run emulation of setting leverage."""
        self._leverage_cache[symbol] = leverage
        logger.info(f"[DryRun] Leverage for {symbol} set to {leverage}x")
        return {"symbol": symbol, "leverage": leverage, "maxNotionalValue": "100000000"}

    def get_symbol_ticker(self, symbol: str) -> Dict[str, str]:
        self._simulate_price_move()
        return {"price": str(self.price)}

    def _simulate_price_move(self) -> None:
        drift = Decimal(str(random.uniform(-0.001, 0.001)))
        self.price = (self.price * (Decimal("1") + drift)).quantize(Decimal("0.01"))
        if self.price <= 0:
            self.price = Decimal("59562.81")

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.000001", "maxQty": "1000", "stepSize": "0.000001"},
                {"filterType": "MIN_NOTIONAL", "minNotional": "10.0"},
            ],
        }

    def create_order(self, symbol: str, side: str, type: str, quantity: float) -> Dict[str, Any]:
        """Create order with Taker Fee (0.05%) deduction."""
        side = side.upper()
        price = Decimal(self.get_symbol_ticker(symbol)["price"])
        qty = Decimal(str(quantity))
        gross = qty * price
        fee = (gross * Decimal(str(TAKER_FEE_RATE))).quantize(Decimal("0.01"))
        
        if side == "BUY":
            total_cost = (gross + fee).quantize(Decimal("0.01"))
            self.balances["USDT"]["free"] = str((Decimal(self.balances["USDT"]["free"]) - total_cost).quantize(Decimal("0.01")))
            self.balances["BTC"]["free"] = str((Decimal(self.balances["BTC"]["free"]) + qty).normalize())
        else:
            net_proceeds = (gross - fee).quantize(Decimal("0.01"))
            self.balances["USDT"]["free"] = str((Decimal(self.balances["USDT"]["free"]) + net_proceeds).quantize(Decimal("0.01")))
            self.balances["BTC"]["free"] = str((Decimal(self.balances["BTC"]["free"]) - qty).normalize())

        return {
            "symbol": symbol,
            "side": side,
            "type": type,
            "origQty": str(qty),
            "executedQty": str(qty),
            "cummulativeQuoteQty": str(gross.quantize(Decimal("0.01"))),
            "status": "FILLED",
        }


try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from binance.client import Client
except Exception:
    Client = None


class BinanceTestnetTrader:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        dry_run: bool = True,
    ) -> None:
        self.api_key = None
        self.api_secret = None
        self.dry_run = True
        self.client = DryRunBinanceClient()

    def get_price(self, symbol: str = "BTCUSDT") -> float:
        if self.dry_run:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker.get("price"))
        else:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker.get("price"))

    def place_order(self, symbol: str, side: str, qty: float) -> Dict[str, Any]:
        side = side.upper()
        if self.dry_run:
            return self.client.create_order(symbol=symbol, side=side, type="MARKET", quantity=qty)
        else:
            return self.client.futures_create_order(symbol=symbol, side=side, type="MARKET", quantity=qty)

    def get_asset_balance(self, asset: str) -> Dict[str, str]:
        if self.dry_run:
            return self.client.get_asset_balance(asset)
        else:
            balances = self.client.futures_account_balance()
            for b in balances:
                if b.get("asset") == asset:
                    return {"free": b.get("withdrawAvailable", b.get("balance", "0.0")), "locked": "0.0"}
            return {"free": "0.0", "locked": "0.0"}

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        if self.dry_run:
            return self.client.get_symbol_info(symbol)
        else:
            info = self.client.futures_exchange_info()
            for s in info.get("symbols", []):
                if s.get("symbol") == symbol:
                    return s
            return {}

    def get_symbol_filter(self, symbol_info: Dict[str, Any], filter_type: str) -> Dict[str, Any] | None:
        for symbol_filter in symbol_info.get("filters", []):
            if symbol_filter.get("filterType") == filter_type:
                return symbol_filter
            if filter_type == "LOT_SIZE" and symbol_filter.get("filterType") == "MARKET_LOT_SIZE":
                return symbol_filter
        return None

    def quantize_qty(self, qty: float, step_size: str) -> float | None:
        getcontext().prec = 18
        decimal_qty = Decimal(str(qty))
        decimal_step = Decimal(step_size)
        if decimal_step <= 0:
            return None
        quantized = (decimal_qty // decimal_step) * decimal_step
        if quantized <= 0:
            return None
        return float(quantized.normalize())

    def get_valid_quantity(self, symbol: str, raw_qty: float, price: float | None = None) -> float | None:
        symbol_info = self.get_symbol_info(symbol)
        if not symbol_info:
            return raw_qty
        lot_filter = self.get_symbol_filter(symbol_info, "LOT_SIZE")
        if lot_filter is None:
            return raw_qty

        step_size = lot_filter.get("stepSize", "0.000001")
        min_qty = Decimal(str(lot_filter.get("minQty", "0.000001")))
        
        adjusted_qty = self.quantize_qty(raw_qty, step_size)
        if adjusted_qty is None:
            return None
        if Decimal(str(adjusted_qty)) < min_qty:
            return float(min_qty)
        return adjusted_qty

    def set_leverage(self, symbol: str, leverage: int = LEVERAGE) -> None:
        if self.dry_run:
            res = self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
        else:
            res = self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logger.info(f"Leverage for {symbol}: {leverage}x (response: {res})")


def log_trade(
    timestamp: str, symbol: str, side: str, qty: float, price: float, pnl: float | None
) -> None:
    created_new = not os.path.exists(TRADE_LOG_FILE)
    with open(TRADE_LOG_FILE, mode="a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        if created_new:
            writer.writerow(["timestamp", "symbol", "side", "qty", "price", "pnl"])
        writer.writerow(
            [
                timestamp,
                symbol,
                side,
                f"{qty:.6f}",
                f"{price:.2f}",
                "" if pnl is None else f"{pnl:.2f}",
            ]
        )
        csv_file.flush()


def log_completed_trade(
    exit_timestamp: str,
    symbol: str,
    entry_timestamp: str,
    entry_price: float,
    exit_price: float,
    qty: float,
    pnl: float,
    entry_reason: str,
    exit_reason: str,
    news_title: str = "",
    verdict: str = "",
    recommendation: str = "",
) -> None:
    created_new = not os.path.exists(TRADE_SUMMARY_FILE)
    with open(TRADE_SUMMARY_FILE, mode="a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        if created_new:
            writer.writerow(
                [
                    "exit_timestamp",
                    "symbol",
                    "entry_timestamp",
                    "entry_price",
                    "exit_price",
                    "qty",
                    "pnl",
                    "entry_reason",
                    "exit_reason",
                    "news_title",
                    "verdict",
                    "recommendation",
                ]
            )
        writer.writerow(
            [
                exit_timestamp,
                symbol,
                entry_timestamp,
                f"{entry_price:.2f}",
                f"{exit_price:.2f}",
                f"{qty:.6f}",
                f"{pnl:.2f}",
                entry_reason,
                exit_reason,
                news_title,
                verdict,
                recommendation,
            ]
        )
        csv_file.flush()


async def run_with_retry(
    operation,
    *args,
    retries: int = API_MAX_RETRIES,
    base_delay: float = API_BASE_DELAY_SECONDS,
    max_delay: float = API_MAX_DELAY_SECONDS,
    context: str = "API",
):
    delay = base_delay
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return await asyncio.to_thread(operation, *args)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{context} failed")


async def execute_buy_order(trader, symbol, qty, amount_usdt, price, label="BUY"):
    try:
        await asyncio.to_thread(trader.place_order, symbol, "BUY", qty)
        msg = f"🛒 [{label}] Executed order BUY {qty:.6f} {symbol} at price {price:.2f}"
        print(msg)
        log_trade(datetime.now().isoformat(), symbol, "BUY", qty, price, None)
        await notifier.send_notification(msg)
    except Exception as e:
        print(f"❌ Error executing BUY order: {e}")


async def execute_sell_order(trader, symbol, qty, price, pnl=None, label="SELL"):
    try:
        await asyncio.to_thread(trader.place_order, symbol, "SELL", qty)
        msg = f"💰 [{label}] Executed order SELL {qty:.6f} {symbol} at price {price:.2f}."
        if pnl is not None:
            msg += f" Trade result: {'+' if pnl >= 0 else ''}{pnl:.2f} USDT"
        print(msg)
        log_trade(datetime.now().isoformat(), symbol, "SELL", qty, price, pnl)
        await notifier.send_notification(msg)
    except Exception as e:
        print(f"❌ Error executing SELL order: {e}")


async def run_testnet_trade(interval_seconds: int = 60, dry_run: bool = True):
    config_path = os.path.join(BASE_DIR, "config.json")
    api_key, api_secret = None, None
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
                api_key = cfg.get("BINANCE_API_KEY")
                api_secret = cfg.get("BINANCE_API_SECRET")
                if api_key and api_secret:
                    dry_run = False
        except Exception:
            pass

    trader = BinanceTestnetTrader(
        api_key=api_key, api_secret=api_secret, dry_run=dry_run
    )

    position = None
    last_sentiment = "NEUTRAL"
    last_processed_news = ""
    positive_streak = 0
    positive_start_time = None
    price_history = []
    last_trade_time = None

    def load_recent_news_context() -> str:
        if pd is None:
            return "No previous news (pandas not installed)."
        try:
            df_old = pd.read_csv(TRADE_SUMMARY_FILE)
            last_news = df_old.dropna(subset=["news_title"]).tail(3)
            if not last_news.empty:
                recent_news_context = "Recent market events:\n"
                for _, row in last_news.iterrows():
                    recent_news_context += f"- [{row['verdict']}] {row['news_title']}\n"
                return recent_news_context
            return "No previous news. This is the first news in the session."
        except Exception:
            return "No previous news (file empty or pandas not installed)."

    async def record_trade() -> None:
        nonlocal last_trade_time
        last_trade_time = time.time()

    await notifier.send_notification(
        "🚀 Trading bot successfully started in Futures Monitor mode!"
    )

    symbol = "BTCUSDT"
    try:
        trader.set_leverage(symbol, LEVERAGE)
        print(f"🔒 Leverage for {symbol} locked: {LEVERAGE}x")
    except Exception as e:
        print(f"⚠️ Failed to set leverage for {symbol}: {e}")

    news_parser = NewsParser()
    start_news = await news_parser.init()
    seen_news = set()

    # Initial analysis of historical news on startup
    if start_news:
        print("🔍 Performing initial express market analysis on past news...")
        latest_start_news = start_news[-1]
        import re
        news_text_clean = re.sub(r'<[^>]+>', '', latest_start_news["content"]).strip()
        
        # Load recent trades for prompt context
        try:
            df_old = pd.read_csv(TRADE_SUMMARY_FILE)
            last_news = df_old.dropna(subset=['news_title']).tail(3)
            if not last_news.empty:
                recent_news_context = "Recent market events:\n"
                for _, row in last_news.iterrows():
                    recent_news_context += f"- [{row['verdict']}] {row['news_title']}\n"
            else:
                recent_news_context = "No previous news. This is the first news in the session."
        except Exception:
            recent_news_context = "No previous news (file empty)."

        prompt = (
            "Determine the sentiment of the news relative to Bitcoin (BTC).\n"
            f"News: {news_text_clean}\n\n"
            "Provide output STRICTLY as a JSON object, without extra text or markdown code blocks:\n"
            "{\n"
            '  "verdict": "EXCLUSIVE_POSITIVE" or "EXCLUSIVE_NEGATIVE" or "NEUTRAL",\n'
            '  "importance": number from 1 to 5,\n'
            '  "recommendation": "Brief demo recommendation in English."\n'
            "}"
        )
        
        try:
            raw_sentiment = await evaluate_sentiment(prompt, return_raw=True)
            clean_string = raw_sentiment.strip()
            if clean_string.startswith("```json"):
                clean_string = clean_string[7:]
            if clean_string.endswith("```"):
                clean_string = clean_string[:-3]
            clean_string = clean_string.strip()

            ai_data = json.loads(clean_string)
            start_verdict = ai_data.get("verdict", ai_data.get("VERDICT", "NEUTRAL")).upper()
            start_importance = int(ai_data.get("importance", ai_data.get("IMPORTANCE", 0)))
            start_rec = ai_data.get("recommendation", ai_data.get("RECOMMENDATION", ""))
        except Exception:
            start_verdict = "NEUTRAL"
            start_importance = 0
            start_rec = "Market observation. No active signals from initial analysis."
            
        update_ai_recommendation(start_verdict, start_importance, start_rec, news_text_clean)
        print(f"✅ Initial express analysis completed. Recommendation saved. Verdict: {start_verdict}")

    # === MAIN ENGINE LOOP ===
    while True:
        try:
            news_items = []
            try:
                news_items = await news_parser.get_news()
                new_unseen_items = [item for item in news_items if item["content"].strip() not in seen_news]

                if not new_unseen_items:
                    news_text = "No news found"
                else:
                    selected = new_unseen_items[0]
                    news_text = selected["content"]
                    seen_news.add(news_text.strip())

                    if len(seen_news) > 300:
                        seen_news.pop()
                        
            except Exception as e:
                print(f"Error fetching news: {e}")
                news_text = "Error loading news"

            import re
            news_text_clean = re.sub(r'<[^>]+>', '', news_text).strip()

            # Load recent trades for prompt context
            try:
                df_old = pd.read_csv(TRADE_SUMMARY_FILE)
                last_news = df_old.dropna(subset=['news_title']).tail(3)
                if not last_news.empty:
                    recent_news_context = "Recent market events:\n"
                    for _, row in last_news.iterrows():
                        recent_news_context += f"- [{row['verdict']}] {row['news_title']}\n"
                else:
                    recent_news_context = "No previous news. This is the first news in the session."
            except Exception:
                recent_news_context = "No previous news (file empty)."

            prompt = (
                "Determine the sentiment of the news relative to Bitcoin (BTC).\n"
                f"News: {news_text_clean}\n\n"
                "Provide output STRICTLY as a JSON object, without extra text or markdown code blocks:\n"
                "{\n"
                '  "verdict": "EXCLUSIVE_POSITIVE" or "EXCLUSIVE_NEGATIVE" or "NEUTRAL",\n'
                '  "importance": number from 1 to 5,\n'
                '  "recommendation": "Brief demo recommendation in English."\n'
                "}"
            )

            if news_items and news_text != "No news found" and news_text_clean != last_processed_news:
                last_processed_news = news_text_clean
                try:
                    raw_sentiment = await evaluate_sentiment(prompt, return_raw=True)
                except Exception as e:
                    print(f"Error calling local AI: {e}")
                    raw_sentiment = '{"verdict": "NEUTRAL", "importance": 0}'
            else:
                raw_sentiment = '{"verdict": "NEUTRAL", "importance": 0}'

            verdict = "NEUTRAL"
            importance = 0
            try:
                clean_string = raw_sentiment.strip()
                if clean_string.startswith("```json"):
                    clean_string = clean_string[7:]
                if clean_string.endswith("```"):
                    clean_string = clean_string[:-3]
                clean_string = clean_string.strip()

                ai_data = json.loads(clean_string)
                verdict = ai_data.get("verdict", ai_data.get("VERDICT", "NEUTRAL")).upper()
                importance = int(ai_data.get("importance", ai_data.get("IMPORTANCE", 0)))
                recommendation = ai_data.get("recommendation", ai_data.get("RECOMMENDATION", ""))

            except Exception:
                upper_raw = raw_sentiment.upper()
                if "EXCLUSIVE_POSITIVE" in upper_raw or "POSITIVE" in upper_raw or "ПОЗИТИВ" in upper_raw:
                    verdict = "EXCLUSIVE_POSITIVE"
                elif "EXCLUSIVE_NEGATIVE" in upper_raw or "NEGATIVE" in upper_raw or "НЕГАТИВ" in upper_raw:
                    verdict = "EXCLUSIVE_NEGATIVE"
                else:
                    verdict = "NEUTRAL"
                importance = 0
                recommendation = ""

            # Save AI recommendation to JSON on each news analysis
            if news_items and news_text != "No news found" and news_text_clean == last_processed_news:
                update_ai_recommendation(verdict, importance, recommendation, news_text_clean)

            print("\n=== Binance Testnet trade ===")
            print(f"News: {news_text}")
            print(f"Sentiment: {verdict} (Importance: {importance})")

            if news_items and news_text != "No news found":
                try:
                    NEWS_LOG_FILE = os.path.join(DATA_DIR, "news_history.csv")
                    created_new = not os.path.exists(NEWS_LOG_FILE)
                    with open(
                        NEWS_LOG_FILE, mode="a", newline="", encoding="utf-8"
                    ) as f:
                        writer = csv.writer(f)
                        if created_new:
                            writer.writerow(["timestamp", "content", "verdict"])
                        writer.writerow(
                            [datetime.now().isoformat(), news_text_clean, verdict]
                        )
                except Exception:
                    pass

            if verdict in ["EXCLUSIVE_POSITIVE", "POSITIVE"]:
                if positive_streak == 0:
                    positive_start_time = time.time()
                positive_streak += 1
            else:
                positive_streak = 0
                positive_start_time = None

            confidence_ok = positive_streak >= BUY_CONFIDENCE_REQUIRED or (
                positive_start_time is not None
                and time.time() - positive_start_time <= BUY_CONFIDENCE_WINDOW
            )
            print(
                f"Positive confidence: streak={positive_streak}, ok={confidence_ok}"
            )

            try:
                price = await run_with_retry(lambda: trader.get_price(symbol=symbol), context=f"price {symbol}")
                print(f"Current price of {symbol}: {price}")
            except Exception:
                price = position["entry_price"] if position else 60000.0

            sma = None
            if price is not None:
                price_history.append(price)
                if len(price_history) > SMA_PERIOD:
                    price_history = price_history[-SMA_PERIOD:]
                if len(price_history) >= SMA_PERIOD:
                    sma = sum(price_history[-SMA_PERIOD:]) / SMA_PERIOD

            if sma is not None:
                print(f"SMA{SMA_PERIOD}: {sma:.2f}, trend: {'bullish' if price > sma else 'bearish'}")
            else:
                print(f"Insufficient data for SMA{SMA_PERIOD} yet ({len(price_history)}/{SMA_PERIOD})")

            free_usdt_balance = 0.0
            try:
                usdt_bal = await run_with_retry(
                    lambda: trader.get_asset_balance("USDT"), context="balance USDT"
                )
                free_usdt_balance = float(usdt_bal.get("free") or 0.0)
                print(f"Balance: {free_usdt_balance} USDT.")
            except Exception:
                pass

            if free_usdt_balance < MIN_USDT_ORDER or price is None:
                trade_quantity = None
                order_amount_usdt = 0.0
            else:
                order_amount_usdt = round(free_usdt_balance * TRADE_PERCENT, 2)
                raw_quantity = order_amount_usdt / price
                trade_quantity = trader.get_valid_quantity(symbol, raw_quantity, price)

            if position and position.get("entry_price") and price:
                entry = position["entry_price"]
                qty = position["qty"]
                side = position["side"]

                if side == "BUY":
                    if "max_price" not in position:
                        position["max_price"] = price
                    if price > position["max_price"]:
                        position["max_price"] = price
                    
                    # Calculate current profit for break-even
                    unrealized_pnl_pct = (price - position['entry_price']) / position['entry_price']

                    # Break-even stop-loss logic
                    if not position.get('is_break_even') and unrealized_pnl_pct >= BREAK_EVEN_TRIGGER:
                        new_sl = position['entry_price'] * (1 + BREAK_EVEN_OFFSET)
                        position['stop_loss'] = new_sl
                        position['is_break_even'] = True  # Flag to avoid redundant updates
                        msg = f"🛡️ [BREAK-EVEN] Profit +{unrealized_pnl_pct*100:.2f}%. Stop moved to {new_sl:.2f}"
                        print(msg)
                        await notifier.send_notification(msg)

                    pnl = (price - entry) * qty
                    change = (price - entry) / entry
                    drawback = (position["max_price"] - price) / position["max_price"]
                    
                    if change <= -HARD_STOP_LOSS_PERCENT:
                        await execute_sell_order(trader, symbol, qty, price, pnl, "HARD STOP LOSS")
                        log_completed_trade(datetime.now().isoformat(), symbol, position["entry_time"], entry, price, qty, pnl, position["entry_reason"], "hard_stop_loss", news_title=news_text_clean, verdict=verdict, recommendation=recommendation)
                        position = None
                    elif change >= TAKE_PROFIT_PERCENT and drawback >= TRAILING_DROP_PERCENT:
                        await execute_sell_order(trader, symbol, qty, price, pnl, "TAKE PROFIT")
                        log_completed_trade(datetime.now().isoformat(), symbol, position["entry_time"], entry, price, qty, pnl, position["entry_reason"], "take_profit", news_title=news_text_clean, verdict=verdict, recommendation=recommendation)
                        position = None
                    elif change <= -STOP_LOSS_PERCENT:
                        await execute_sell_order(trader, symbol, qty, price, pnl, "STOP LOSS")
                        log_completed_trade(datetime.now().isoformat(), symbol, position["entry_time"], entry, price, qty, pnl, position["entry_reason"], "stop_loss", news_title=news_text_clean, verdict=verdict, recommendation=recommendation)
                        position = None

                else:
                    if "min_price" not in position:
                        position["min_price"] = price
                    if price < position["min_price"]:
                        position["min_price"] = price
                    
                    pnl = (entry - price) * qty
                    change = (entry - price) / entry
                    drawback = (price - position["min_price"]) / position["min_price"]

                    if change <= -HARD_STOP_LOSS_PERCENT:
                        await execute_buy_order(trader, symbol, qty, qty * price, price, "HARD STOP LOSS SHORT")
                        log_completed_trade(datetime.now().isoformat(), symbol, position["entry_time"], entry, price, qty, pnl, position["entry_reason"], "hard_stop_loss_short", news_title=news_text_clean, verdict=verdict, recommendation=recommendation)
                        position = None
                    elif (
                        change >= TAKE_PROFIT_PERCENT
                        and drawback >= TRAILING_DROP_PERCENT
                    ):
                        await execute_buy_order(trader, symbol, qty, qty * price, price, "TAKE PROFIT SHORT")
                        log_completed_trade(datetime.now().isoformat(), symbol, position["entry_time"], entry, price, qty, pnl, position["entry_reason"], "take_profit_short", news_title=news_text_clean, verdict=verdict, recommendation=recommendation)
                        position = None
                    elif change <= -STOP_LOSS_PERCENT:
                        await execute_buy_order(trader, symbol, qty, qty * price, price, "STOP LOSS SHORT")
                        log_completed_trade(datetime.now().isoformat(), symbol, position["entry_time"], entry, price, qty, pnl, position["entry_reason"], "stop_loss_short", news_title=news_text_clean, verdict=verdict, recommendation=recommendation)
                        position = None

            can_enter_trade = True
            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                can_enter_trade = False

            if verdict in ["EXCLUSIVE_POSITIVE", "POSITIVE"]:
                if position and position.get("side") == "SELL":
                    print("📈 Market sentiment is POSITIVE. Closing SHORT position immediately.")
                    gross_pnl = (position["entry_price"] - price) * position["qty"]
                    fee_cost = (
                        position["qty"] * position["entry_price"]
                        + position["qty"] * price
                    ) * TAKER_FEE_RATE
                    net_pnl = gross_pnl - fee_cost
                    await execute_buy_order(
                        trader,
                        symbol,
                        position["qty"],
                        position["qty"] * price,
                        price,
                        "NEWS REVERSAL SHORT CLOSE",
                    )
                    log_completed_trade(
                        datetime.now().isoformat(),
                        symbol,
                        position["entry_time"],
                        position["entry_price"],
                        price,
                        position["qty"],
                        net_pnl,
                        position["entry_reason"],
                        "news_reversal",
                        news_title=news_text_clean,
                        verdict=verdict,
                        recommendation=recommendation,
                    )
                    print(
                        f"💸 Gross PnL: {gross_pnl:.2f} | Fees: {fee_cost:.2f} | Net PnL: {net_pnl:.2f} USDT"
                    )
                    position = None
                    await record_trade()
                elif position is None:
                    if not can_enter_trade:
                        print("⏳ Long entry skipped: cooldown.")
                    elif importance < MIN_IMPORTANCE:
                        print(
                            f"💎 Skipped: importance ({importance}) below threshold ({MIN_IMPORTANCE})."
                        )
                    elif not confidence_ok:
                        print("📉 Skipped: no news streak.")
                    elif sma is None:
                        print("📊 Skipped: SMA is accumulating data.")
                    elif price <= sma:
                        print("🐻 Skipped: price below SMA — bearish trend.")
                    elif not trade_quantity:
                        print("❌ Skipped: lot size not calculated.")
                    else:
                        if importance >= 5:
                            print(
                                f"🚨 IMPORTANCE 5 NEWS! Delaying {SLIPPAGE_DELAY_HIGH_IMPACT}s before entry..."
                            )
                            await asyncio.sleep(SLIPPAGE_DELAY_HIGH_IMPACT)
                            try:
                                new_price = await run_with_retry(
                                    lambda: trader.get_price(symbol=symbol),
                                    context=f"price {symbol} post-delay",
                                )
                                slippage = abs(new_price - price) / price
                                if slippage > SLIPPAGE_PANIC:
                                    print(
                                        f"⛔ Entry CANCELLED: slippage {slippage * 100:.2f}% > {SLIPPAGE_PANIC * 100:.1f}%."
                                    )
                                else:
                                    print(
                                        f"📉 Slippage: {slippage * 100:.2f}% (price changed from {price:.2f} to {new_price:.2f})"
                                    )
                                    adjusted_slippage = max(slippage, SLIPPAGE_BUFFER)
                                    effective_price = new_price * (
                                        1 + adjusted_slippage
                                    )
                                    print(
                                        f"🔧 Effective price with buffer: {effective_price:.2f}"
                                    )
                            except Exception:
                                print(
                                    "⚠️ Failed to reread price after delay, entering at original price."
                                )
                                effective_price = price
                        else:
                            effective_price = price

                        await execute_buy_order(
                            trader,
                            symbol,
                            trade_quantity,
                            order_amount_usdt,
                            effective_price,
                            "OPEN LONG",
                        )
                        position = {
                            "side": "BUY",
                            "qty": trade_quantity,
                            "entry_price": effective_price,
                            "entry_time": datetime.now().isoformat(),
                            "entry_reason": "news_sentiment_positive",
                            "max_price": effective_price,
                            "is_break_even": False,
                        }
                        await record_trade()

            elif verdict in ["EXCLUSIVE_NEGATIVE", "NEGATIVE"]:
                if position and position.get("side") == "BUY":
                    print("📉 Market sentiment is NEGATIVE. Closing LONG position immediately.")
                    gross_pnl = (price - position["entry_price"]) * position["qty"]
                    fee_cost = (position["qty"] * position["entry_price"] + position["qty"] * price) * TAKER_FEE_RATE
                    net_pnl = gross_pnl - fee_cost
                    await execute_sell_order(trader, symbol, position["qty"], price, net_pnl, "NEWS REVERSAL LONG CLOSE")
                    log_completed_trade(datetime.now().isoformat(), symbol, position["entry_time"], position["entry_price"], price, position["qty"], net_pnl, position["entry_reason"], "news_reversal", news_title=news_text_clean, verdict=verdict, recommendation=recommendation)
                    print(f"💸 Gross PnL: {gross_pnl:.2f} | Fees: {fee_cost:.2f} | Net PnL: {net_pnl:.2f} USDT")
                    position = None
                    await record_trade()
                elif position is None:
                    if not can_enter_trade: print("⏳ Short entry skipped: cooldown.")
                    elif importance < MIN_IMPORTANCE: print(f"💎 Skipped short: importance ({importance}) below threshold ({MIN_IMPORTANCE}).")
                    elif sma is None: print("📊 Skipped short: SMA is accumulating data.")
                    elif price >= sma: print("🐂 Skipped short: price above SMA — bullish trend.")
                    elif not trade_quantity: print("❌ Skipped short: lot size not calculated.")
                    else:
                        if importance >= 5:
                            print(
                                f"🚨 IMPORTANCE 5 NEWS! Delaying {SLIPPAGE_DELAY_HIGH_IMPACT}s before entry..."
                            )
                            await asyncio.sleep(SLIPPAGE_DELAY_HIGH_IMPACT)
                            try:
                                new_price = await run_with_retry(lambda: trader.get_price(symbol=symbol), context=f"price {symbol} post-delay")
                                slippage = abs(new_price - price) / price
                                if slippage > SLIPPAGE_PANIC:
                                    print(
                                        f"⛔ Entry CANCELLED: slippage {slippage * 100:.2f}% > {SLIPPAGE_PANIC * 100:.1f}%."
                                    )
                                else:
                                    print(f"📉 Slippage: {slippage*100:.2f}% (price changed from {price:.2f} to {new_price:.2f})")
                                    adjusted_slippage = max(slippage, SLIPPAGE_BUFFER)
                                    effective_price = new_price * (
                                        1 - adjusted_slippage
                                    )
                                    print(f"🔧 Effective price with buffer: {effective_price:.2f}")
                            except Exception:
                                print("⚠️ Failed to reread price after delay, entering at original price.")
                                effective_price = price
                        else:
                            effective_price = price

                        await execute_sell_order(trader, symbol, trade_quantity, effective_price, None, "OPEN SHORT")
                        position = {"side": "SELL", "qty": trade_quantity, "entry_price": effective_price, "entry_time": datetime.now().isoformat(), "entry_reason": "news_sentiment_negative", "min_price": effective_price}
                        await record_trade()

        except Exception as e:
            print(f"An error occurred during loop execution: {e}")

        last_sentiment = verdict
        print(f"Waiting {interval_seconds}s before next analysis...")
        await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    try:
        import argparse

        parser = argparse.ArgumentParser(description="Binance Testnet News-Based Trader")
        parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")
        parser.add_argument("--backtest", action="store_true", help="Run on historical data instead of live news")
        parser.add_argument("--history-csv", type=str, default="historical_prices.csv", help="Path to historical CSV or news history CSV")
        parser.add_argument("--price-csv", type=str, default=None, help="Optional candle price CSV to align news history timestamps with real prices")
        parser.add_argument("--start-usdt", type=float, default=100000.0, help="Starting USDT balance for backtest")
        parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds")
        args = parser.parse_args()

        if args.backtest:
            from backtest import run_backtest
            run_backtest(args.history_csv, price_csv=args.price_csv, starting_usdt=args.start_usdt)
        else:
            asyncio.run(run_testnet_trade(interval_seconds=args.interval, dry_run=args.dry_run))
    except KeyboardInterrupt:
        print("\n🛑 Robot stopped by user.")