"""Data cleaning for a daily Tmax series: impossible values, short gaps, quality report.

Order matters: impossible values are turned into NaN *first*, so they become gaps
and get the same treatment as genuinely missing days.
"""

from dataclasses import dataclass

import pandas as pd

# Beyond the observed world records (about -89 °C and +57 °C), so anything outside
# this range is a data error, not weather.
TMAX_MIN_C = -90.0
TMAX_MAX_C = 60.0

# Interpolating one or two days barely changes the statistics. Longer gaps are left
# missing because an invented week of temperatures could create or hide a heatwave.
MAX_GAP_TO_FILL = 2


@dataclass
class CleanedSeries:
    tmax: pd.Series  # complete daily index; NaN only where gaps were too long to fill
    quality: pd.DataFrame  # one row per year (see yearly_quality)


def to_complete_daily_index(tmax: pd.Series, start: str, end: str) -> pd.Series:
    """Reindex to every calendar day in [start, end], so missing dates become NaN.

    Event detection relies on "next row = next day"; this guarantees it.
    """
    full_index = pd.date_range(start, end, freq="D")
    return tmax.reindex(full_index)


def remove_impossible_values(tmax: pd.Series) -> pd.Series:
    """Set physically impossible temperatures to NaN."""
    return tmax.where((tmax >= TMAX_MIN_C) & (tmax <= TMAX_MAX_C))


def fill_short_gaps(tmax: pd.Series, max_gap: int = MAX_GAP_TO_FILL) -> pd.Series:
    """Linearly interpolate runs of at most `max_gap` missing days; leave longer runs as NaN.

    pandas' `interpolate(limit=n)` is not enough here: on a 5-day gap it would still
    fill the first n days. So we measure each gap's full length first.
    """
    is_missing = tmax.isna()
    # A new block starts whenever the missing/present state changes.
    block_id = (is_missing != is_missing.shift()).cumsum()
    gap_length = is_missing.groupby(block_id).transform("size")
    short_gap = is_missing & (gap_length <= max_gap)

    # limit_area="inside": only fill between two known values, never extrapolate at the edges.
    interpolated = tmax.interpolate(method="linear", limit_area="inside")
    return tmax.where(~short_gap, interpolated)


def yearly_quality(raw: pd.Series, impossible: pd.Series, cleaned: pd.Series) -> pd.DataFrame:
    """Per-year data-quality percentages (index = year)."""
    year = raw.index.year
    filled = raw.isna() | impossible  # days that were missing or bad before cleaning
    return pd.DataFrame(
        {
            "missing_raw_pct": raw.isna().groupby(year).mean() * 100,
            "impossible_values": impossible.groupby(year).sum().astype(int),
            "filled_pct": (filled & cleaned.notna()).groupby(year).mean() * 100,
            "missing_after_cleaning_pct": cleaned.isna().groupby(year).mean() * 100,
        }
    )


def clean_tmax(tmax: pd.Series, start: str, end: str) -> CleanedSeries:
    """Run the full cleaning pipeline and report data quality per year."""
    raw = to_complete_daily_index(tmax, start, end)
    valid = remove_impossible_values(raw)
    impossible = raw.notna() & valid.isna()
    cleaned = fill_short_gaps(valid)
    return CleanedSeries(tmax=cleaned, quality=yearly_quality(raw, impossible, cleaned))
