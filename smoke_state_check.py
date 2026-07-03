import os
import tempfile
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state_manager import StateStore

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = os.path.join(tmpdir, 'state.db')
    store = StateStore(db_path)
    payload = {'side': 'BUY', 'qty': 0.01, 'entry_price': 60000.0, 'entry_time': '2026-06-29T00:00:00', 'entry_reason': 'test'}
    store.save_position(payload)
    print(store.load_position())
