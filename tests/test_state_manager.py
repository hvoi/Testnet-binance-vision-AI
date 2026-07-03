import os
import tempfile
import unittest

from state_manager import StateStore


class StateStoreTests(unittest.TestCase):
    def test_save_and_load_position_round_trip(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "state.db")
            store = StateStore(db_path)

            position = {
                "side": "BUY",
                "qty": 0.01,
                "entry_price": 60000.0,
                "entry_time": "2026-06-29T00:00:00",
                "entry_reason": "test",
            }

            store.save_position(position)
            self.assertEqual(store.load_position(), position)

            store.clear_position()
            self.assertIsNone(store.load_position())

    def test_save_and_load_bot_state_round_trip(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "state.db")
            store = StateStore(db_path)

            runtime_state = {
                "positive_streak": 3,
                "positive_start_time": 1234567890.5,
                "last_trade_time": 1234567800.0,
                "price_history": [59000.0, 59500.0, 60000.0],
            }

            store.save_bot_state(runtime_state)
            loaded = store.load_bot_state()
            self.assertEqual(loaded, runtime_state)

    def test_load_bot_state_returns_none_when_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "state.db")
            store = StateStore(db_path)
            self.assertIsNone(store.load_bot_state())

    def test_save_bot_state_overwrites_previous(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "state.db")
            store = StateStore(db_path)

            first = {"positive_streak": 1, "positive_start_time": None, "last_trade_time": None, "price_history": []}
            store.save_bot_state(first)

            second = {"positive_streak": 5, "positive_start_time": 9999.0, "last_trade_time": 8888.0, "price_history": [1.0, 2.0]}
            store.save_bot_state(second)

            loaded = store.load_bot_state()
            self.assertEqual(loaded, second)

    def test_bot_state_and_position_are_independent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "state.db")
            store = StateStore(db_path)

            position = {"side": "BUY", "qty": 0.01, "entry_price": 60000.0, "entry_time": "t", "entry_reason": "r"}
            runtime = {"positive_streak": 2, "positive_start_time": 111.0, "last_trade_time": 222.0, "price_history": [60000.0]}

            store.save_position(position)
            store.save_bot_state(runtime)

            store.clear_position()
            self.assertIsNone(store.load_position())
            self.assertEqual(store.load_bot_state(), runtime)


if __name__ == "__main__":
    unittest.main()
