import pytest
import httpx
from ai_service import evaluate_sentiment, load_bot_config


def test_load_bot_config() -> None:
    """Verify correct loading of bot configuration parameters."""
    base_url, model_name = load_bot_config()
    assert base_url.startswith("http")
    assert model_name != ""


@pytest.mark.asyncio
async def test_evaluate_sentiment_positive(monkeypatch) -> None:
    """Test successful identification of positive news sentiment."""
    class MockResponse:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "EXCLUSIVE_POSITIVE"
                        }
                    }
                ]
            }

    async def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await evaluate_sentiment("Test positive news")
    assert result == "EXCLUSIVE_POSITIVE"
