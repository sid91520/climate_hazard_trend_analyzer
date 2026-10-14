"""HTTP endpoints. Kept thin: validate input, call services, shape the response."""

import asyncio
import io
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Query, Request, Response

from app.config import get_settings
from app.db import mongo
from app.rate_limit import limiter
from app.schemas import (
    Event,
    GeocodeQuery,
    HeatwaveExportQuery,
    HeatwaveQuery,
    HeatwaveResponse,
    Place,
    YearlyMetrics,
)
from app.services import weather_client
from app.services.analysis import ANALYSIS_VERSION, fetch_range, run_heatwave_analysis

router = APIRouter(prefix="/api")
settings = get_settings()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness check for Render and for the frontend's "is the API awake?" ping."""
    # The app still works without the database (no caching), so "ok" either way.
    return {"status": "ok", "database": "ok" if await mongo.ping() else "unavailable"}


@router.get("/geocode", response_model=list[Place])
@limiter.limit(settings.rate_limit_geocode)
async def geocode(request: Request, query: Annotated[GeocodeQuery, Query()]):
    """City search for the autocomplete box."""
    return await weather_client.geocode(query.q)


@router.get("/hazards/heatwave", response_model=HeatwaveResponse)
@limiter.limit(settings.rate_limit_analysis)
async def heatwave(request: Request, query: Annotated[HeatwaveQuery, Query()]):
    return await get_heatwave_analysis(query)


@router.get("/hazards/heatwave/export.csv")
@limiter.limit(settings.rate_limit_analysis)
async def heatwave_csv(request: Request, query: Annotated[HeatwaveExportQuery, Query()]):
    """The same analysis as a CSV download: one row per year, or one row per event."""
    result = await get_heatwave_analysis(query)
    buffer = io.StringIO()
    # Columns come from the response models, so an empty events table still has a header.
    columns = list((YearlyMetrics if query.table == "yearly" else Event).model_fields)
    pd.DataFrame(result[query.table], columns=columns).to_csv(buffer, index=False)
    lat, lon = query.point()
    filename = f"heatwave_{query.table}_{lat}_{lon}_{query.start_year}-{query.end_year}.csv"
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def get_heatwave_analysis(query: HeatwaveQuery) -> dict:
    """The request flow. Step 1 (validation) already happened in HeatwaveQuery.

    2. Return a stored result if this exact request was answered recently.
    3. Otherwise load the daily series from raw_weather, or fetch it from Open-Meteo.
    4. Compute, store the result, return it.
    """
    lat, lon = query.point()
    # Everything that changes the answer goes into the key, including the code version.
    # Only HeatwaveQuery's fields, so the CSV export's extra `table` param shares the cache.
    analysis_params = query.model_dump(include=set(HeatwaveQuery.model_fields))
    params = {"hazard": "heatwave", "version": ANALYSIS_VERSION, **analysis_params, "lat": lat, "lon": lon}
    cache_key = mongo.analysis_cache_key(params)

    cached = await mongo.get_cached_analysis(cache_key)
    if cached is not None:
        cached["metadata"]["cached"] = True
        return cached

    start_date, end_date = fetch_range(query)
    weather = await mongo.get_cached_weather(lat, lon, start_date, end_date)
    if weather is None:
        weather = await weather_client.fetch_daily_tmax(lat, lon, start_date, end_date)
        await mongo.save_weather(lat, lon, start_date, end_date, weather)

    # The pandas work is CPU-bound; run it in a thread so it doesn't block the
    # event loop (and with it, every other request) while it computes.
    result = await asyncio.to_thread(run_heatwave_analysis, weather, query)
    await mongo.save_analysis(cache_key, params, result)
    return result
