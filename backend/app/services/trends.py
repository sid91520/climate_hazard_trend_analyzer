"""Trend statistics and plain-English insight sentences for yearly metrics.

Pure functions, no I/O. All slopes are reported per decade because "+1.2 days per
decade" is easier to read than "+0.12 days per year".
"""

import numpy as np
import pandas as pd
import pymannkendall as mk
from scipy import stats

ROLLING_WINDOW_YEARS = 5
SIGNIFICANCE_LEVEL = 0.05
COMPARISON_PERIOD_YEARS = 10  # compare decade averages, not single (noisy) years

# A percentage change is only shown when the earlier average is at least this big.
# Going from 0.2 to 1.0 days/year is "+400%", which sounds dramatic but is less
# than one day; the absolute change is the honest number there.
MIN_BASE_FOR_PERCENT = 1.0

# key -> (label at the start of a sentence, unit for averages, unit for changes, show a % change?)
METRIC_INFO = {
    "events": ("Heatwave events", "events/year", "events/year", True),
    "heatwave_days": ("Heatwave days", "days/year", "days/year", True),
    "longest_event": ("The longest heatwave of the year", "days", "days", True),
    # A % of "°C above threshold" is not meaningful, so intensity uses °C only.
    "mean_intensity": ("Mean heatwave intensity", "°C above the threshold", "°C", False),
    "max_tmax": ("The hottest day of the year", "°C", "°C", False),
}


def rolling_mean(values: pd.Series, window: int = ROLLING_WINDOW_YEARS) -> pd.Series:
    """Centred rolling mean; needs at least 3 non-missing years in each window."""
    return values.rolling(window, center=True, min_periods=3).mean()


def linear_trend(years: pd.Series, values: pd.Series) -> dict | None:
    """Ordinary least-squares slope. Returns None if fewer than 3 usable years."""
    ok = values.notna()
    if ok.sum() < 3:
        return None
    result = stats.linregress(years[ok].astype(float), values[ok].astype(float))
    return {
        "slope_per_decade": result.slope * 10,
        "intercept": result.intercept,  # lets the frontend draw the line: intercept + slope/10 * year
        "p_value": result.pvalue,
        "r_squared": result.rvalue**2,
    }


def mann_kendall(years: pd.Series, values: pd.Series) -> dict | None:
    """Mann-Kendall trend test plus Sen's slope.

    Mann-Kendall only asks "do later years tend to be higher than earlier ones?", so
    unlike regression it does not assume a straight line or normal residuals, and a
    single extreme year cannot dominate it. Sen's slope (median of all pairwise
    slopes) is the matching robust estimate of the rate of change.
    """
    ok = values.notna()
    if ok.sum() < 4:
        return None
    test = mk.original_test(values[ok].to_numpy())
    # pymannkendall's own slope assumes evenly spaced points; years with no value
    # (e.g. intensity when there was no heatwave) break that, so use real years.
    sens_slope = stats.theilslopes(values[ok].to_numpy(), years[ok].to_numpy())[0]
    return {
        "trend": test.trend,  # "increasing", "decreasing" or "no trend"
        "p_value": test.p,
        "tau": test.Tau,
        "sens_slope_per_decade": sens_slope * 10,
    }


def trend_summary(years: pd.Series, values: pd.Series) -> dict:
    """Both tests for one metric. Significance is judged on Mann-Kendall (see above)."""
    mk_result = mann_kendall(years, values)
    significant = bool(mk_result is not None and mk_result["p_value"] < SIGNIFICANCE_LEVEL)
    return {"linear": linear_trend(years, values), "mann_kendall": mk_result, "significant": significant}


def comparison_periods(years: list[int]) -> tuple[list[int], list[int]]:
    """First and last decade of the range (or halves, if the range is under 20 years)."""
    length = min(COMPARISON_PERIOD_YEARS, len(years) // 2)
    return years[:length], years[-length:]


def format_p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def describe_change(metric: str, yearly: pd.DataFrame, trend: dict) -> str:
    """One or two sentences: decade-average change, then whether the trend is significant."""
    label, unit, change_unit, allow_percent = METRIC_INFO[metric]
    first_years, last_years = comparison_periods(list(yearly.index))
    first = yearly.loc[first_years, metric].mean()  # mean() skips NaN years
    last = yearly.loc[last_years, metric].mean()
    first_label = f"{first_years[0]}–{first_years[-1]}"
    last_label = f"{last_years[0]}–{last_years[-1]}"

    if np.isnan(first) or np.isnan(last):
        empty = first_label if np.isnan(first) else last_label
        change = f"{label}: no heatwaves occurred in {empty}, so the two periods can't be compared."
    elif round(first, 1) == round(last, 1):
        change = f"{label} stayed about the same: {first:.1f} {unit} in {first_label} and {last:.1f} in {last_label}."
    else:
        verb = "rose" if last > first else "fell"
        change = f"{label} {verb} from an average of {first:.1f} {unit} ({first_label}) to {last:.1f} {unit} ({last_label})"
        if allow_percent and first >= MIN_BASE_FOR_PERCENT:
            change += f", a change of {(last - first) / first * 100:+.0f}%."
        else:
            change += f", a change of {last - first:+.1f} {change_unit}."

    mk_result = trend["mann_kendall"]
    if mk_result is None:
        return change + " There are too few years with heatwaves to test for a trend."
    p = format_p(mk_result["p_value"])
    if trend["significant"]:
        direction = "upward" if mk_result["trend"] == "increasing" else "downward"
        slope = mk_result["sens_slope_per_decade"]
        return change + (
            f" The {direction} trend is statistically significant "
            f"(Mann-Kendall {p}; Sen's slope {slope:+.2f} {change_unit} per decade)."
        )
    return change + (
        f" The trend is not statistically significant (Mann-Kendall {p}), "
        "so this difference may just be natural year-to-year variation."
    )
