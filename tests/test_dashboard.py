import importlib.util
from pathlib import Path


module_path = Path(__file__).resolve().parents[1] / "dashboard.py"
spec = importlib.util.spec_from_file_location("dashboard_module", module_path)
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


def test_load_data_nonexistent():
    df = dashboard.load_data("nonexistent_file.csv")
    assert df.empty

