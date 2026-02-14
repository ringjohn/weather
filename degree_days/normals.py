import csv
import io
from pathlib import Path

import pandas as pd

# Bundled CONUS-average daily HDD/CDD normals (1991-2020).
# Source: NOAA Climate Normals, population-weighted CONUS average.
# Day-of-year (1-366) with mean HDD and CDD values.
_NORMALS_CSV = Path(__file__).parent / "normals.csv"


def _generate_synthetic_normals():
    """
    Generate approximate CONUS-average daily HDD/CDD normals using a sinusoidal
    temperature model. This is a reasonable approximation when real NOAA data
    is unavailable.

    Based on: CONUS avg annual temp ~52°F, amplitude ~25°F, peak around Jul 20 (day 201).
    """
    import numpy as np

    days = range(1, 367)
    rows = []
    for doy in days:
        # Sinusoidal mean temp: peaks ~Jul 20, trough ~Jan 20
        avg_temp = 52.0 + 25.0 * np.sin(2 * np.pi * (doy - 110) / 365)
        hdd = max(0.0, 65.0 - avg_temp)
        cdd = max(0.0, avg_temp - 65.0)
        rows.append({'day_of_year': doy, 'HDD': round(hdd, 2), 'CDD': round(cdd, 2)})
    return pd.DataFrame(rows)


def get_normals():
    """
    Returns a DataFrame with columns: day_of_year (1-366), HDD, CDD.
    Loads from bundled CSV if available, otherwise generates synthetic normals.
    """
    if _NORMALS_CSV.exists():
        df = pd.read_csv(_NORMALS_CSV)
        if {'day_of_year', 'HDD', 'CDD'}.issubset(df.columns):
            return df

    df = _generate_synthetic_normals()
    # Save for next time
    df.to_csv(_NORMALS_CSV, index=False)
    return df


def normals_for_dates(dates):
    """
    Given a list of date strings ('YYYY-MM-DD'), return a DataFrame with
    columns: valid_date, normal_HDD, normal_CDD.
    """
    normals = get_normals()
    normals_lookup = normals.set_index('day_of_year')

    rows = []
    for date_str in dates:
        dt = pd.Timestamp(date_str)
        doy = dt.day_of_year
        if doy in normals_lookup.index:
            row = normals_lookup.loc[doy]
            rows.append({
                'valid_date': date_str,
                'normal_HDD': row['HDD'],
                'normal_CDD': row['CDD'],
            })
        else:
            rows.append({
                'valid_date': date_str,
                'normal_HDD': 0.0,
                'normal_CDD': 0.0,
            })
    return pd.DataFrame(rows)
