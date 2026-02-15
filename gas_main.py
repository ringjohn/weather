#!/usr/bin/env python3
"""CLI for EIA gas storage analysis and degree day regression."""

import io
import sys

if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import argparse
from datetime import date, timedelta

import pandas as pd

from eia_gas.client import EIAStorageClient
from eia_gas.noaa_cpc import NOAACPCClient
from eia_gas.cache import GasDataCache
from eia_gas.regression import GasFlowRegression
from eia_gas.display import (
    print_regression_summary, print_gas_forecast_table,
    print_storage_history, plot_regression_fit, plot_storage_forecast,
)


def cmd_bootstrap(cache):
    """Download full EIA + NOAA CPC history."""
    print("=== Bootstrapping EIA storage history ===")
    client = EIAStorageClient()
    df = client.fetch_all_history()
    print(f"Downloaded {len(df)} weekly storage reports from EIA.")
    cache.save_storage(df)
    cache.recompute_implied_flows()
    print("Saved to cache.")

    print("\n=== Bootstrapping NOAA CPC degree day history ===")
    # Start from 3 years before earliest EIA data for regression context
    start = date(1993, 1, 1)
    end = date.today()
    cpc = NOAACPCClient()
    cpc.fetch_history_range(start, end, cache=cache, rate_limit=0.2)
    print("NOAA CPC bootstrap complete.")


def cmd_update(cache):
    """Refresh with latest EIA + NOAA data."""
    # Update EIA storage
    latest_eia = cache.get_latest_storage_date()
    if latest_eia:
        start = latest_eia
        print(f"Updating EIA storage from {start}...")
    else:
        print("No EIA data cached. Run --bootstrap first.")
        return

    client = EIAStorageClient()
    df = client.fetch_storage(start_date=start)
    if not df.empty:
        cache.save_storage(df)
        cache.recompute_implied_flows()
        print(f"Updated {len(df)} EIA records.")
    else:
        print("No new EIA data.")

    # Update NOAA CPC
    latest_dd = cache.get_latest_dd_date()
    if latest_dd:
        start_dd = date.fromisoformat(latest_dd) - timedelta(days=7)
    else:
        start_dd = date.today() - timedelta(days=30)

    print(f"Updating NOAA CPC degree days from {start_dd}...")
    cpc = NOAACPCClient()
    # Try live file first
    try:
        live_df = cpc.fetch_live()
        cache.save_degree_days(live_df)
        print(f"Updated live CPC data: {live_df.iloc[0]['week_end_date']}")
    except Exception as e:
        print(f"Live CPC fetch failed: {e}")

    # Also fetch any archive gaps
    cpc.fetch_history_range(start_dd, date.today(), cache=cache, rate_limit=0.1)


def cmd_coefficients(cache, no_chart=False):
    """Show current regression coefficients."""
    reg = GasFlowRegression()
    dataset = cache.get_regression_dataset(lookback_weeks=160)
    if len(dataset) < 20:
        print(f"Insufficient data for regression ({len(dataset)} rows). Run --bootstrap.")
        return

    coefs = reg.fit_current(dataset)
    print_regression_summary(coefs)

    if not no_chart:
        print("Computing rolling regression (this may take a moment)...")
        full_data = cache.get_regression_dataset(lookback_weeks=5000)
        rolling = reg.fit_rolling(full_data)
        if not rolling.empty:
            plot_regression_fit(rolling)


def cmd_history(cache, n=10):
    """Show recent storage history."""
    storage = cache.get_storage()
    if storage.empty:
        print("No storage data. Run --bootstrap.")
        return
    print_storage_history(storage, n=n)


def cmd_forecast(cache, model='gfs', no_chart=False):
    """Predict gas flows from weather forecast."""
    from degree_days.cache import ForecastCache
    from degree_days.extractor import DegreeDayExtractor

    # Get regression coefficients
    reg = GasFlowRegression()
    dataset = cache.get_regression_dataset(lookback_weeks=160)
    if len(dataset) < 20:
        print(f"Insufficient data for regression ({len(dataset)} rows). Run --bootstrap.")
        return

    coefs = reg.fit_current(dataset)
    print_regression_summary(coefs)

    # Get latest weather forecast
    fcst_cache = ForecastCache()
    runs = fcst_cache.get_recent_runs(model, n=1)
    if not runs:
        print(f"No cached {model.upper()} forecast. Run: python main.py --model {model}")
        return

    run_date, run_hour, daily_df = runs[0]
    print(f"Using {model.upper()} forecast: {run_date} {run_hour:02d}z")

    # Get latest storage level
    storage = cache.get_storage()
    if storage.empty:
        print("No storage data. Run --bootstrap.")
        return
    latest_storage = storage.iloc[-1]['storage_bcf']
    print(f"Latest storage: {latest_storage:.0f} Bcf ({storage.iloc[-1]['period']})")
    print()

    # Predict
    forecast = reg.predict_from_forecast(coefs, daily_df, latest_storage)
    if forecast.empty:
        print("No forecast weeks generated.")
        return

    print_gas_forecast_table(forecast, latest_storage)

    if not no_chart:
        plot_storage_forecast(storage, forecast)


def main():
    parser = argparse.ArgumentParser(description="EIA Gas Storage & Degree Day Regression")
    parser.add_argument('--bootstrap', action='store_true',
                        help='Download full EIA + NOAA history (first run)')
    parser.add_argument('--update', action='store_true',
                        help='Refresh with latest data')
    parser.add_argument('--coefficients', action='store_true',
                        help='Show current regression coefficients')
    parser.add_argument('--history', action='store_true',
                        help='Show recent storage history')
    parser.add_argument('--forecast', action='store_true',
                        help='Predict gas flows from weather forecast')
    parser.add_argument('--model', default='gfs',
                        help='Weather model for forecast (default: gfs)')
    parser.add_argument('--no-chart', action='store_true',
                        help='Skip chart generation')
    parser.add_argument('--history-weeks', type=int, default=10,
                        help='Number of weeks for --history (default: 10)')
    args = parser.parse_args()

    cache = GasDataCache()

    if args.bootstrap:
        cmd_bootstrap(cache)
    elif args.update:
        cmd_update(cache)
    elif args.coefficients:
        cmd_coefficients(cache, no_chart=args.no_chart)
    elif args.history:
        cmd_history(cache, n=args.history_weeks)
    elif args.forecast:
        cmd_forecast(cache, model=args.model, no_chart=args.no_chart)
    else:
        # Default: update + show coefficients + show history
        cmd_update(cache)
        cmd_coefficients(cache, no_chart=args.no_chart)
        cmd_history(cache)


if __name__ == '__main__':
    main()
