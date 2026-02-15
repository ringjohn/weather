#!/usr/bin/env python3
"""CLI entry point for degree day forecasting."""

import io
import sys

# Fix Windows console encoding for Herbie's emoji output
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
from datetime import datetime, timedelta

import pandas as pd

from degree_days.extractor import DegreeDayExtractor, MODEL_CONFIG
from degree_days.cache import ForecastCache
from degree_days.normals import normals_for_dates
from degree_days.display import (
    print_forecast_table,
    print_trend_table,
    print_model_comparison_table,
    plot_forecast_vs_normals,
    plot_trend,
    print_changes_table,
    plot_changes,
)


def parse_run_date(date_str):
    """Parse a run date string into (date, hour) for cache storage."""
    ts = pd.Timestamp(date_str)
    return ts.strftime('%Y-%m-%d'), ts.hour


def _run_label(run_date, run_hour):
    return f"{run_date} {run_hour:02d}z"


def _is_weekend_or_monday_00z(run_date, run_hour):
    d = datetime.strptime(run_date, '%Y-%m-%d').date()
    return d.weekday() in (5, 6) or (d.weekday() == 0 and run_hour == 0)


def _fetch_or_cached(cache, extractor, model, run_date_str, no_cache=False):
    """Fetch a forecast run, using cache if available. Returns (run_date, run_hour, daily_df)."""
    run_date, run_hour = parse_run_date(run_date_str)
    if not no_cache:
        cached = cache.get_run(model, run_date, run_hour)
        if cached is not None:
            return run_date, run_hour, cached
    print(f"Fetching {model.upper()} run: {run_date} {run_hour:02d}z ...")
    daily_df = extractor.get_full_forecast(model=model, date=run_date_str)
    if not daily_df.empty and not no_cache:
        cache.save_run(model, run_date, run_hour, daily_df)
        print(f"Cached {len(daily_df)} days.")
    return run_date, run_hour, daily_df


def _backfill(cache, extractor, model, current_run_date, current_run_hour, lookback_hours=48):
    """Backfill any missing forecast runs within the lookback window."""
    dt = datetime.strptime(current_run_date, '%Y-%m-%d') + timedelta(hours=current_run_hour)

    cfg = MODEL_CONFIG.get(model, MODEL_CONFIG['gfs'])
    cycle_hours = cfg['cycle_hours']

    existing = set(cache.get_all_runs(model))

    runs_to_check = []
    t = dt - timedelta(hours=cycle_hours)
    cutoff = dt - timedelta(hours=lookback_hours)
    while t >= cutoff:
        rd = t.strftime('%Y-%m-%d')
        rh = t.hour
        if (rd, rh) not in existing:
            runs_to_check.append((rd, rh, t.strftime('%Y-%m-%d %H:00')))
        t -= timedelta(hours=cycle_hours)

    if not runs_to_check:
        return

    print(f"Backfilling {len(runs_to_check)} missing {model.upper()} run(s)...")
    for rd, rh, date_str in runs_to_check:
        print(f"  Backfill: {rd} {rh:02d}z")
        try:
            daily_df = extractor.get_full_forecast(model=model, date=date_str)
            if not daily_df.empty:
                cache.save_run(model, rd, rh, daily_df)
                print(f"  Cached {len(daily_df)} days for {rd} {rh:02d}z")
        except Exception as e:
            print(f"  Backfill failed for {rd} {rh:02d}z: {e}")


def _generate_changes(cache, current_df, model, run_date, run_hour, no_chart=False):
    """Generate change tables and charts for 12h, 24h, and weekend/Friday comparisons."""
    cur_label = _run_label(run_date, run_hour)

    comparisons = []

    # 12-hour change
    prev_12h = cache.get_run_by_offset(model, run_date, run_hour, 12)
    if prev_12h is not None:
        dt_prev = datetime.strptime(run_date, '%Y-%m-%d') + timedelta(hours=run_hour) - timedelta(hours=12)
        prev_label = _run_label(dt_prev.strftime('%Y-%m-%d'), dt_prev.hour)
        comparisons.append(('12h', prev_12h, prev_label))

    # 24-hour change
    prev_24h = cache.get_run_by_offset(model, run_date, run_hour, 24)
    if prev_24h is not None:
        dt_prev = datetime.strptime(run_date, '%Y-%m-%d') + timedelta(hours=run_hour) - timedelta(hours=24)
        prev_label = _run_label(dt_prev.strftime('%Y-%m-%d'), dt_prev.hour)
        comparisons.append(('24h', prev_24h, prev_label))

    # Weekend/Monday: compare vs Friday 12z
    if _is_weekend_or_monday_00z(run_date, run_hour):
        fri_df = cache.get_friday_12z(model, run_date)
        if fri_df is not None:
            d = datetime.strptime(run_date, '%Y-%m-%d').date()
            days_since_friday = (d.weekday() - 4) % 7
            friday = d - timedelta(days=days_since_friday)
            fri_label = _run_label(friday.strftime('%Y-%m-%d'), 12)
            comparisons.append(('fri12z', fri_df, fri_label))

    for tag, compare_df, compare_label in comparisons:
        print_changes_table(current_df, compare_df, cur_label, compare_label)
        if not no_chart:
            save_path = f"changes_{tag}_{run_date}_{run_hour:02d}z.png"
            plot_changes(current_df, compare_df, cur_label, compare_label, save_path=save_path)


def main():
    parser = argparse.ArgumentParser(description="Degree Day Forecast Tool")
    model_names = ', '.join(MODEL_CONFIG.keys())
    parser.add_argument('--model', default='gfs', help=f'Forecast model ({model_names})')
    parser.add_argument('--date', default=None, help='Model run date (YYYY-MM-DD or YYYY-MM-DD HH:00)')
    parser.add_argument('--trend', action='store_true', help='Show trend of recent cached runs')
    parser.add_argument('--trend-date', default=None, help='Target date for trend chart (YYYY-MM-DD)')
    parser.add_argument('--compare', nargs='?', const='latest', metavar='DATE_HHz',
                        help='Compare models for a cycle (e.g. "2026-02-14 00z") or "latest"')
    parser.add_argument('--changes', action='store_true', help='Show changes vs previous runs')
    parser.add_argument('--no-cache', action='store_true', help='Skip caching')
    parser.add_argument('--no-chart', action='store_true', help='Skip chart generation')
    parser.add_argument('--no-backfill', action='store_true', help='Skip backfilling missing runs')
    parser.add_argument('--weights', default=None, help='Path to weights CSV')
    args = parser.parse_args()

    cache = ForecastCache()

    if args.compare is not None:
        compare_models = ['gfs', 'gefs', 'ecmwf', 'ecmwf-ens', 'aifs']
        if args.compare == 'latest':
            # Find the most recent cycle where at least 2 models have data
            from collections import Counter
            cycle_counts = Counter()
            model_cycles = {}
            for m in compare_models:
                for rd, rh in cache.get_all_runs(m):
                    cycle_counts[(rd, rh)] += 1
                    model_cycles.setdefault((rd, rh), []).append(m)
            # Pick the cycle with the most models, breaking ties by most recent
            candidates = sorted(
                [(k, v) for k, v in cycle_counts.items() if v >= 2],
                key=lambda x: (x[1], x[0]), reverse=True,
            )
            if not candidates:
                print("No shared cycles found.")
                return
            (target_date, target_hour), _ = candidates[0]
        else:
            # Parse "2026-02-14 00z" or "2026-02-14 12:00"
            ts = pd.Timestamp(args.compare.replace('z', ':00'))
            target_date, target_hour = ts.strftime('%Y-%m-%d'), ts.hour

        model_runs = []
        for m in compare_models:
            df = cache.get_run(m, target_date, target_hour)
            if df is not None:
                model_runs.append((m, target_date, target_hour, df))
        print_model_comparison_table(model_runs)
        return

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
    extractor = DegreeDayExtractor(weights_path=args.weights)

    # Backfill missing runs
    if not args.no_cache and not args.no_backfill:
        _backfill(cache, extractor, args.model, run_date, run_hour)

    # Fetch current run (from cache or network)
    run_date, run_hour, daily_df = _fetch_or_cached(
        cache, extractor, args.model, run_date_str, no_cache=args.no_cache,
    )

    if daily_df.empty:
        print("No forecast data retrieved.")
        return

    # Cache the run
    if not args.no_cache:
        cache.save_run(args.model, run_date, run_hour, daily_df)

    # Display
    normals_df = normals_for_dates(daily_df['valid_date'].tolist())
    print_forecast_table(daily_df, normals_df)

    if not args.no_chart:
        run_label = _run_label(run_date, run_hour)
        save_path = f"forecast_{run_date}_{run_hour:02d}z.png"
        plot_forecast_vs_normals(daily_df, normals_df, save_path=save_path, run_label=run_label)

    # Changes
    if args.changes:
        _generate_changes(cache, daily_df, args.model, run_date, run_hour, no_chart=args.no_chart)


if __name__ == '__main__':
    main()
