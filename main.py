#!/usr/bin/env python3
"""CLI entry point for degree day forecasting."""

import io
import sys

# Fix Windows console encoding for Herbie's emoji output
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
from datetime import datetime

import pandas as pd

from degree_days.extractor import DegreeDayExtractor
from degree_days.cache import ForecastCache
from degree_days.normals import normals_for_dates
from degree_days.display import (
    print_forecast_table,
    print_trend_table,
    plot_forecast_vs_normals,
    plot_trend,
)


def parse_run_date(date_str):
    """Parse a run date string into (date, hour) for cache storage."""
    ts = pd.Timestamp(date_str)
    return ts.strftime('%Y-%m-%d'), ts.hour


def main():
    parser = argparse.ArgumentParser(description="Degree Day Forecast Tool")
    parser.add_argument('--model', default='gfs', help='Forecast model (gfs, gefs, ifs, aifs)')
    parser.add_argument('--date', default=None, help='Model run date (YYYY-MM-DD or YYYY-MM-DD HH:00)')
    parser.add_argument('--trend', action='store_true', help='Show trend of recent cached runs')
    parser.add_argument('--trend-date', default=None, help='Target date for trend chart (YYYY-MM-DD)')
    parser.add_argument('--no-cache', action='store_true', help='Skip caching')
    parser.add_argument('--no-chart', action='store_true', help='Skip chart generation')
    parser.add_argument('--weights', default=None, help='Path to weights CSV')
    args = parser.parse_args()

    cache = ForecastCache()

    if args.trend:
        runs = cache.get_recent_runs(args.model)
        print_trend_table(runs, model=args.model)
        if args.trend_date:
            plot_trend(runs, args.trend_date)
        return

    # Determine run date
    if args.date:
        run_date_str = args.date
    else:
        run_date_str = (
            pd.Timestamp.now('UTC') - pd.Timedelta(hours=6)
        ).floor('6h').strftime("%Y-%m-%d %H:00")

    run_date, run_hour = parse_run_date(run_date_str)

    # Check cache first
    if not args.no_cache:
        cached = cache.get_run(args.model, run_date, run_hour)
        if cached is not None:
            print(f"Using cached {args.model.upper()} run: {run_date} {run_hour:02d}z")
            normals_df = normals_for_dates(cached['valid_date'].tolist())
            print_forecast_table(cached, normals_df)
            if not args.no_chart:
                plot_forecast_vs_normals(cached, normals_df)
            return

    # Fetch forecast
    print(f"Fetching {args.model.upper()} run: {run_date} {run_hour:02d}z ...")
    extractor = DegreeDayExtractor(weights_path=args.weights)
    daily_df = extractor.get_full_forecast(model=args.model, date=run_date_str)

    if daily_df.empty:
        print("No forecast data retrieved.")
        return

    # Cache the run
    if not args.no_cache:
        cache.save_run(args.model, run_date, run_hour, daily_df)
        print(f"Cached {len(daily_df)} days.")

    # Display
    normals_df = normals_for_dates(daily_df['valid_date'].tolist())
    print_forecast_table(daily_df, normals_df)
    if not args.no_chart:
        plot_forecast_vs_normals(daily_df, normals_df)


if __name__ == '__main__':
    main()
