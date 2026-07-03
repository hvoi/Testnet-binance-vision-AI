import asyncio
import pytest
from live_trader import BinanceTestnetTrader, run_with_retry


def test_quantize_qty() -> None:
    """Test quantity quantization."""
    trader = BinanceTestnetTrader(dry_run=True)
    assert trader.quantize_qty(0.12345, "0.01") == 0.12
    assert trader.quantize_qty(0.0056, "0.001") == 0.005
    assert trader.quantize_qty(1.0, "-0.1") is None


@pytest.mark.asyncio
async def test_run_with_retry_success() -> None:
    """Test successful execution with retries."""
    call_count = 0

    def fail_once_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Temporary failure")
        return "success"

    result = await run_with_retry(fail_once_then_succeed, retries=3, base_delay=0.01)
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_run_with_retry_exhausted() -> None:
    """Test retry limit exhaustion."""
    def always_fail():
        raise RuntimeError("Persistent error")

    with pytest.raises(RuntimeError, match="Persistent error"):
        await run_with_retry(always_fail, retries=2, base_delay=0.01)
