"""Pydantic models: what the API accepts (validated) and what it returns (documented).

FastAPI turns a failed validation into a 422 response; main.py reshapes that into
our standard {"error": {...}} body.
"""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.heatwave import DEFAULT_MIN_DURATION, DEFAULT_PERCENTILE, default_baseline

FIRST_DATA_YEAR = 1940  # ERA5 (and so Open-Meteo's archive) starts in 1940
MIN_RANGE_YEARS = 10  # fewer years than this can't support a trend
MAX_RANGE_YEARS = 85
MIN_BASELINE_YEARS = 10  # enough days for a stable percentile
MAX_BOX_DEGREES = 2.0


def last_full_year() -> int:
    """The archive lags real time by days, so only finished years are offered."""
    return date.today().year - 1


# ---------------------------------------------------------------- requests


class GeocodeQuery(BaseModel):
    q: str = Field(min_length=2, max_length=100)

    @field_validator("q")
    @classmethod
    def only_place_name_characters(cls, value: str) -> str:
        value = " ".join(value.split())  # trim and collapse whitespace
        # Letters in any language (\w is Unicode-aware), digits, and the punctuation
        # place names use. Anything else is rejected rather than forwarded upstream.
        if len(value) < 2 or not re.fullmatch(r"[\w\s\-'.,()]+", value):
            raise ValueError("must be a place name (letters, digits, spaces and - ' . , ( ) only)")
        return value


class HeatwaveQuery(BaseModel):
    """Query parameters for the heatwave analysis.

    The location is either a point (lat + lon) or a bounding box (all four min/max
    values). For a box we analyse its centre point; see the README for why.
    """

    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    min_lat: float | None = Field(None, ge=-90, le=90)
    max_lat: float | None = Field(None, ge=-90, le=90)
    min_lon: float | None = Field(None, ge=-180, le=180)
    max_lon: float | None = Field(None, ge=-180, le=180)

    start_year: int = Field(ge=FIRST_DATA_YEAR)
    end_year: int = Field(ge=FIRST_DATA_YEAR)

    percentile: float = Field(DEFAULT_PERCENTILE, ge=80, le=99)
    min_duration: int = Field(DEFAULT_MIN_DURATION, ge=2, le=10)
    method: Literal["doy", "annual"] = "doy"

    baseline_start: int | None = Field(None, ge=FIRST_DATA_YEAR)
    baseline_end: int | None = Field(None, ge=FIRST_DATA_YEAR)

    @model_validator(mode="after")
    def check_location(self):
        box = [self.min_lat, self.max_lat, self.min_lon, self.max_lon]
        has_point = self.lat is not None or self.lon is not None
        has_box = any(v is not None for v in box)

        if has_point and has_box:
            raise ValueError("give either lat/lon or a bounding box, not both")
        if has_point and (self.lat is None or self.lon is None):
            raise ValueError("both lat and lon are required")
        if has_box:
            if any(v is None for v in box):
                raise ValueError("a bounding box needs min_lat, max_lat, min_lon and max_lon")
            if self.min_lat >= self.max_lat or self.min_lon >= self.max_lon:
                raise ValueError("bounding box min values must be smaller than max values")
            if self.max_lat - self.min_lat > MAX_BOX_DEGREES or self.max_lon - self.min_lon > MAX_BOX_DEGREES:
                raise ValueError(f"bounding box must be at most {MAX_BOX_DEGREES}° × {MAX_BOX_DEGREES}°")
        if not has_point and not has_box:
            raise ValueError("a location is required: lat/lon or a bounding box")
        return self

    @model_validator(mode="after")
    def check_years(self):
        last = last_full_year()
        if self.end_year > last or (self.baseline_end or 0) > last:
            raise ValueError(f"years must be {last} or earlier (the last full year of data)")
        if self.start_year >= self.end_year:
            raise ValueError("start_year must be before end_year")
        n_years = self.end_year - self.start_year + 1
        if not MIN_RANGE_YEARS <= n_years <= MAX_RANGE_YEARS:
            raise ValueError(f"the year range must cover {MIN_RANGE_YEARS} to {MAX_RANGE_YEARS} years")

        if (self.baseline_start is None) != (self.baseline_end is None):
            raise ValueError("give both baseline_start and baseline_end, or neither")
        if self.baseline_start is not None and self.baseline_end - self.baseline_start + 1 < MIN_BASELINE_YEARS:
            raise ValueError(f"the baseline must cover at least {MIN_BASELINE_YEARS} years")
        return self

    def point(self) -> tuple[float, float]:
        """The point to analyse, rounded to 2 decimals (~1 km).

        ERA5 cells are ~25 km wide, so finer precision changes nothing except the
        cache key. Rounding means nearby clicks share cached data.
        """
        if self.lat is not None:
            lat, lon = self.lat, self.lon
        else:
            lat = (self.min_lat + self.max_lat) / 2
            lon = (self.min_lon + self.max_lon) / 2
        return round(lat, 2), round(lon, 2)

    def baseline(self) -> tuple[int, int]:
        if self.baseline_start is not None:
            return self.baseline_start, self.baseline_end
        return default_baseline(self.start_year, self.end_year)


class HeatwaveExportQuery(HeatwaveQuery):
    """Same params plus which table to download. A subclass, because FastAPI only
    expands a model into query params when it is the endpoint's only query input."""

    table: Literal["yearly", "events"] = "yearly"


# ---------------------------------------------------------------- responses


class Place(BaseModel):
    name: str
    country: str | None = None
    admin1: str | None = None  # state / province
    lat: float
    lon: float


class Location(BaseModel):
    lat: float
    lon: float
    grid_lat: float  # centre of the ERA5 grid cell actually used
    grid_lon: float
    elevation: float | None
    timezone: str
    bbox: list[float] | None = None  # [min_lat, max_lat, min_lon, max_lon] if a box was requested


class Threshold(BaseModel):
    method: Literal["doy", "annual"]
    percentile: float
    baseline_start: int
    baseline_end: int
    min_c: float  # for "annual" all three are the same number
    mean_c: float
    max_c: float


class DataQuality(BaseModel):
    missing_raw_pct: float
    filled_pct: float
    missing_after_cleaning_pct: float
    impossible_values: int
    low_quality_years: list[int]  # years with too many missing days to trust fully


class Metadata(BaseModel):
    hazard: Literal["heatwave"]
    location: Location
    start_year: int
    end_year: int
    min_duration: int
    threshold: Threshold
    data_quality: DataQuality
    source: str
    analysis_version: str
    generated_at: str
    cached: bool


class YearlyMetrics(BaseModel):
    year: int
    events: int
    heatwave_days: int
    longest_event: int
    mean_intensity: float | None  # None in years without a heatwave
    max_tmax: float | None
    missing_pct: float  # % of days still missing after cleaning
    filled_pct: float  # % of days that were missing/invalid and got interpolated
    events_rolling: float | None  # 5-year centred rolling means
    heatwave_days_rolling: float | None
    longest_event_rolling: float | None
    mean_intensity_rolling: float | None
    max_tmax_rolling: float | None


class Event(BaseModel):
    start: str
    end: str
    duration: int
    peak_temp: float
    mean_excess: float


class LinearTrend(BaseModel):
    slope_per_decade: float
    intercept: float
    p_value: float
    r_squared: float


class MannKendall(BaseModel):
    trend: str
    p_value: float
    tau: float
    sens_slope_per_decade: float


class MetricTrend(BaseModel):
    linear: LinearTrend | None
    mann_kendall: MannKendall | None
    significant: bool


class HeatwaveResponse(BaseModel):
    metadata: Metadata
    yearly: list[YearlyMetrics]
    events: list[Event]
    trends: dict[str, MetricTrend]
    insights: list[str]
