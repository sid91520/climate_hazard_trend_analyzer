"""Endpoint tests. Open-Meteo and MongoDB are replaced by in-memory fakes."""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.config import Settings
from app.main import app
from app.rate_limit import limiter
from app.schemas import last_full_year
from app.services.weather_client import WeatherSeries

client = TestClient(app)  # not used as a context manager, so no real DB connection
END = last_full_year()
VALID = {"lat": 19.07, "lon": 72.88, "start_year": END - 29, "end_year": END}


@pytest.fixture(autouse=True)
def reset_rate_limits():
    limiter.reset()


@pytest.fixture
def fakes(monkeypatch):
    """Fake weather API + in-memory caches. Returns counters so tests can assert on them."""
    calls = {"fetch": 0}
    analysis_cache, weather_cache = {}, {}

    async def fake_fetch(lat, lon, start_date, end_date):
        calls["fetch"] += 1
        dates = pd.date_range(start_date, end_date, freq="D")
        rng = np.random.default_rng(0)
        seasonal = 30 + 5 * np.sin(2 * np.pi * dates.dayofyear / 365)
        warming = (dates.year - dates.year[0]) * 0.05  # so there is a trend to find
        tmax = pd.Series(seasonal + warming + rng.normal(0, 1.5, len(dates)), index=dates)
        return WeatherSeries(grid_lat=lat, grid_lon=lon, elevation=10.0, timezone="UTC", tmax=tmax)

    async def get_weather(lat, lon, start, end):
        return weather_cache.get((lat, lon, start, end))

    async def save_weather(lat, lon, start, end, weather):
        weather_cache[(lat, lon, start, end)] = weather

    async def get_analysis(key):
        return analysis_cache.get(key)

    async def save_analysis(key, params, result):
        analysis_cache[key] = result

    monkeypatch.setattr(routes.weather_client, "fetch_daily_tmax", fake_fetch)
    monkeypatch.setattr(routes.mongo, "get_cached_weather", get_weather)
    monkeypatch.setattr(routes.mongo, "save_weather", save_weather)
    monkeypatch.setattr(routes.mongo, "get_cached_analysis", get_analysis)
    monkeypatch.setattr(routes.mongo, "save_analysis", save_analysis)
    return calls


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cors_origins_are_split_and_trimmed():
    settings = Settings(cors_origins="https://a.example, http://localhost:3000 ,")
    assert settings.cors_origin_list == ["https://a.example", "http://localhost:3000"]


def test_heatwave_analysis_returns_full_response(fakes):
    response = client.get("/api/hazards/heatwave", params=VALID)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"metadata", "yearly", "events", "trends", "insights"}
    assert len(body["yearly"]) == 30
    assert body["metadata"]["threshold"]["method"] == "doy"
    assert body["metadata"]["cached"] is False
    assert body["trends"]["heatwave_days"]["significant"] is True
    assert body["insights"]
    assert {"missing_pct", "filled_pct"} <= set(body["yearly"][0])  # data quality per year


def test_second_identical_request_is_served_from_cache(fakes):
    client.get("/api/hazards/heatwave", params=VALID)
    response = client.get("/api/hazards/heatwave", params=VALID)
    assert response.json()["metadata"]["cached"] is True
    assert fakes["fetch"] == 1


def test_different_params_reuse_cached_weather(fakes):
    client.get("/api/hazards/heatwave", params=VALID)
    response = client.get("/api/hazards/heatwave", params={**VALID, "percentile": 90})
    assert response.json()["metadata"]["cached"] is False  # new analysis...
    assert fakes["fetch"] == 1  # ...but no new download


def test_bounding_box_uses_its_centre(fakes):
    box = {"min_lat": 19.0, "max_lat": 20.0, "min_lon": 72.0, "max_lon": 73.0, "start_year": END - 19, "end_year": END}
    location = client.get("/api/hazards/heatwave", params=box).json()["metadata"]["location"]
    assert (location["lat"], location["lon"]) == (19.5, 72.5)
    assert location["bbox"] == [19.0, 20.0, 72.0, 73.0]


def test_csv_export(fakes):
    response = client.get("/api/hazards/heatwave/export.csv", params=VALID)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[0].startswith("year,events,heatwave_days")
    events_csv = client.get("/api/hazards/heatwave/export.csv", params={**VALID, "table": "events"})
    assert events_csv.text.startswith("start,end,duration")
    assert fakes["fetch"] == 1  # all three requests share one analysis


@pytest.mark.parametrize(
    "override, expected_text",
    [
        ({"lat": 100}, "lat"),
        ({"lon": -181}, "lon"),
        ({"start_year": END, "end_year": END - 20}, "start_year must be before end_year"),
        ({"start_year": END - 5}, "10 to 85 years"),
        ({"start_year": 1940, "end_year": 2030}, "or earlier"),
        ({"start_year": 1939}, "start_year"),
        ({"percentile": 79}, "percentile"),
        ({"percentile": 99.5}, "percentile"),
        ({"min_duration": 1}, "min_duration"),
        ({"min_duration": 11}, "min_duration"),
        ({"method": "magic"}, "method"),
        ({"lon": None}, "both lat and lon"),
        ({"min_lat": 1, "max_lat": 2, "min_lon": 1, "max_lon": 2}, "not both"),
        ({"baseline_start": 1990}, "baseline_start and baseline_end"),
        ({"baseline_start": 1990, "baseline_end": 1995}, "at least 10 years"),
    ],
)
def test_invalid_heatwave_params_are_rejected(fakes, override, expected_text):
    params = {k: v for k, v in {**VALID, **override}.items() if v is not None}
    response = client.get("/api/hazards/heatwave", params=params)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert expected_text in error["message"]
    assert fakes["fetch"] == 0  # nothing was fetched for a bad request


def test_bounding_box_too_large_is_rejected():
    box = {"min_lat": 10, "max_lat": 13, "min_lon": 70, "max_lon": 71, "start_year": END - 19, "end_year": END}
    response = client.get("/api/hazards/heatwave", params=box)
    assert response.status_code == 422
    assert "at most 2.0°" in response.json()["error"]["message"]


@pytest.mark.parametrize("q", ["a", "x" * 101, "<script>", "Mumbai; DROP", "   "])
def test_bad_geocode_queries_are_rejected(q):
    response = client.get("/api/geocode", params={"q": q})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_geocode_accepts_non_english_names(monkeypatch):
    async def fake_geocode(query):
        return [{"name": query, "country": "Brazil", "admin1": None, "lat": -23.5, "lon": -46.6}]

    monkeypatch.setattr(routes.weather_client, "geocode", fake_geocode)
    response = client.get("/api/geocode", params={"q": "  São   Paulo "})
    assert response.status_code == 200
    assert response.json()[0]["name"] == "São Paulo"  # trimmed and collapsed


def test_unknown_route_uses_standard_error_shape():
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_rate_limit_returns_429(monkeypatch):
    async def fake_geocode(query):
        return []

    monkeypatch.setattr(routes.weather_client, "geocode", fake_geocode)
    limit = int(routes.settings.rate_limit_geocode.split("/")[0])
    statuses = [client.get("/api/geocode", params={"q": "Pune"}).status_code for _ in range(limit + 1)]
    assert statuses[:limit] == [200] * limit
    assert statuses[-1] == 429
    assert client.get("/api/geocode", params={"q": "Pune"}).json()["error"]["code"] == "rate_limited"
