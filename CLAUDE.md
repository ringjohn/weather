# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Jupyter notebook-based tool for calculating Heating Degree Days (HDD) and Cooling Degree Days (CDD) from weather forecast models. Uses the [Herbie](https://herbie.readthedocs.io/) library to fetch forecast data from GFS, GEFS, IFS (ECMWF), and AIFS models.

## Dependencies

Install via `pip install -r requirements.txt`. Requires: numpy, pandas, xarray, herbie-data.

## Running

Open `degree_days.ipynb` in Jupyter and run cells. There is no build system, test suite, or linter configured.

## Architecture

All code lives in `degree_days.ipynb`. The core class is `DegreeDayExtractor`:

- `get_forecast(model, date, fxx)` — fetches 2m temperature data via Herbie for CONUS
- `calc_degree_days(ds)` — converts Kelvin to Fahrenheit, computes HDD/CDD against a 65°F base
- `apply_weights(dd_array, lat, lon)` — interpolates spatial weights (gas/population) onto the forecast grid via nearest-neighbor, computes weighted average

## Notes

- Herbie config is at `~/.config/herbie/config.toml`
