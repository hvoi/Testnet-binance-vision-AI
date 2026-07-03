import json
import logging
import os
import httpx

logger = logging.getLogger("TelegramNotifier")


class TelegramNotifier:
    def __init__(self):
        config = self._read_config()
        bot = config.get('TELEGRAM', {}).get('BOT_TOKEN')
        chat = config.get('TELEGRAM', {}).get('CHAT_ID')

        self.BOT_TOKEN = str(bot) if bot is not None else None
        self.CHAT_ID = str(chat) if chat is not None else None

        if not self.BOT_TOKEN or not self.CHAT_ID:
            logger.warning("Missing TELEGRAM keys; notifier is inactive.")
            self.is_active = False
        else:
            self.is_active = True

    def _read_config(self) -> dict:
        """Read configuration file safely."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, "config.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8-sig") as file:
                    return json.load(file)
        except Exception as e:
            logger.error(f"Error reading config.json: {e}")
        return {}

    async def send_notification(self, text: str) -> bool:
        """Send message to Telegram."""
        if not self.is_active:
            return False

        url = f"https://api.telegram.org/bot{self.BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": self.CHAT_ID,
            "text": text
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            resp = e.response
            try:
                body = resp.text
            except Exception:
                body = '<unable to read body>'
            logger.error(f"Telegram API error {resp.status_code}: {body}")
        except httpx.RequestError as e:
            logger.error(f"Network error when sending to Telegram: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        return False
