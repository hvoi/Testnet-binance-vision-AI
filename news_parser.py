import asyncio
import json
import os
import xml.etree.ElementTree as ET
import httpx
from datetime import datetime
import logging

logger = logging.getLogger("NewsParser")


class NewsParser:
    def __init__(self):
        self.news_buffer = []
        self.rss_urls = [
            "https://cointelegraph.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://cryptopanic.com/news/rss/"
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.seen_titles = set()

    async def init(self) -> list:
        """Initialize parser and load news history."""
        print("🚀 Autonomous NewsParser started! Crypto streams are active.")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        history_path = os.path.join(current_dir, "data", "news_history.csv")
        if os.path.exists(history_path):
            try:
                import csv
                with open(history_path, mode="r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    next(reader, None)
                    for row in reader:
                        if len(row) > 1:
                            self.seen_titles.add(row[1].strip())
            except Exception as e:
                logger.error(f"Error reading news history: {e}")
        already_read_history = len(self.seen_titles)
        await self.fetch_updates()
        initial_news = list(self.news_buffer)
        total_rss = len(self.seen_titles)
        self.news_buffer.clear()
        print(
            f"📊 Initial market snapshot captured.\n"
            f"   - Loaded from database history: {already_read_history} news items\n"
            f"   - Found new in RSS feeds: {total_rss - already_read_history} news items\n"
            f"   - Marked as read at startup: {total_rss} news items"
        )
        return initial_news

    async def fetch_updates(self):
        """Scan RSS feeds for new publications."""
        async with httpx.AsyncClient(timeout=10.0, headers=self.headers, follow_redirects=True) as client:
            for url in self.rss_urls:
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        root = ET.fromstring(response.content)
                        for item in root.findall(".//item"):
                            title_elem = item.find("title")
                            if title_elem is not None and title_elem.text:
                                title_text = title_elem.text.strip()
                                
                                if title_text not in self.seen_titles:
                                    self.seen_titles.add(title_text)
                                    self.news_buffer.append({
                                        "content": title_text,
                                        "timestamp": datetime.now().isoformat()
                                    })
                except Exception:
                    continue

    async def get_news(self) -> list:
        """Fetch latest updates from RSS feeds."""
        await self.fetch_updates()
        
        if not self.news_buffer:
            return []
        
        extracted_items = list(self.news_buffer)
        self.news_buffer.clear()
        return extracted_items

    async def log_news_to_history(self, selected_news: dict):
        """Log news to history (compatibility stub)."""
        pass