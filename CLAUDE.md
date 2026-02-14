# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python library and CLI tool for calculating Heating Degree Days (HDD) and Cooling Degree Days (CDD) from weather forecast models. Uses the [Herbie](https://herbie.readthedocs.io/) library to fetch forecast data from GFS, GEFS, IFS (ECMWF), and AIFS models. Compares forecasts against NOAA 30-year climate normals (1991-2020) and caches results in SQLite.

## Dependencies

Install via `pip install -r requirements.txt`. Requires: numpy, pandas, xarray, herbie-data, rich, matplotlib.

## Running

```
python main.py                    # Fetch latest GFS, show table + save chart
python main.py --model gfs        # Specify model
python main.py --date 2026-02-14  # Specific run date
python main.py --trend            # Show trend of recent runs
python main.py --no-cache         # Skip caching
python main.py --no-chart         # Skip chart generation
```

The original `degree_days.ipynb` notebook is kept for reference.

## Architecture

```
weather/
├── degree_days/
│   ├── __init__.py        # Package exports
│   ├── extractor.py       # DegreeDayExtractor class (forecast fetching + HDD/CDD calc)
│   ├── cache.py           # ForecastCache — SQLite caching at ~/.weather/forecasts.db
│   ├── normals.py         # NOAA 30-year climate normals (bundled CSV + synthetic fallback)
│   └── display.py         # Rich tables + matplotlib charts
├── main.py                # CLI entry point (argparse)
├── degree_days.ipynb      # Original notebook (reference only)
├── requirements.txt
└── CLAUDE.md
```

### Key classes and functions

- `DegreeDayExtractor` (`extractor.py`):
  - `get_forecast(model, date, fxx)` — fetches 2m temperature data via Herbie for CONUS
  - `get_full_forecast(model, date)` — fetches full forecast range (up to 384h for GFS) and returns daily HDD/CDD DataFrame
  - `calc_degree_days(ds)` — converts Kelvin to Fahrenheit, computes HDD/CDD against a 65°F base
  - `apply_weights(dd_array, lat, lon)` — interpolates spatial weights onto the forecast grid

- `ForecastCache` (`cache.py`):
  - `save_run(model, run_date, run_hour, daily_df)` — stores a forecast run
  - `get_run(model, run_date, run_hour)` — retrieves a cached run
  - `get_recent_runs(model, n)` — returns last N runs for trend analysis

- Display (`display.py`):
  - `print_forecast_table(daily_df, normals_df)` — Rich table with normals comparison
  - `print_trend_table(runs, model)` — Rich table showing forecast evolution across runs
  - `plot_forecast_vs_normals(daily_df, normals_df, save_path)` — bar/line chart
  - `plot_trend(runs, target_date, save_path)` — trend line chart

## Notes

- Herbie config is at `~/.config/herbie/config.toml`
- Forecast cache is at `~/.weather/forecasts.db`
- Climate normals CSV is auto-generated on first run at `degree_days/normals.csv`
