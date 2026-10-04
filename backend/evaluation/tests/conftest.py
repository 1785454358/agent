"""All isolated scorer tests block HTTP before reaching a transport."""

import httpx
import pytest


@pytest.fixture(autouse=True)
def block_external_http(monkeypatch):
    def blocked_sync(*args, **kwargs):
        raise RuntimeError("offline_scorer_network_blocked")

    async def blocked_async(*args, **kwargs):
        raise RuntimeError("offline_scorer_network_blocked")

    monkeypatch.setattr(httpx.Client, "send", blocked_sync)
    monkeypatch.setattr(httpx.AsyncClient, "send", blocked_async)
