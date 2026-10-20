import httpx
import pytest

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.business import PlatformAccount
from app.publishers.bluesky import BlueskyPublisher


@pytest.mark.asyncio
async def test_bluesky_uses_explicit_outbound_proxy_without_redirecting(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            captured["url"] = url
            return httpx.Response(200, json={}, request=httpx.Request(method, url))

    monkeypatch.setattr(settings, "outbound_http_proxy", " http://127.0.0.1:7892 ")
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    with SessionLocal() as db:
        publisher = BlueskyPublisher(db, PlatformAccount(platform="BLUESKY", user_id=1))
        response = await publisher._raw("GET", "com.atproto.server.getSession")
    assert response.status_code == 200
    assert captured["proxy"] == "http://127.0.0.1:7892"
    assert captured["follow_redirects"] is False
    assert captured["url"].endswith("/xrpc/com.atproto.server.getSession")
