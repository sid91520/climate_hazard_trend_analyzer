"""Run the heatwave analysis for one point and print it (no API server, no database).

Usage, from the backend/ folder:
    python -m scripts.analyze_city --lat 19.07 --lon 72.88 --start 1980 --end 2023
"""

import argparse
import asyncio

import pandas as pd

from app.schemas import HeatwaveQuery
from app.services.analysis import fetch_range, run_heatwave_analysis
from app.services.weather_client import fetch_daily_tmax


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--percentile", type=float, default=95)
    parser.add_argument("--min-duration", type=int, default=3)
    parser.add_argument("--method", choices=["doy", "annual"], default="doy")
    args = parser.parse_args()

    query = HeatwaveQuery(
        lat=args.lat, lon=args.lon, start_year=args.start, end_year=args.end,
        percentile=args.percentile, min_duration=args.min_duration, method=args.method,
    )
    weather = await fetch_daily_tmax(*query.point(), *fetch_range(query))
    result = run_heatwave_analysis(weather, query)

    meta = result["metadata"]
    print("Location:", meta["location"])
    print("Threshold:", meta["threshold"])
    print("Data quality:", meta["data_quality"])
    print()
    columns = ["year", "events", "heatwave_days", "longest_event", "mean_intensity", "max_tmax", "heatwave_days_rolling"]
    print(pd.DataFrame(result["yearly"])[columns].to_string(index=False))
    print(f"\n{len(result['events'])} events. Longest five:")
    print(pd.DataFrame(result["events"]).sort_values("duration", ascending=False).head().to_string(index=False))
    print("\nTrends (per decade):")
    for metric, trend in result["trends"].items():
        mk_result, linear = trend["mann_kendall"], trend["linear"]
        if mk_result:
            print(f"  {metric:15} OLS {linear['slope_per_decade']:+.3f} (p={linear['p_value']:.3f})   "
                  f"Sen {mk_result['sens_slope_per_decade']:+.3f}  MK p={mk_result['p_value']:.3f}  {mk_result['trend']}")
    print("\nInsights:")
    for sentence in result["insights"]:
        print(" -", sentence)


if __name__ == "__main__":
    asyncio.run(main())
