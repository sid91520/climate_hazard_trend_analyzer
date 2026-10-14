import numpy as np
import pandas as pd
import pytest

from app.services.trends import (
    comparison_periods,
    describe_change,
    linear_trend,
    mann_kendall,
    rolling_mean,
    trend_summary,
)

YEARS = pd.Series(range(1981, 2021), index=range(1981, 2021))  # 40 years
rng = np.random.default_rng(seed=42)  # fixed seed: the tests must not be flaky
NOISE = pd.Series(rng.normal(0, 1, len(YEARS)), index=YEARS.index)


def test_increasing_series():
    values = 0.5 * (YEARS - 1981) + NOISE  # +5 per decade
    linear = linear_trend(YEARS, values)
    mk_result = mann_kendall(YEARS, values)
    assert linear["slope_per_decade"] == pytest.approx(5, abs=0.5)
    assert linear["p_value"] < 0.001
    assert mk_result["trend"] == "increasing"
    assert mk_result["sens_slope_per_decade"] == pytest.approx(5, abs=0.5)


def test_decreasing_series():
    values = -0.5 * (YEARS - 1981) + NOISE
    assert mann_kendall(YEARS, values)["trend"] == "decreasing"
    assert trend_summary(YEARS, values)["significant"]


def test_flat_series_has_no_significant_trend():
    values = 10 + NOISE
    summary = trend_summary(YEARS, values)
    assert summary["mann_kendall"]["trend"] == "no trend"
    assert not summary["significant"]


def test_constant_series_does_not_crash():
    values = pd.Series(0.0, index=YEARS.index)
    summary = trend_summary(YEARS, values)
    assert summary["mann_kendall"]["sens_slope_per_decade"] == 0
    assert not summary["significant"]


def test_missing_years_are_skipped_and_slope_uses_real_years():
    values = 0.5 * (YEARS - 1981).astype(float)
    values.iloc[::3] = np.nan  # drop every third year
    assert mann_kendall(YEARS, values)["sens_slope_per_decade"] == pytest.approx(5)


def test_too_few_points_returns_none():
    short = YEARS.iloc[:3]
    assert mann_kendall(short, short.astype(float)) is None
    assert linear_trend(short.iloc[:2], short.iloc[:2].astype(float)) is None


def test_rolling_mean_is_centred():
    values = pd.Series([0, 0, 10, 0, 0, 0, 0], dtype=float)
    out = rolling_mean(values, window=5)
    assert out.iloc[2] == 2.0  # window 0..4
    assert out.iloc[0] == pytest.approx(10 / 3)  # edge: only 3 values available


def test_comparison_periods():
    assert comparison_periods(list(range(1991, 2021))) == (list(range(1991, 2001)), list(range(2011, 2021)))
    # A 12-year range is compared half against half.
    first, last = comparison_periods(list(range(2000, 2012)))
    assert first == list(range(2000, 2006)) and last == list(range(2006, 2012))


# ------------------------------------------------------------ insight text

def yearly_with(metric, values):
    return pd.DataFrame({metric: values}, index=YEARS.index)


def test_insight_uses_percent_when_base_is_large_enough():
    values = pd.Series(np.r_[np.full(10, 4.0), np.full(20, 6.0), np.full(10, 10.0)], index=YEARS.index)
    text = describe_change("heatwave_days", yearly_with("heatwave_days", values), trend_summary(YEARS, values))
    assert "rose from an average of 4.0 days/year (1981–1990) to 10.0 days/year (2011–2020)" in text
    assert "+150%" in text
    assert "statistically significant" in text and "not statistically" not in text


def test_insight_avoids_percent_when_base_is_near_zero():
    values = pd.Series(np.r_[np.full(10, 0.2), np.full(20, 0.5), np.full(10, 1.0)], index=YEARS.index)
    text = describe_change("events", yearly_with("events", values), trend_summary(YEARS, values))
    assert "%" not in text
    assert "+0.8 events/year" in text


def test_insight_says_when_trend_is_not_significant():
    values = 5 + NOISE
    text = describe_change("heatwave_days", yearly_with("heatwave_days", values), trend_summary(YEARS, values))
    assert "not statistically significant" in text


def test_insight_handles_period_without_heatwaves():
    values = pd.Series(np.r_[np.full(10, np.nan), np.full(30, 1.0)], index=YEARS.index)
    text = describe_change("mean_intensity", yearly_with("mean_intensity", values), trend_summary(YEARS, values))
    assert "no heatwaves occurred in 1981–1990" in text
