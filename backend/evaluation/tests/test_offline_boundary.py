import asyncio

import httpx
import pytest


def test_all_scorer_tests_block_real_sync_http_dispatch():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, request=request)
    )
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(RuntimeError, match="offline_scorer_network_blocked"),
    ):
        client.get("https://example.org")


def test_all_scorer_tests_block_real_async_http_dispatch():
    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, request=request)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(RuntimeError, match="offline_scorer_network_blocked"):
                await client.get("https://example.org")

    asyncio.run(run())
