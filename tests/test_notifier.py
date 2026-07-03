import importlib.util
import pathlib
import sys
import pytest
import httpx

# Load module directly from path since the directory name contains spaces or special characters
base = pathlib.Path(__file__).resolve().parents[1]
mod_path = base / "notifier.py"
spec = importlib.util.spec_from_file_location("notifier_mod", str(mod_path))
notifier_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = notifier_mod
spec.loader.exec_module(notifier_mod)
TelegramNotifier = notifier_mod.TelegramNotifier


@pytest.mark.asyncio
async def test_send_notification_inactive():
    tn = TelegramNotifier()
    tn.is_active = False
    result = await tn.send_notification("hello")
    assert result is False


@pytest.mark.asyncio
async def test_send_notification_success(monkeypatch):
    tn = TelegramNotifier()
    tn.BOT_TOKEN = "dummy"
    tn.CHAT_ID = "123"
    tn.is_active = True

    class DummyResponse:
        def __init__(self, status_code=200, text='OK'):
            self.status_code = status_code
            self._text = text
        @property
        def text(self):
            return self._text
        def raise_for_status(self):
            if not (200 <= self.status_code < 300):
                raise httpx.HTTPStatusError("status", request=None, response=self)

    class DummyClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, json):
            return DummyResponse()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    result = await tn.send_notification("hello")
    assert result is True
