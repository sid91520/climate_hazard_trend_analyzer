import numpy as np
import pandas as pd
import pytest

from app.services.heatwave import (
    annual_threshold,
    calendar_day,
    day_of_year_threshold,
    daily_threshold,
    default_baseline,
    detect_events,
    yearly_metrics,
)


def series(values, start="2000-06-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype="float64")


def events_for(values, threshold=30.0, min_duration=3):
    tmax = series(values)
    return detect_events(tmax, pd.Series(threshold, index=tmax.index), min_duration)


# ------------------------------------------------------------ event detection

def test_exactly_two_hot_days_is_not_a_heatwave():
    assert events_for([25, 31, 31, 25]).empty


def test_exactly_three_hot_days_is_a_heatwave():
    events = events_for([25, 31, 32, 33, 25])
    assert len(events) == 1
    event = events.iloc[0]
    assert event["duration"] == 3
    assert event["start"] == pd.Timestamp("2000-06-02")
    assert event["end"] == pd.Timestamp("2000-06-04")
    assert event["peak_temp"] == 33
    assert event["mean_excess"] == pytest.approx(2.0)  # (1 + 2 + 3) / 3


def test_runs_at_start_and_end_of_series_are_detected():
    events = events_for([31, 31, 31, 25, 25, 31, 31, 31])
    assert events["duration"].tolist() == [3, 3]
    assert events["start"].iloc[0] == pd.Timestamp("2000-06-01")
    assert events["end"].iloc[1] == pd.Timestamp("2000-06-08")


def test_equal_to_threshold_is_not_hot():
    # The definition is strictly "above" the threshold.
    assert events_for([30, 30, 30, 30]).empty


def test_missing_day_breaks_a_run_instead_of_joining_two():
    # 2 hot + NaN + 2 hot: two short runs, not one 5-day heatwave.
    assert events_for([31, 31, np.nan, 31, 31]).empty
    # And 3 hot + NaN + 3 hot is two separate heatwaves.
    assert events_for([31, 31, 31, np.nan, 31, 31, 31])["duration"].tolist() == [3, 3]


def test_min_duration_is_a_parameter():
    assert len(events_for([31, 31, 25], min_duration=2)) == 1
    assert events_for([31, 31, 31, 25], min_duration=4).empty


def test_no_hot_days_gives_empty_frame_with_columns():
    events = events_for([20, 21, 22])
    assert events.empty
    assert list(events.columns) == ["start", "end", "duration", "peak_temp", "mean_excess"]


# ------------------------------------------------------------ thresholds

def test_annual_threshold_is_the_percentile_of_all_days():
    tmax = series(np.arange(1, 101))  # 1..100
    assert annual_threshold(tmax, 95) == pytest.approx(np.percentile(np.arange(1, 101), 95))


def test_calendar_day_maps_29_feb_onto_28_feb_in_leap_years():
    dates = pd.to_datetime(["2000-02-28", "2000-02-29", "2000-03-01", "2001-03-01", "2000-12-31"])
    assert calendar_day(dates).tolist() == [59, 59, 60, 60, 365]


def test_day_of_year_threshold_follows_the_season():
    # 10 years of a pure seasonal cycle: cold in January, hot in July.
    dates = pd.date_range("1990-01-01", "1999-12-31", freq="D")
    tmax = pd.Series(20 - 10 * np.cos(2 * np.pi * calendar_day(dates) / 365), index=dates)
    curve = day_of_year_threshold(tmax, 95)

    assert len(curve) == 365
    assert curve.loc[1] < 12  # around 10 °C in early January
    assert curve.loc[182] > 29  # around 30 °C in early July


def test_day_of_year_threshold_window_wraps_around_new_year():
    # Make only 31 December hot. With a ±7-day window, early January's threshold
    # must "see" those hot values from the end of the previous year.
    dates = pd.date_range("1990-01-01", "1999-12-31", freq="D")
    tmax = pd.Series(10.0, index=dates)
    tmax[(dates.month == 12) & (dates.day == 31)] = 40.0
    curve = day_of_year_threshold(tmax, 99)
    assert curve.loc[3] > 10
    assert curve.loc[180] == 10


def test_daily_threshold_annual_method_is_constant():
    tmax = series(np.arange(10))
    assert daily_threshold(tmax, tmax, 50, "annual").nunique() == 1


def test_default_baseline():
    assert default_baseline(1950, 2020) == (1961, 1990)  # WMO period when covered
    assert default_baseline(1990, 2020) == (1990, 2019)  # else first 30 years
    assert default_baseline(2005, 2020) == (2005, 2020)  # or the whole range if shorter


# ------------------------------------------------------------ yearly metrics

def test_yearly_metrics_counts_events_by_start_year():
    tmax = series(np.full(800, 25.0), start="2000-01-01")
    tmax["2000-07-01":"2000-07-03"] = 32.0  # 3 days, excess 2
    tmax["2000-08-01":"2000-08-05"] = 34.0  # 5 days, excess 4
    tmax["2000-12-30":"2001-01-02"] = 31.0  # 4 days spanning New Year, excess 1
    threshold = pd.Series(30.0, index=tmax.index)
    events = detect_events(tmax, threshold)

    metrics = yearly_metrics(tmax, events, [2000, 2001, 2002])

    assert metrics.loc[2000, "events"] == 3
    assert metrics.loc[2000, "heatwave_days"] == 12
    assert metrics.loc[2000, "longest_event"] == 5
    # Day-weighted: (3*2 + 5*4 + 4*1) / 12
    assert metrics.loc[2000, "mean_intensity"] == pytest.approx(30 / 12)
    assert metrics.loc[2000, "max_tmax"] == 34
    # The New Year event belongs to 2000 only; 2001 has none.
    assert metrics.loc[2001, "events"] == 0
    assert np.isnan(metrics.loc[2001, "mean_intensity"])
