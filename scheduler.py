#!/usr/bin/env python3
"""Scheduler for periodic forecast fetching.

Runs on a loop, checking for new model runs and fetching them automatically.
Each model has known release cycles; the scheduler waits for availability
then fetches and caches the data.

Usage:
    python scheduler.py                    # Run all default models
    python scheduler.py --models gfs gefs  # Run specific models
    python scheduler.py --once             # Single pass, then exit
"""

import io
import sys

if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
import time
from datetime import datetime, timedelta, timezone

from degree_days.extractor import DegreeDayExtractor, MODEL_CONFIG
from degree_days.cache import ForecastCache

# Default models to schedule (skip 'ifs' alias to avoid duplicate with 'ecmwf')
DEFAULT_MODELS = ['gfs', 'gefs', 'ecmwf', 'ecmwf-ens', 'aifs']


def _latest_cycle(model, now_utc):
    """Return the most recent cycle (date_str, hour) that should be available by now."""
    cfg = MODEL_CONFIG.get(model, MODEL_CONFIG['gfs'])
    cycle_h = cfg['cycle_hours']
    delay_h = cfg['delay_hours']

    available_time = now_utc - timedelta(hours=delay_h)
    cycle_hour = (available_time.hour // cycle_h) * cycle_h
    cycle_dt = available_time.replace(hour=cycle_hour, minute=0, second=0, microsecond=0)

    return cycle_dt.strftime('%Y-%m-%d'), cycle_dt.hour


def _recent_cycles(model, now_utc, lookback_hours=48):
    """Return list of (date_str, hour) for all cycles within lookback window."""
    cfg = MODEL_CONFIG.get(model, MODEL_CONFIG['gfs'])
    cycle_h = cfg['cycle_hours']

    latest_date, latest_hour = _latest_cycle(model, now_utc)
    latest_dt = datetime.strptime(latest_date, '%Y-%m-%d').replace(
        hour=latest_hour, tzinfo=timezone.utc
    )
    cutoff = now_utc - timedelta(hours=lookback_hours)

    cycles = []
    t = latest_dt
    while t >= cutoff:
        cycles.append((t.strftime('%Y-%m-%d'), t.hour))
        t -= timedelta(hours=cycle_h)
    return cycles


def run_once(models, cache, extractor):
    """Single pass: check each model for missing runs and fetch them."""
    now_utc = datetime.now(timezone.utc)
    fetched = 0

    for model in models:
        cfg = MODEL_CONFIG.get(model)
        if cfg is None:
            print(f"Unknown model '{model}', skipping.")
            continue

        existing = set(cache.get_all_runs(model))
        cycles = _recent_cycles(model, now_utc, lookback_hours=48)

        for run_date, run_hour in cycles:
            if (run_date, run_hour) in existing:
                continue

            date_str = f"{run_date} {run_hour:02d}:00"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Fetching {cfg['description']} {run_date} {run_hour:02d}z...")
            try:
                daily_df = extractor.get_full_forecast(model=model, date=date_str)
                if not daily_df.empty:
                    cache.save_run(model, run_date, run_hour, daily_df)
                    print(f"  Cached {len(daily_df)} days.")
                    fetched += 1
                else:
                    print(f"  No data returned.")
            except Exception as e:
                print(f"  Failed: {e}")

    return fetched


def main():
    parser = argparse.ArgumentParser(description="Forecast Scheduler")
    parser.add_argument(
        '--models', nargs='+', default=DEFAULT_MODELS,
        help=f'Models to fetch (default: {" ".join(DEFAULT_MODELS)})',
    )
    parser.add_argument('--once', action='store_true', help='Run once then exit')
    parser.add_argument(
        '--interval', type=int, default=1800,
        help='Seconds between checks (default: 1800 = 30 min)',
    )
    parser.add_argument('--weights', default=None, help='Path to weights CSV')
    args = parser.parse_args()

    cache = ForecastCache()
    extractor = DegreeDayExtractor(weights_path=args.weights)

    if args.once:
        fetched = run_once(args.models, cache, extractor)
        print(f"Done. Fetched {fetched} new run(s).")
        return

    print(f"Scheduler started. Checking {', '.join(m.upper() for m in args.models)} "
          f"every {args.interval}s.")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            run_once(args.models, cache, extractor)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Sleeping {args.interval}s until next check...\n")
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nScheduler stopped.")
            break


if __name__ == '__main__':
    main()
