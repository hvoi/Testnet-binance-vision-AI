import bisect
import csv
import json
import math
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

TRADE_PERCENT = 0.10
MIN_USDT_ORDER = 11.0
SMA_PERIOD = 20
BUY_CONFIDENCE_REQUIRED = 3
BUY_CONFIDENCE_WINDOW = 30
MIN_IMPORTANCE = 4
STOP_LOSS_PERCENT = 0.010
HARD_STOP_LOSS_PERCENT = 0.020
TAKE_PROFIT_PERCENT = 0.025
TRAILING_DROP_PERCENT = 0.003
BREAK_EVEN_TRIGGER = 0.015
BREAK_EVEN_OFFSET = 0.001
TAKER_FEE_RATE = 0.0005


def parse_timestamp(raw_timestamp: str) -> datetime:
    if raw_timestamp is None:
        raise ValueError("Timestamp value is missing")
    timestamp = str(raw_timestamp).strip()
    if not timestamp:
        raise ValueError("Timestamp string is empty")

    if timestamp.isdigit() or (timestamp.replace('.', '', 1).isdigit() and timestamp.count('.') == 1):
        value = float(timestamp)
        if value > 1e12:
            value /= 1000.0
        parsed = datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        return parsed

    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(timestamp, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unable to parse timestamp: {raw_timestamp}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


try:
    _cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(_cfg_path):
        with open(_cfg_path, "r", encoding="utf-8-sig") as _f:
            _cfg = json.load(_f)
            SMA_PERIOD = int(_cfg.get("SMA_PERIOD", SMA_PERIOD))
            STOP_LOSS_PERCENT = float(_cfg.get("STOP_LOSS_PERCENT", STOP_LOSS_PERCENT))
            TAKE_PROFIT_PERCENT = float(_cfg.get("TAKE_PROFIT_PERCENT", TAKE_PROFIT_PERCENT))
            BUY_CONFIDENCE_REQUIRED = int(_cfg.get("BUY_CONFIDENCE_REQUIRED", BUY_CONFIDENCE_REQUIRED))
            BUY_CONFIDENCE_WINDOW = int(_cfg.get("BUY_CONFIDENCE_WINDOW", BUY_CONFIDENCE_WINDOW))
except Exception:
    pass

try:
    SMA_PERIOD = int(os.getenv("SMA_PERIOD", SMA_PERIOD))
except Exception:
    pass
try:
    STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", STOP_LOSS_PERCENT))
except Exception:
    pass
try:
    HARD_STOP_LOSS_PERCENT = float(os.getenv("HARD_STOP_LOSS_PERCENT", HARD_STOP_LOSS_PERCENT))
except Exception:
    pass
try:
    TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", TAKE_PROFIT_PERCENT))
except Exception:
    pass
try:
    BUY_CONFIDENCE_REQUIRED = int(os.getenv("BUY_CONFIDENCE_REQUIRED", BUY_CONFIDENCE_REQUIRED))
except Exception:
    pass
try:
    BUY_CONFIDENCE_WINDOW = int(os.getenv("BUY_CONFIDENCE_WINDOW", BUY_CONFIDENCE_WINDOW))
except Exception:
    pass


def normalize_dataframe_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    if pd is None:
        return df

    mappings = {
        "timestamp": ["timestamp", "time", "datetime", "open_time", "date"],
        "price": ["price", "close", "close_price", "price_usdt"],
        "verdict": ["verdict", "sentiment", "label"],
        "news_title": ["news_title", "title", "content", "headline"],
        "importance": ["importance", "impact", "score"],
        "recommendation": ["recommendation", "note", "comment"],
    }

    columns = {col.lower().strip(): col for col in df.columns if col is not None}
    rename_map = {}
    for canonical, variants in mappings.items():
        for variant in variants:
            if variant in columns:
                rename_map[columns[variant]] = canonical
                break
    return df.rename(columns=rename_map)


def _read_news_csv_dataframe(news_path: str) -> "pd.DataFrame":
    rows: List[Dict[str, str]] = []
    with open(news_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        for index, row in enumerate(reader, start=1):
            if not row:
                continue
            if index == 1:
                continue
            if len(row) < 2:
                continue

            timestamp = row[0].strip()
            sentiment = row[-1].strip() if len(row) > 1 else ""
            title = " ".join(part.strip() for part in row[1:-1] if part and part.strip()) if len(row) > 2 else ""
            rows.append({"Timestamp": timestamp, "Title": title, "Sentiment": sentiment})

    if not rows:
        raise ValueError(f"Unable to parse any news rows from {news_path}")
    return pd.DataFrame(rows)


def load_and_sync_data(news_path: str, price_path: str, max_gap: str = "5min") -> List[Dict[str, Any]]:
    if pd is None:
        raise ImportError("Pandas is required for load_and_sync_data. Install pandas or use the fallback reader.")

    df_news = pd.read_csv(news_path, engine="python", on_bad_lines="skip")
    df_price = pd.read_csv(price_path)

    df_news = normalize_dataframe_columns(df_news)
    df_price = normalize_dataframe_columns(df_price)

    if "timestamp" not in df_news.columns or "timestamp" not in df_price.columns:
        raise ValueError("Both news and price CSV files must contain a timestamp column.")

    df_news["timestamp"] = pd.to_datetime(df_news["timestamp"], utc=True, errors="coerce")
    df_price["timestamp"] = pd.to_datetime(df_price["timestamp"], utc=True, errors="coerce")

    df_news = df_news.sort_values("timestamp").reset_index(drop=True)
    df_price = df_price.sort_values("timestamp").reset_index(drop=True)

    df_news = df_news.dropna(subset=["timestamp"])
    df_price = df_price.dropna(subset=["timestamp"])

    news_min = df_news["timestamp"].min()
    news_max = df_news["timestamp"].max()
    price_min = df_price["timestamp"].min()
    price_max = df_price["timestamp"].max()
    if price_max < news_min:
        raise ValueError(
            "Price data ends before news timestamps start. Update historical_prices.csv so it covers news period."
        )
    if price_min > news_max:
        raise ValueError(
            "Price data starts after news timestamps end. Provide price CSV that overlaps news period."
        )

    if "price" not in df_price.columns:
        raise ValueError("Price CSV must contain a price or close column.")

    merged = pd.merge_asof(
        df_news,
        df_price[["timestamp", "price"]],
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta(max_gap),
    )

    nan_count = int(merged["price"].isna().sum())
    print(f"DEBUG: Empty prices after merge: {nan_count} of {len(merged)}")
    if nan_count == len(merged):
        raise ValueError(
            "No matching candle prices found for any news timestamps. "
            "Verify date overlaps between news_history.csv and historical_prices.csv."
        )

    unmatched = merged[merged["price"].isna()]
    print(f"Loaded news rows: {len(df_news)}")
    print(f"Loaded price rows: {len(df_price)}")
    print(f"Matched rows: {len(merged) - len(unmatched)}; unmatched news rows: {len(unmatched)}")
    if len(unmatched) > 0:
        print("First unmatched news timestamps:")
        for ts in unmatched["timestamp"].head(5):
            print(f"  - {ts}")

    merged = merged.dropna(subset=["price"]).reset_index(drop=True)

    return [
        {
            "timestamp": row["timestamp"].isoformat(),
            "price": float(row["price"]),
            "verdict": str(row.get("verdict", "NEUTRAL")).upper(),
            "importance": int(row.get("importance", 0) or 0) if pd.notna(row.get("importance", 0)) else 0,
            "recommendation": str(row.get("recommendation", "")),
            "news_title": str(row.get("news_title", "")),
        }
        for _, row in merged.iterrows()
    ]


def _normalize_csv_key(row: Dict[str, str], candidates: List[str]) -> Optional[str]:
    for key in row:
        if key is None:
            continue
        normalized = key.strip().lower()
        for candidate in candidates:
            if normalized == candidate.lower():
                return key
    return None


def load_price_candles(price_csv_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(price_csv_path):
        raise FileNotFoundError(f"Price candles file not found: {price_csv_path}")

    candles: List[Dict[str, Any]] = []
    with open(price_csv_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            ts_key = _normalize_csv_key(row, ["timestamp", "time", "datetime", "open_time", "date"])
            price_key = _normalize_csv_key(row, ["close", "price", "close_price"])
            if ts_key is None or price_key is None:
                continue
            try:
                timestamp = parse_timestamp(row[ts_key])
                price = float(row[price_key])
            except Exception:
                continue
            candles.append({"timestamp": timestamp, "price": price, "raw": row})

    if not candles:
        raise ValueError(f"No valid candles were loaded from {price_csv_path}")
    candles.sort(key=lambda item: item["timestamp"])
    return candles


def load_news_history(news_csv_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(news_csv_path):
        raise FileNotFoundError(f"News history file not found: {news_csv_path}")

    rows: List[Dict[str, Any]] = []
    with open(news_csv_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            ts_key = _normalize_csv_key(row, ["timestamp", "time", "datetime", "date"])
            sentiment_key = _normalize_csv_key(row, ["sentiment", "verdict", "label"])
            if ts_key is None or sentiment_key is None:
                continue

            title_key = _normalize_csv_key(row, ["title", "content", "news_title", "headline"])
            importance_key = _normalize_csv_key(row, ["importance", "impact", "score"])
            recommendation_key = _normalize_csv_key(row, ["recommendation", "note", "comment"])

            sentiment = (row.get(sentiment_key) or "").strip().upper()
            if sentiment in ("EXCLUSIVE_POSITIVE", "POSITIVE", "ПОЗИТИВ"):
                sentiment = "EXCLUSIVE_POSITIVE"
            elif sentiment in ("EXCLUSIVE_NEGATIVE", "NEGATIVE", "НЕГАТИВ"):
                sentiment = "EXCLUSIVE_NEGATIVE"
            else:
                sentiment = "NEUTRAL"

            importance = 0
            if importance_key:
                try:
                    importance = int(float(row.get(importance_key) or 0))
                except Exception:
                    importance = 0
            if importance <= 0:
                importance = 4 if sentiment in ("EXCLUSIVE_POSITIVE", "EXCLUSIVE_NEGATIVE") else 1

            rows.append(
                {
                    "timestamp": parse_timestamp(row[ts_key]),
                    "price": 0.0,
                    "verdict": sentiment,
                    "importance": importance,
                    "recommendation": (row.get(recommendation_key) or "News signal").strip() if recommendation_key else "News signal",
                    "news_title": (row.get(title_key) or "news_history event").strip() if title_key else "news_history event",
                }
            )

    if not rows:
        raise ValueError(f"No valid news rows found in {news_csv_path}")
    rows.sort(key=lambda item: item["timestamp"])
    return rows


def get_price_for_timestamp(news_ts: datetime, candles: List[Dict[str, Any]]) -> float:
    timestamps = [candle["timestamp"] for candle in candles]
    index = bisect.bisect_right(timestamps, news_ts)
    if index == 0:
        return candles[0]["price"]
    if index >= len(candles):
        return candles[-1]["price"]

    previous_candle = candles[index - 1]
    next_candle = candles[index]
    if (news_ts - previous_candle["timestamp"]) <= (next_candle["timestamp"] - news_ts):
        return previous_candle["price"]
    return next_candle["price"]


def merge_news_with_prices(news_rows: List[Dict[str, Any]], candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for row in news_rows:
        merged.append(
            {
                "timestamp": row["timestamp"].isoformat(),
                "price": get_price_for_timestamp(row["timestamp"], candles),
                "verdict": row["verdict"],
                "importance": row["importance"],
                "recommendation": row["recommendation"],
                "news_title": row["news_title"],
            }
        )
    return merged


def read_history(csv_path: str, price_csv: Optional[str] = None) -> List[Dict[str, Any]]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"History file not found: {csv_path}")

    rows: List[Dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        fieldnames = [h.lower() for h in (reader.fieldnames or [])]
        has_price = any(key in fieldnames for key in ("price", "close", "close_price"))
        if not has_price:
            if price_csv is None:
                candidate = os.path.join(os.path.dirname(csv_path), "historical_prices.csv")
                if os.path.exists(candidate):
                    price_csv = candidate
                else:
                    raise ValueError(
                        "History CSV does not contain price data. Provide --price-csv with a candle data file."
                    )
            if pd is not None:
                return load_and_sync_data(csv_path, price_csv)
            return merge_news_with_prices(load_news_history(csv_path), load_price_candles(price_csv))

        for row in reader:
            price = float(row.get("price", row.get("close", "0")) or 0)
            verdict = (row.get("verdict") or row.get("Sentiment") or "NEUTRAL").upper()
            if verdict in ("EXCLUSIVE_POSITIVE", "POSITIVE", "ПОЗИТИВ"):
                verdict = "EXCLUSIVE_POSITIVE"
            elif verdict in ("EXCLUSIVE_NEGATIVE", "NEGATIVE", "НЕГАТИВ"):
                verdict = "EXCLUSIVE_NEGATIVE"
            else:
                verdict = "NEUTRAL"
            
            importance_raw = row.get("importance") or row.get("Importance") or ""
            try:
                importance = int(float(importance_raw)) if importance_raw else 0
            except Exception:
                importance = 0
            if importance <= 0:
                importance = 4 if verdict in ("EXCLUSIVE_POSITIVE", "EXCLUSIVE_NEGATIVE") else 1
            rows.append(
                {
                    "timestamp": row.get("timestamp") or row.get("time") or "",
                    "price": price,
                    "verdict": verdict,
                    "importance": importance,
                    "recommendation": row.get("recommendation", ""),
                    "news_title": row.get("news_title", "historical signal"),
                }
            )
    return rows


class BacktestTrader:
    def __init__(self, starting_usdt: float = 100000.0) -> None:
        self.balance_usdt = Decimal(str(starting_usdt))
        self.balance_btc = Decimal("0")
        self.price = Decimal("0")
        self.orders: List[Dict[str, Any]] = []

    def set_price(self, price: float) -> None:
        self.price = Decimal(str(price))

    def get_asset_balance(self, asset: str) -> Dict[str, str]:
        if asset == "USDT":
            return {"free": str(self.balance_usdt), "locked": "0.0"}
        if asset == "BTC":
            return {"free": str(self.balance_btc), "locked": "0.0"}
        return {"free": "0.0", "locked": "0.0"}

    def place_order(self, symbol: str, side: str, type: str, quantity: float) -> Dict[str, Any]:
        side = side.upper()
        qty = Decimal(str(quantity))
        gross = qty * self.price
        fee = (gross * Decimal(str(TAKER_FEE_RATE))).quantize(Decimal("0.01"))
        if side == "BUY":
            total_cost = (gross + fee).quantize(Decimal("0.01"))
            self.balance_usdt -= total_cost
            self.balance_btc += qty
        else:
            proceeds = (gross - fee).quantize(Decimal("0.01"))
            self.balance_usdt += proceeds
            self.balance_btc -= qty

        self.orders.append({
            "symbol": symbol,
            "side": side,
            "qty": float(qty),
            "price": float(self.price),
            "fee": float(fee),
            "timestamp": datetime.now().isoformat(),
        })
        return {
            "symbol": symbol,
            "side": side,
            "type": type,
            "origQty": str(qty),
            "executedQty": str(qty),
            "cummulativeQuoteQty": str(gross.quantize(Decimal("0.01"))),
            "status": "FILLED",
        }


def normalize_quantity(raw_qty: float) -> Optional[float]:
    if raw_qty <= 0:
        return None
    return raw_qty


def run_backtest(history_csv: str, price_csv: Optional[str] = None, starting_usdt: float = 100000.0) -> None:
    history = read_history(history_csv, price_csv)
    if not history:
        raise ValueError("History file is empty or invalid.")

    trader = BacktestTrader(starting_usdt)
    position: Optional[Dict[str, Any]] = None
    price_history: List[float] = []
    positive_streak = 0
    positive_start_time = 0.0
    last_trade_time = 0.0
    trade_count = 0
    total_pnl = Decimal("0")
    closed_trades = 0
    win_trades = 0
    skipped_neutral = 0
    skipped_importance = 0
    skipped_nan_price = 0
    skipped_by_trend = 0
    skipped_already_in_position = 0

    for row_index, row in enumerate(history, start=1):
        price = row["price"]
        if price is None or (isinstance(price, float) and math.isnan(price)):
            skipped_nan_price += 1
            continue

        verdict = row["verdict"]
        importance = int(row.get("importance", 0) or 0)
        if verdict == "NEUTRAL":
            skipped_neutral += 1
            continue
        if int(row.get("importance", 0) or 0) < 0:
            skipped_importance += 1
            continue

        recommendation = row["recommendation"]
        news_title = row["news_title"]
        timestamp = row["timestamp"] or datetime.now().isoformat()

        trader.set_price(price)
        price_history.append(price)
        if SMA_PERIOD > 0:
            if len(price_history) > SMA_PERIOD:
                price_history = price_history[-SMA_PERIOD:]
            sma = sum(price_history[-SMA_PERIOD:]) / SMA_PERIOD if len(price_history) >= SMA_PERIOD else None
        else:
            sma = None

        if verdict == "EXCLUSIVE_POSITIVE":
            if positive_streak == 0:
                positive_start_time = row_index
            positive_streak += 1
        else:
            positive_streak = 0
            positive_start_time = 0

        confidence_ok = positive_streak >= BUY_CONFIDENCE_REQUIRED or (
            positive_start_time != 0 and (row_index - positive_start_time) <= BUY_CONFIDENCE_WINDOW
        )

        free_usdt_balance = float(trader.get_asset_balance("USDT")["free"])
        if free_usdt_balance < MIN_USDT_ORDER or price <= 0:
            trade_quantity = None
            order_amount_usdt = 0.0
        else:
            order_amount_usdt = round(free_usdt_balance * TRADE_PERCENT, 2)
            raw_quantity = order_amount_usdt / price
            trade_quantity = normalize_quantity(raw_quantity)

        if position and price:
            entry = Decimal(str(position["entry_price"]))
            qty = Decimal(str(position["qty"]))
            current_price = Decimal(str(price))
            if position["side"] == "BUY":
                if "max_price" not in position:
                    position["max_price"] = price
                if current_price > Decimal(str(position["max_price"])):
                    position["max_price"] = float(current_price)
                unrealized_pct = (current_price - entry) / entry
                if not position.get("is_break_even") and unrealized_pct >= Decimal(str(BREAK_EVEN_TRIGGER)):
                    position["stop_loss"] = entry * (Decimal("1") + Decimal(str(BREAK_EVEN_OFFSET)))
                    position["is_break_even"] = True
                pnl = (current_price - entry) * qty
                change = (current_price - entry) / entry
                drawback = (Decimal(str(position["max_price"])) - current_price) / Decimal(str(position["max_price"]))
                if change <= Decimal(str(-HARD_STOP_LOSS_PERCENT)):
                    trader.place_order("BTCUSDT", "SELL", "MARKET", float(qty))
                    total_pnl += pnl
                    closed_trades += 1
                    if pnl > 0:
                        win_trades += 1
                    position = None
                elif change >= Decimal(str(TAKE_PROFIT_PERCENT)) and drawback >= Decimal(str(TRAILING_DROP_PERCENT)):
                    trader.place_order("BTCUSDT", "SELL", "MARKET", float(qty))
                    total_pnl += pnl
                    closed_trades += 1
                    if pnl > 0:
                        win_trades += 1
                    position = None
                elif change <= Decimal(str(-STOP_LOSS_PERCENT)):
                    trader.place_order("BTCUSDT", "SELL", "MARKET", float(qty))
                    total_pnl += pnl
                    closed_trades += 1
                    if pnl > 0:
                        win_trades += 1
                    position = None
            else:
                if "min_price" not in position:
                    position["min_price"] = price
                if current_price < Decimal(str(position["min_price"])):
                    position["min_price"] = float(current_price)
                pnl = (entry - current_price) * qty
                change = (entry - current_price) / entry
                drawback = (current_price - Decimal(str(position["min_price"]))) / Decimal(str(position["min_price"]))
                if change <= Decimal(str(-HARD_STOP_LOSS_PERCENT)):
                    trader.place_order("BTCUSDT", "BUY", "MARKET", float(qty))
                    total_pnl += pnl
                    closed_trades += 1
                    if pnl > 0:
                        win_trades += 1
                    position = None
                elif change >= Decimal(str(TAKE_PROFIT_PERCENT)) and drawback >= Decimal(str(TRAILING_DROP_PERCENT)):
                    trader.place_order("BTCUSDT", "BUY", "MARKET", float(qty))
                    total_pnl += pnl
                    closed_trades += 1
                    if pnl > 0:
                        win_trades += 1
                    position = None
                elif change <= Decimal(str(-STOP_LOSS_PERCENT)):
                    trader.place_order("BTCUSDT", "BUY", "MARKET", float(qty))
                    total_pnl += pnl
                    closed_trades += 1
                    if pnl > 0:
                        win_trades += 1
                    position = None

        can_enter_trade = True
        if last_trade_time != 0 and (row_index - last_trade_time) < 1:
            can_enter_trade = False

        can_open_long = (
            verdict == "EXCLUSIVE_POSITIVE"
            and confidence_ok
            and trade_quantity
        )
        can_open_short = (
            verdict == "EXCLUSIVE_NEGATIVE"
            and trade_quantity
        )

        if verdict == "EXCLUSIVE_POSITIVE":
            if SMA_PERIOD == 0:
                trend_aligned = True
            else:
                original_trend_ok = sma is not None and price > sma
                if not original_trend_ok:
                    skipped_by_trend += 1
                trend_aligned = original_trend_ok
            if position is None:
                if can_enter_trade and can_open_long and trend_aligned:
                    trader.place_order("BTCUSDT", "BUY", "MARKET", trade_quantity)
                    position = {
                        "side": "BUY",
                        "qty": trade_quantity,
                        "entry_price": price,
                        "entry_time": timestamp,
                        "entry_reason": "news_sentiment_positive",
                        "max_price": price,
                        "is_break_even": False,
                    }
                    last_trade_time = row_index
                    trade_count += 1
            elif position["side"] == "BUY":
                if can_enter_trade and can_open_long and trend_aligned and trade_quantity:
                    existing_qty = Decimal(str(position["qty"]))
                    addition_qty = Decimal(str(trade_quantity))
                    existing_entry = Decimal(str(position["entry_price"]))
                    new_qty = existing_qty + addition_qty
                    weighted_entry = (
                        (existing_entry * existing_qty) + (Decimal(str(price)) * addition_qty)
                    ) / new_qty
                    position["qty"] = float(new_qty)
                    position["entry_price"] = float(weighted_entry)
                    if price > Decimal(str(position["max_price"])):
                        position["max_price"] = price
                    trader.place_order("BTCUSDT", "BUY", "MARKET", trade_quantity)
                    last_trade_time = row_index
                    trade_count += 1
            else:
                if can_open_long:
                    skipped_already_in_position += 1
        elif verdict == "EXCLUSIVE_NEGATIVE":
            if SMA_PERIOD == 0:
                trend_aligned = True
            else:
                original_trend_ok = sma is not None and price < sma
                if not original_trend_ok:
                    skipped_by_trend += 1
                trend_aligned = original_trend_ok
            if position is None:
                if can_enter_trade and can_open_short and trend_aligned:
                    trader.place_order("BTCUSDT", "SELL", "MARKET", trade_quantity)
                    position = {
                        "side": "SELL",
                        "qty": trade_quantity,
                        "entry_price": price,
                        "entry_time": timestamp,
                        "entry_reason": "news_sentiment_negative",
                        "min_price": price,
                    }
                    last_trade_time = row_index
                    trade_count += 1
            elif position["side"] == "SELL":
                if can_enter_trade and can_open_short and trend_aligned and trade_quantity:
                    existing_qty = Decimal(str(position["qty"]))
                    addition_qty = Decimal(str(trade_quantity))
                    existing_entry = Decimal(str(position["entry_price"]))
                    new_qty = existing_qty + addition_qty
                    weighted_entry = (
                        (existing_entry * existing_qty) + (Decimal(str(price)) * addition_qty)
                    ) / new_qty
                    position["qty"] = float(new_qty)
                    position["entry_price"] = float(weighted_entry)
                    if price < Decimal(str(position["min_price"])):
                        position["min_price"] = price
                    trader.place_order("BTCUSDT", "SELL", "MARKET", trade_quantity)
                    last_trade_time = row_index
                    trade_count += 1
            else:
                if can_open_short:
                    skipped_already_in_position += 1

    initial_usdt_balance = Decimal(str(starting_usdt))
    final_usdt_balance = Decimal(str(trader.get_asset_balance("USDT")["free"]))
    final_btc_balance = Decimal(str(trader.get_asset_balance("BTC")["free"]))
    last_market_price = Decimal(str(price))

    current_crypto_value = final_btc_balance * last_market_price
    total_equity = final_usdt_balance + current_crypto_value
    unrealized_pnl = total_equity - initial_usdt_balance

    realised_pnl = total_pnl
    trades_executed = trade_count
    if final_btc_balance != Decimal("0"):
        closing_notional = abs(final_btc_balance * last_market_price)
        fee = closing_notional * Decimal(str(TAKER_FEE_RATE))
        if position is not None:
            entry = Decimal(str(position.get("entry_price", 0)))
            qty = Decimal(str(position.get("qty", 0)))
            if position.get("side") == "BUY":
                final_pnl = (last_market_price - entry) * qty
            else:
                final_pnl = (entry - last_market_price) * qty
            closed_trades += 1
            if final_pnl > 0:
                win_trades += 1
        if final_btc_balance > 0:
            final_usdt_balance += closing_notional - fee
        else:
            final_usdt_balance -= closing_notional + fee
        final_btc_balance = Decimal("0")
        trades_executed += 1
        realised_pnl = final_usdt_balance - initial_usdt_balance
        total_equity = final_usdt_balance
        unrealized_pnl = total_equity - initial_usdt_balance

    print("=== Backtest summary ===")
    print(f"Rows processed: {len(history)}")
    print(f"Trades executed: {trades_executed}")
    print(f"Final USDT balance: {final_usdt_balance:.2f}")
    win_rate = (win_trades / closed_trades * 100) if closed_trades > 0 else 0.0
    print(f"Final BTC balance: {final_btc_balance}")
    print(f"Total realised PnL (USDT): {realised_pnl:.2f}")
    print(f"Final Account Equity (USDT): {total_equity:.2f} (Floating PnL: {unrealized_pnl:.2f})")
    print(f"Winrate: {win_rate:.2f}% ({win_trades}/{closed_trades})")

    print("\n=== Filters Diagnostics ===")
    print(f"Skipped due to missing price (NaN): {skipped_nan_price}")
    print(f"Skipped neutral news: {skipped_neutral}")
    print(f"Skipped low importance news (<2): {skipped_importance}")
    print(f"Skipped signals due to trend/SMA: {skipped_by_trend}")
    print(f"Skipped signals (already in position): {skipped_already_in_position}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backtest Binance news trader on historical price data")
    parser.add_argument("history_csv", type=str, help="Path to historical CSV or news history CSV")
    parser.add_argument("--price-csv", type=str, default=None, help="Optional candle price CSV to align news history timestamps with real prices")
    parser.add_argument("--start-usdt", type=float, default=100000.0, help="Starting USDT balance")
    args = parser.parse_args()
    run_backtest(args.history_csv, price_csv=args.price_csv, starting_usdt=args.start_usdt)
