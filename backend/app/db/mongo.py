"""MongoDB connection and the two caches.

raw_weather       one document per (point, date range) holding the daily Tmax series,
                  so repeated or overlapping requests don't hit Open-Meteo again.
analysis_results  the finished API response, keyed by a hash of all request params,
                  removed automatically by a TTL index after N days.

The cache "fails open": if MongoDB is down, every function logs a warning and acts
like a cache miss, so users still get a (slower) answer instead of an error.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

import pandas as pd
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.services.weather_client import WeatherSeries

logger = logging.getLogger(__name__)

RAW_WEATHER = "raw_weather"
ANALYSIS_RESULTS = "analysis_results"

_client: AsyncMongoClient | None = None


async def connect() -> None:
    """Create the client (called once at app startup) and make sure indexes exist."""
    global _client
    settings = get_settings()
    # Short server-selection timeout: if Atlas is unreachable we want to fall back to
    # "no cache" within seconds, not hang each request for the 30 s default.
    _client = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000, tz_aware=True)
    try:
        db = _client[settings.mongodb_db]
        await db[RAW_WEATHER].create_index([("lat", 1), ("lon", 1)])
        await db[ANALYSIS_RESULTS].create_index(
            "created_at", expireAfterSeconds=settings.analysis_cache_ttl_days * 24 * 3600
        )
    except PyMongoError as exc:
        logger.warning("MongoDB unavailable at startup, running without cache: %s", exc)


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def _db():
    return None if _client is None else _client[get_settings().mongodb_db]


async def ping() -> bool:
    db = _db()
    if db is None:
        return False
    try:
        await db.command("ping")
        return True
    except PyMongoError:
        return False


# ---------------------------------------------------------------- raw_weather


async def get_cached_weather(lat: float, lon: float, start_date: str, end_date: str) -> WeatherSeries | None:
    """Return a stored series that covers [start_date, end_date], sliced to that range.

    Any cached range that contains the requested one is reused, e.g. a stored
    1950-2020 series answers a 1990-2010 request. ISO date strings compare
    correctly as plain strings, so the range check is a simple $lte/$gte.
    """
    db = _db()
    if db is None:
        return None
    try:
        doc = await db[RAW_WEATHER].find_one(
            {"lat": lat, "lon": lon, "start_date": {"$lte": start_date}, "end_date": {"$gte": end_date}}
        )
    except PyMongoError as exc:
        logger.warning("raw_weather read failed: %s", exc)
        return None
    if doc is None:
        return None

    # Only the values are stored; the dates are rebuilt from start_date because the
    # series is stored complete (one value per day, null where missing).
    index = pd.date_range(doc["start_date"], periods=len(doc["tmax"]), freq="D")
    tmax = pd.Series(doc["tmax"], index=index, dtype="float64", name="tmax")  # None -> NaN
    return WeatherSeries(
        grid_lat=doc["grid_lat"],
        grid_lon=doc["grid_lon"],
        elevation=doc.get("elevation"),
        timezone=doc["timezone"],
        tmax=tmax[start_date:end_date],
    )


async def save_weather(lat: float, lon: float, start_date: str, end_date: str, weather: WeatherSeries) -> None:
    db = _db()
    if db is None:
        return
    complete = weather.tmax.reindex(pd.date_range(start_date, end_date, freq="D"))
    doc = {
        "lat": lat,
        "lon": lon,
        "start_date": start_date,
        "end_date": end_date,
        "tmax": [None if pd.isna(v) else float(v) for v in complete],
        "grid_lat": weather.grid_lat,
        "grid_lon": weather.grid_lon,
        "elevation": weather.elevation,
        "timezone": weather.timezone,
        "fetched_at": datetime.now(timezone.utc),
    }
    try:
        # A deterministic _id + upsert means two identical concurrent requests
        # can't create duplicate documents.
        await db[RAW_WEATHER].replace_one({"_id": f"{lat}:{lon}:{start_date}:{end_date}"}, doc, upsert=True)
    except PyMongoError as exc:
        logger.warning("raw_weather write failed: %s", exc)


# ---------------------------------------------------------------- analysis_results


def analysis_cache_key(params: dict) -> str:
    """Stable hash of the request params (sort_keys makes key order irrelevant)."""
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


async def get_cached_analysis(key: str) -> dict | None:
    db = _db()
    if db is None:
        return None
    try:
        doc = await db[ANALYSIS_RESULTS].find_one({"_id": key})
    except PyMongoError as exc:
        logger.warning("analysis_results read failed: %s", exc)
        return None
    return None if doc is None else doc["result"]


async def save_analysis(key: str, params: dict, result: dict) -> None:
    db = _db()
    if db is None:
        return
    doc = {"params": params, "result": result, "created_at": datetime.now(timezone.utc)}
    try:
        await db[ANALYSIS_RESULTS].replace_one({"_id": key}, doc, upsert=True)
    except PyMongoError as exc:
        logger.warning("analysis_results write failed: %s", exc)
