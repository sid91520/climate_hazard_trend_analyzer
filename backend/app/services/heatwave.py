"""Heatwave threshold, event detection and yearly metrics.

Every function here is pure: pandas in, pandas out, no I/O. That keeps the science
easy to unit-test with small synthetic series.

Definition used: a heatwave is at least `min_duration` consecutive days on which
daily maximum temperature is strictly above a percentile threshold computed from a
fixed baseline period.
"""

from typing import Literal

import numpy as np
import pandas as pd

DEFAULT_PERCENTILE = 95.0
DEFAULT_MIN_DURATION = 3
# ±7 days gives each calendar day 15 days × N baseline years of samples, which is
# enough for a stable 95th percentile while still following the seasonal cycle.
DOY_WINDOW_DAYS = 7
BASELINE_LENGTH_YEARS = 30  # the WMO convention for a climate "normal"

ThresholdMethod = Literal["doy", "annual"]
EVENT_COLUMNS = ["start", "end", "duration", "peak_temp", "mean_excess"]


def default_baseline(start_year: int, end_year: int) -> tuple[int, int]:
    """Pick the baseline period when the user did not choose one.

    Use the WMO reference period 1961-1990 if the requested range covers it,
    otherwise the first 30 years of the range (or the whole range if it is shorter).
    """
    if start_year <= 1961 and end_year >= 1990:
        return 1961, 1990
    return start_year, min(end_year, start_year + BASELINE_LENGTH_YEARS - 1)


def calendar_day(dates: pd.DatetimeIndex) -> np.ndarray:
    """Day of year on a fixed 365-day calendar (1..365).

    Plain `dayofyear` shifts every date after 29 Feb by one in leap years, so
    1 March would be compared with 2 March. Here 29 Feb shares day 59 with 28 Feb.
    """
    day = dates.dayofyear.to_numpy()
    after_feb_28_in_leap_year = dates.is_leap_year & (day > 59)
    return np.where(after_feb_28_in_leap_year, day - 1, day)


def annual_threshold(baseline_tmax: pd.Series, percentile: float) -> float:
    """One threshold for the whole year: the given percentile of all baseline days."""
    return float(np.nanpercentile(baseline_tmax.to_numpy(), percentile))


def day_of_year_threshold(
    baseline_tmax: pd.Series, percentile: float, window_days: int = DOY_WINDOW_DAYS
) -> pd.Series:
    """A threshold for each calendar day (index 1..365).

    The threshold for, say, 10 July is the percentile of all baseline Tmax values
    from 3-17 July. This catches unusually hot spells in any season, not just summer.

    Implementation: each observation is copied into the 2*window+1 calendar days
    around it, then we take one percentile per calendar day. No loop over days.
    """
    days = calendar_day(baseline_tmax.index)
    values = baseline_tmax.to_numpy()
    offsets = range(-window_days, window_days + 1)
    stacked = pd.DataFrame(
        {
            # Wraps around the year end, so 31 Dec's window includes early January.
            "day": np.concatenate([(days - 1 + offset) % 365 + 1 for offset in offsets]),
            "tmax": np.tile(values, len(offsets)),
        }
    )
    return stacked.groupby("day")["tmax"].quantile(percentile / 100)  # skips NaN


def daily_threshold(
    tmax: pd.Series, baseline_tmax: pd.Series, percentile: float, method: ThresholdMethod
) -> pd.Series:
    """The threshold that applies on each day of `tmax`, aligned to its index."""
    if method == "annual":
        return pd.Series(annual_threshold(baseline_tmax, percentile), index=tmax.index)
    curve = day_of_year_threshold(baseline_tmax, percentile)
    return pd.Series(curve.reindex(calendar_day(tmax.index)).to_numpy(), index=tmax.index)


def detect_events(tmax: pd.Series, threshold: pd.Series, min_duration: int = DEFAULT_MIN_DURATION) -> pd.DataFrame:
    """Find runs of at least `min_duration` consecutive days with Tmax > threshold.

    `tmax` must have a complete daily index (one row per day), which cleaning guarantees.
    A missing day (NaN) compares as not-hot, so it ends a run instead of joining
    two runs together. Returns one row per event with columns EVENT_COLUMNS.
    """
    hot = tmax > threshold
    # Same trick as gap filling: a new run starts whenever hot/not-hot flips.
    run_id = (hot != hot.shift()).cumsum()
    hot_days = pd.DataFrame(
        {"date": tmax.index, "tmax": tmax.to_numpy(), "excess": (tmax - threshold).to_numpy(), "run": run_id.to_numpy()}
    )[hot.to_numpy()]

    events = hot_days.groupby("run").agg(
        start=("date", "min"),
        end=("date", "max"),
        duration=("date", "size"),
        peak_temp=("tmax", "max"),
        mean_excess=("excess", "mean"),
    )
    events = events[events["duration"] >= min_duration]
    return events.reset_index(drop=True)[EVENT_COLUMNS]


def yearly_metrics(tmax: pd.Series, events: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Per-year heatwave statistics (index = year).

    An event is counted in the year it *starts*, so a heatwave spanning New Year is
    counted once, not split in two.
    """
    events = events.assign(
        year=events["start"].dt.year,
        total_excess=events["mean_excess"] * events["duration"],
    )
    by_year = events.groupby("year")

    metrics = pd.DataFrame(index=pd.Index(years, name="year"))
    metrics["events"] = by_year.size().reindex(years, fill_value=0)
    metrics["heatwave_days"] = by_year["duration"].sum().reindex(years, fill_value=0)
    metrics["longest_event"] = by_year["duration"].max().reindex(years, fill_value=0)
    # Day-weighted mean excess. NaN (not 0) in years without heatwaves: "no heatwave"
    # is not the same as "a heatwave of zero intensity".
    metrics["mean_intensity"] = (by_year["total_excess"].sum() / by_year["duration"].sum()).reindex(years)
    metrics["max_tmax"] = tmax.groupby(tmax.index.year).max().reindex(years)
    return metrics
