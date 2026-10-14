"""Glue: turns a cleaned weather series + query into the full API response.

This is the only place that knows the order of the steps. The science lives in
cleaning.py, heatwave.py and trends.py; this file just calls them and shapes JSON.
"""

import math
from datetime import datetime, timezone

import pandas as pd

from app.schemas import HeatwaveQuery
from app.services import heatwave, trends
from app.services.cleaning import clean_tmax
from app.services.weather_client import WeatherSeries

# Bump this whenever the analysis logic changes. It is part of the result cache key,
# so old cached results computed with the previous logic are not served.
ANALYSIS_VERSION = "1"

METRICS = ["events", "heatwave_days", "longest_event", "mean_intensity", "max_tmax"]
COUNT_METRICS = ["events", "heatwave_days", "longest_event"]  # always whole numbers
# Metrics that get an insight sentence (max_tmax is shown but isn't a heatwave measure).
INSIGHT_METRICS = ["heatwave_days", "events", "longest_event", "mean_intensity"]

# A year missing more than this share of days (after filling short gaps) could have
# heatwaves hidden in the gaps, so it is flagged to the user.
LOW_QUALITY_MISSING_PCT = 10.0

SOURCE = "ECMWF ERA5 reanalysis via the Open-Meteo Historical Weather API (daily temperature_2m_max)"


def fetch_range(query: HeatwaveQuery) -> tuple[str, str]:
    """Date range to download: the analysis years plus the baseline, if it lies outside."""
    baseline_start, baseline_end = query.baseline()
    first = min(query.start_year, baseline_start)
    last = max(query.end_year, baseline_end)
    return f"{first}-01-01", f"{last}-12-31"


def number(value, digits: int = 2) -> float | None:
    """Round for JSON, and turn NaN (which JSON can't represent) into null."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), digits)


def run_heatwave_analysis(weather: WeatherSeries, query: HeatwaveQuery) -> dict:
    """Compute the complete heatwave response for one location (CPU only, no I/O)."""
    fetch_start, fetch_end = fetch_range(query)
    cleaned = clean_tmax(weather.tmax, fetch_start, fetch_end)

    baseline_start, baseline_end = query.baseline()
    baseline_tmax = cleaned.tmax[str(baseline_start) : str(baseline_end)]
    tmax = cleaned.tmax[str(query.start_year) : str(query.end_year)]
    years = list(range(query.start_year, query.end_year + 1))

    threshold = heatwave.daily_threshold(tmax, baseline_tmax, query.percentile, query.method)
    events = heatwave.detect_events(tmax, threshold, query.min_duration)
    yearly = heatwave.yearly_metrics(tmax, events, years)

    year_series = pd.Series(years, index=years)
    metric_trends = {m: trends.trend_summary(year_series, yearly[m]) for m in METRICS}
    rolling = {m: trends.rolling_mean(yearly[m]) for m in METRICS}

    quality = cleaned.quality.loc[years]
    insights = build_insights(yearly, metric_trends, events, quality)

    return {
        "metadata": {
            "hazard": "heatwave",
            "location": location_metadata(weather, query),
            "start_year": query.start_year,
            "end_year": query.end_year,
            "min_duration": query.min_duration,
            "threshold": {
                "method": query.method,
                "percentile": query.percentile,
                "baseline_start": baseline_start,
                "baseline_end": baseline_end,
                "min_c": number(threshold.min()),
                "mean_c": number(threshold.mean()),
                "max_c": number(threshold.max()),
            },
            "data_quality": quality_summary(quality),
            "source": SOURCE,
            "analysis_version": ANALYSIS_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cached": False,
        },
        "yearly": [
            {
                "year": year,
                **{m: int(yearly.at[year, m]) for m in COUNT_METRICS},
                "mean_intensity": number(yearly.at[year, "mean_intensity"]),
                "max_tmax": number(yearly.at[year, "max_tmax"]),
                "missing_pct": number(quality.at[year, "missing_after_cleaning_pct"], 1),
                "filled_pct": number(quality.at[year, "filled_pct"], 1),
                **{f"{m}_rolling": number(rolling[m].at[year]) for m in METRICS},
            }
            for year in years
        ],
        "events": [
            {
                "start": row.start.date().isoformat(),
                "end": row.end.date().isoformat(),
                "duration": int(row.duration),
                "peak_temp": number(row.peak_temp),
                "mean_excess": number(row.mean_excess),
            }
            for row in events.itertuples()
        ],
        "trends": {m: rounded_trend(t) for m, t in metric_trends.items()},
        "insights": insights,
    }


def location_metadata(weather: WeatherSeries, query: HeatwaveQuery) -> dict:
    lat, lon = query.point()
    bbox = [query.min_lat, query.max_lat, query.min_lon, query.max_lon] if query.min_lat is not None else None
    return {
        "lat": lat,
        "lon": lon,
        "grid_lat": number(weather.grid_lat, 4),
        "grid_lon": number(weather.grid_lon, 4),
        "elevation": number(weather.elevation, 0),
        "timezone": weather.timezone,
        "bbox": bbox,
    }


def quality_summary(quality: pd.DataFrame) -> dict:
    """Overall data quality for the analysis years (yearly percentages averaged)."""
    low = quality.index[quality["missing_after_cleaning_pct"] > LOW_QUALITY_MISSING_PCT]
    return {
        "missing_raw_pct": number(quality["missing_raw_pct"].mean()),
        "filled_pct": number(quality["filled_pct"].mean()),
        "missing_after_cleaning_pct": number(quality["missing_after_cleaning_pct"].mean()),
        "impossible_values": int(quality["impossible_values"].sum()),
        "low_quality_years": [int(y) for y in low],
    }


def rounded_trend(trend: dict) -> dict:
    """Round the numbers in a trend_summary() result for JSON."""
    linear = trend["linear"]
    mk_result = trend["mann_kendall"]
    return {
        "linear": None if linear is None else {
            "slope_per_decade": number(linear["slope_per_decade"], 3),
            "intercept": number(linear["intercept"], 4),
            "p_value": number(linear["p_value"], 4),
            "r_squared": number(linear["r_squared"], 3),
        },
        "mann_kendall": None if mk_result is None else {
            "trend": mk_result["trend"],
            "p_value": number(mk_result["p_value"], 4),
            "tau": number(mk_result["tau"], 3),
            "sens_slope_per_decade": number(mk_result["sens_slope_per_decade"], 3),
        },
        "significant": trend["significant"],
    }


def build_insights(yearly: pd.DataFrame, metric_trends: dict, events: pd.DataFrame, quality: pd.DataFrame) -> list[str]:
    """Plain-English summary sentences, most important first."""
    if events.empty:
        return [
            "No heatwaves were detected in this period with the chosen settings. "
            "Try a lower percentile or a shorter minimum duration."
        ]
    insights = [trends.describe_change(m, yearly, metric_trends[m]) for m in INSIGHT_METRICS]

    low = quality.index[quality["missing_after_cleaning_pct"] > LOW_QUALITY_MISSING_PCT]
    if len(low) > 0:
        insights.append(
            f"Data note: {len(low)} year(s) are missing more than {LOW_QUALITY_MISSING_PCT:.0f}% of days "
            f"({', '.join(str(y) for y in low)}), so heatwaves in those years may be undercounted."
        )
    return insights
