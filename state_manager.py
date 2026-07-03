import json
import os
import sqlite3
from typing import Any, Dict, Optional


class StateStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(current_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(data_dir, "bot_state.sqlite3")
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_position(self, position: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO bot_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("current_position", json.dumps(position)),
            )
            conn.commit()

    def load_position(self) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM bot_state WHERE key = ?", ("current_position",)).fetchone()
            if not row:
                return None
            return json.loads(row[0])

    def clear_position(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM bot_state WHERE key = ?", ("current_position",))
            conn.commit()

    def save_bot_state(self, state: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO bot_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("bot_runtime_state", json.dumps(state)),
            )
            conn.commit()

    def load_bot_state(self) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM bot_state WHERE key = ?", ("bot_runtime_state",)).fetchone()
            if not row:
                return None
            return json.loads(row[0])
