import json
import os
import threading
import requests


def load_telegram_config(config_path="config.json"):
    if not os.path.exists(config_path) and os.path.exists(os.path.join("..", config_path)):
        config_path = os.path.join("..", config_path)

    if not os.path.exists(config_path):
        print(f"⚠️ [DIAGNOSTIC] File {config_path} NOT FOUND in current directory!")
        return {}
        
    try:
        with open(config_path, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
            tele_block = config.get("TELEGRAM", {})
            return tele_block
    except Exception as e:
        print(f"⚠️ [TELEGRAM] Config read error: {e}")
    return {}


def _send_request_sync(message: str):
    config = load_telegram_config()
    
    if not config:
        print("⚠️ [DIAGNOSTIC] 'TELEGRAM' section is empty or missing in config.json!")
        return

    token = config.get("BOT_TOKEN")
    chat_id = config.get("CHAT_ID")

    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN" or "PLACEHOLDER" in str(token):
        print(f"⚠️ [DIAGNOSTIC] Invalid token in config.json! Current value: '{token}'")
        return
    if not chat_id or chat_id == "YOUR_CHAT_ID" or "PLACEHOLDER" in str(chat_id):
        print(f"⚠️ [DIAGNOSTIC] Invalid Chat ID in config.json! Current value: '{chat_id}'")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            print("🚀 [SUCCESS] Message successfully sent to Telegram!")
        else:
            print(f"⚠️ [TELEGRAM] Telegram API Error: {response.text}")
    except Exception as e:
        print(f"⚠️ [TELEGRAM] Network error: {e}")


def send_telegram_notification(message: str):
    threading.Thread(target=_send_request_sync, args=(message,), daemon=True).start()