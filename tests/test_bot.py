from live_trader import BinanceTestnetTrader


def test_trader_dry_run_init() -> None:
    """Test trader initialization in dry-run mode."""
    trader = BinanceTestnetTrader(dry_run=True)
    assert trader.dry_run is True
    assert trader.client is not None
