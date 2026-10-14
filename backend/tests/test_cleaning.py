import numpy as np
import pandas as pd

from app.services.cleaning import clean_tmax, fill_short_gaps, remove_impossible_values


def series(values, start="2000-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype="float64")


def test_impossible_values_become_nan():
    s = series([25.0, 61.0, -95.0, 60.0, -90.0])
    out = remove_impossible_values(s)
    assert out.isna().tolist() == [False, True, True, False, False]


def test_gap_of_two_days_is_interpolated():
    s = series([10.0, np.nan, np.nan, 16.0])
    assert fill_short_gaps(s).tolist() == [10.0, 12.0, 14.0, 16.0]


def test_gap_of_three_days_is_left_entirely_missing():
    s = series([10.0, np.nan, np.nan, np.nan, 18.0])
    out = fill_short_gaps(s)
    # Not even the first two days of a long gap may be filled.
    assert out.isna().tolist() == [False, True, True, True, False]


def test_gaps_at_the_edges_are_not_extrapolated():
    s = series([np.nan, 10.0, 11.0, np.nan])
    assert fill_short_gaps(s).isna().tolist() == [True, False, False, True]


def test_clean_tmax_adds_missing_dates_and_reports_quality():
    # 2000-01-03 is absent from the input entirely; 61 °C on 2000-01-05 is impossible.
    s = pd.Series(
        [20.0, 21.0, 23.0, 61.0, 25.0],
        index=pd.to_datetime(["2000-01-01", "2000-01-02", "2000-01-04", "2000-01-05", "2000-01-06"]),
    )
    result = clean_tmax(s, "2000-01-01", "2000-01-06")

    assert len(result.tmax) == 6
    assert result.tmax.notna().all()  # both one-day gaps were filled
    q = result.quality.loc[2000]
    assert q["impossible_values"] == 1
    assert round(q["missing_raw_pct"], 1) == round(100 / 6, 1)
    assert round(q["filled_pct"], 1) == round(200 / 6, 1)
    assert q["missing_after_cleaning_pct"] == 0
