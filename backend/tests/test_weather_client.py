"""The Open-Meteo client is tested against a fake transport, so no real network calls."""

import asyncio

import httpx
import pytest

from app.errors import AppError
from app.services import weather_client

ARCHIVE_OK = {
    "latitude": 19.0,
    "longitude": 72.9,
    "elevation": 9.0,
    "timezone": "Asia/Kolkata",
    "daily": {"time": ["2020-01-01", "2020-01-02"], "temperature_2m_max": [25.9, None]},
}


@pytest.fixture
def fake_api(monkeypatch):
    """Route httpx calls to a list of canned responses, and skip the retry sleeps."""
    calls = []

    def install(*responses):
        queue = list(responses)

        def handler(request):
            calls.append(request)
            return queue.pop(0)

        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            weather_client.httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )
        return calls

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(weather_client.asyncio, "sleep", no_sleep)
    return install


def test_fetch_parses_series_and_turns_null_into_nan(fake_api):
    calls = fake_api(httpx.Response(200, json=ARCHIVE_OK))
    result = asyncio.run(weather_client.fetch_daily_tmax(19.07, 72.88, "2020-01-01", "2020-01-02"))
    assert calls[0].url.params["models"] == "era5"  # pinned dataset, see config.py
    assert result.grid_lat == 19.0
    assert result.tmax.iloc[0] == 25.9
    assert result.tmax.isna().iloc[1]


def test_retries_on_server_error_then_succeeds(fake_api):
    calls = fake_api(httpx.Response(503), httpx.Response(200, json=ARCHIVE_OK))
    asyncio.run(weather_client.fetch_daily_tmax(19.07, 72.88, "2020-01-01", "2020-01-02"))
    assert len(calls) == 2


def test_gives_up_after_retries_with_rate_limit_error(fake_api):
    calls = fake_api(httpx.Response(429), httpx.Response(429), httpx.Response(429))
    with pytest.raises(AppError) as exc:
        asyncio.run(weather_client.fetch_daily_tmax(19.07, 72.88, "2020-01-01", "2020-01-02"))
    assert len(calls) == 3  # 1 attempt + 2 retries
    assert exc.value.code == "upstream_rate_limited"


def test_client_error_is_not_retried(fake_api):
    calls = fake_api(httpx.Response(400, json={"error": True, "reason": "bad date"}))
    with pytest.raises(AppError) as exc:
        asyncio.run(weather_client.fetch_daily_tmax(19.07, 72.88, "2020-01-01", "2020-01-02"))
    assert len(calls) == 1
    assert "bad date" in exc.value.message


def test_geocode_returns_empty_list_when_no_results(fake_api):
    fake_api(httpx.Response(200, json={"generationtime_ms": 0.1}))
    assert asyncio.run(weather_client.geocode("zzzz")) == []
