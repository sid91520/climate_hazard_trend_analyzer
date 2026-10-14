"""Calls to the Open-Meteo Historical Archive and Geocoding APIs.

Both APIs are free and need no key. Network problems and upstream errors are turned
into AppError so the route handlers never see raw httpx exceptions.
"""

import asyncio
import logging
from dataclasses import dataclass

import httpx
import pandas as pd

from app.config import get_settings
from app.errors import AppError

logger = logging.getLogger(__name__)

# Status codes worth retrying: rate-limited, or a temporary server-side problem.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class WeatherSeries:
    """Daily maximum temperature for one ERA5 grid cell."""

    grid_lat: float  # Open-Meteo snaps the request to the nearest grid cell
    grid_lon: float
    elevation: float | None
    timezone: str
    tmax: pd.Series  # float °C, indexed by a daily DatetimeIndex; NaN where missing


async def _get_json(url: str, params: dict) -> dict:
    """GET a URL with a timeout and retries (exponential backoff: 1 s, 2 s, ...)."""
    settings = get_settings()
    attempts = settings.http_max_retries + 1
    last_problem = "unknown error"

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        for attempt in range(attempts):
            try:
                response = await client.get(url, params=params)
            except httpx.TimeoutException:
                last_problem = "timed out"
            except httpx.TransportError as exc:
                last_problem = f"network error ({type(exc).__name__})"
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code not in RETRYABLE_STATUS:
                    # A 4xx other than 429 means our request is wrong; retrying won't help.
                    reason = _error_reason(response)
                    raise AppError(400, "upstream_bad_request", f"Weather service rejected the request: {reason}")
                last_problem = f"HTTP {response.status_code}"

            if attempt < attempts - 1:
                delay = 2**attempt
                logger.warning("Open-Meteo %s (attempt %d/%d); retrying in %ss", last_problem, attempt + 1, attempts, delay)
                await asyncio.sleep(delay)

    if last_problem == "HTTP 429":
        raise AppError(503, "upstream_rate_limited", "The weather data service is busy. Please try again in a minute.")
    raise AppError(502, "upstream_unavailable", f"Could not reach the weather data service ({last_problem}).")


def _error_reason(response: httpx.Response) -> str:
    try:
        return str(response.json().get("reason", response.text))
    except ValueError:
        return response.text[:200]


async def fetch_daily_tmax(lat: float, lon: float, start_date: str, end_date: str) -> WeatherSeries:
    """Fetch daily Tmax (°C) for one point and date range ("YYYY-MM-DD" strings)."""
    settings = get_settings()
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max",
        "models": settings.open_meteo_model,  # one consistent dataset for the whole period
        "timezone": "auto",  # so each "day" is the location's local calendar day
    }
    data = await _get_json(settings.open_meteo_archive_url, params)

    daily = data.get("daily") or {}
    if "time" not in daily or "temperature_2m_max" not in daily:
        raise AppError(502, "upstream_bad_response", "Weather service returned no daily temperature data.")

    tmax = pd.Series(
        pd.to_numeric(daily["temperature_2m_max"], errors="coerce"),  # null -> NaN
        index=pd.to_datetime(daily["time"]),
        name="tmax",
        dtype="float64",
    )
    return WeatherSeries(
        grid_lat=data.get("latitude", lat),
        grid_lon=data.get("longitude", lon),
        elevation=data.get("elevation"),
        timezone=data.get("timezone", "UTC"),
        tmax=tmax,
    )


async def geocode(query: str, count: int = 8) -> list[dict]:
    """Search for places by name. Returns [] when nothing matches."""
    settings = get_settings()
    data = await _get_json(
        settings.open_meteo_geocoding_url,
        {"name": query, "count": count, "language": "en", "format": "json"},
    )
    return [
        {
            "name": place.get("name", ""),
            "country": place.get("country"),
            "admin1": place.get("admin1"),
            "lat": place["latitude"],
            "lon": place["longitude"],
        }
        for place in data.get("results", [])  # the key is absent when there are no matches
        if "latitude" in place and "longitude" in place
    ]
