# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python library and CLI tool for calculating Heating Degree Days (HDD) and Cooling Degree Days (CDD) from weather forecast models. Uses the [Herbie](https://herbie.readthedocs.io/) library to fetch forecast data from GFS, GEFS, ECMWF IFS (operational + ensemble), and AIFS models. Compares forecasts against NOAA 30-year climate normals (1991-2020) and caches results in SQLite.

## Dependencies

Install via `pip install -r requirements.txt`. Requires: numpy, pandas, xarray, herbie-data, rich, matplotlib.

## Running

```
python main.py                        # Fetch latest GFS, show table + save chart
python main.py --model gfs            # Specify model
python main.py --model ecmwf-ens      # ECMWF ensemble (~15 days)
python main.py --date "2026-02-14"    # Specific run date
python main.py --date "2026-02-14 12:00"  # Specific run date + hour
python main.py --changes              # Show changes vs previous runs (12h, 24h, weekend/Fri)
python main.py --trend                # Show trend of recent runs
python main.py --no-cache             # Skip caching
python main.py --no-chart             # Skip chart generation
python main.py --no-backfill          # Skip backfilling missing runs
```

### Scheduler

```
python scheduler.py                    # Run continuously, check all models every 30 min
python scheduler.py --models gfs gefs  # Only specific models
python scheduler.py --once             # Single pass then exit
python scheduler.py --interval 3600    # Custom check interval (seconds)
```

The original `degree_days.ipynb` notebook is kept for reference.

## Available Models

| Name        | Description              | Cycles    | Forecast Range |
|-------------|--------------------------|-----------|----------------|
| `gfs`       | GFS Operational          | 00/06/12/18z | 16 days     |
| `gefs`      | GEFS Ensemble Mean       | 00/06/12/18z | 16 days     |
| `ecmwf`     | ECMWF IFS Operational    | 00/12z    | 10 days        |
| `ecmwf-ens` | ECMWF IFS Ensemble       | 00/12z    | 15 days        |
| `aifs`      | ECMWF AIFS (AI)          | 00/12z    | 15 days        |
| `ifs`       | Alias for `ecmwf`        | 00/12z    | 10 days        |

Model configuration is centralized in `MODEL_CONFIG` dict in `extractor.py`.

## Architecture

```
weather/
├── degree_days/
│   ├── __init__.py        # Package exports
│   ├── extractor.py       # DegreeDayExtractor + MODEL_CONFIG (forecast fetching + HDD/CDD calc)
│   ├── cache.py           # ForecastCache — SQLite caching at ~/.weather/forecasts.db
│   ├── normals.py         # NOAA 30-year climate normals (bundled CSV + synthetic fallback)
│   └── display.py         # Rich tables + matplotlib charts (forecast, changes, trend)
├── main.py                # CLI entry point (argparse)
├── scheduler.py           # Periodic forecast fetcher (runs in a loop or --once)
├── degree_days.ipynb      # Original notebook (reference only)
├── requirements.txt
└── CLAUDE.md
```

### Key classes and functions

- `MODEL_CONFIG` (`extractor.py`): Dict mapping model names to Herbie params, forecast hours, cycle info.

- `DegreeDayExtractor` (`extractor.py`):
  - `get_forecast(model, date, fxx)` — fetches 2m temperature data via Herbie for CONUS
  - `get_full_forecast(model, date)` — fetches full forecast range and returns daily HDD/CDD DataFrame
  - `calc_degree_days(ds)` — converts Kelvin to Fahrenheit, computes HDD/CDD against a 65°F base
  - `apply_weights(dd_array, lat, lon)` — interpolates spatial weights onto the forecast grid

- `ForecastCache` (`cache.py`):
  - `save_run(model, run_date, run_hour, daily_df)` — stores a forecast run
  - `get_run(model, run_date, run_hour)` — retrieves a cached run
  - `get_recent_runs(model, n)` — returns last N runs for trend analysis
  - `get_run_by_offset(model, run_date, run_hour, hours_back)` — find run N hours before
  - `get_friday_12z(model, run_date)` — most recent Friday 12z run (for weekend comparisons)
  - `get_all_runs(model)` — list all cached (run_date, run_hour) pairs

- Display (`display.py`):
  - `print_forecast_table(daily_df, normals_df)` — Rich table with normals comparison
  - `print_changes_table(current_df, compare_df, labels)` — Rich table of run-to-run changes
  - `print_trend_table(runs, model)` — Rich table showing forecast evolution across runs
  - `plot_forecast_vs_normals(daily_df, normals_df, save_path, run_label)` — bar/line chart
  - `plot_changes(current_df, compare_df, labels, save_path)` — change bar chart
  - `plot_trend(runs, target_date, save_path)` — trend line chart

## Output Filenames

Charts include the run date and hour:
- `forecast_2026-02-14_00z.png` — forecast vs normals
- `changes_12h_2026-02-14_12z.png` — 12-hour change
- `changes_24h_2026-02-14_12z.png` — 24-hour change
- `changes_fri12z_2026-02-15_00z.png` — vs Friday 12z (weekends/Monday 00z only)

## Notes

- Herbie config is at `~/.config/herbie/config.toml`
- Forecast cache is at `~/.weather/forecasts.db`
- Climate normals CSV is auto-generated on first run at `degree_days/normals.csv`
- Backfill: on each run, main.py checks for missing runs in the last 48h and fetches them
- ECMWF search strings use `:2t:` (ECMWF GRIB convention) vs `TMP:2 m above ground` (NCEP)
