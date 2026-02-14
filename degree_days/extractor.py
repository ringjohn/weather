import numpy as np
import pandas as pd
import xarray as xr
from herbie import Herbie


class DegreeDayExtractor:
    def __init__(self, weights_path=None):
        """
        weights_path: Path to a CSV/NetCDF containing 'lat', 'lon', and 'weight'
        (Gas or Pop) for CONUS.
        """
        self.base_temp = 65.0
        self.weights = pd.read_csv(weights_path) if weights_path else None

    def get_forecast(self, model='gfs', date=None, fxx=24, search_string="TMP:2 m above ground"):
        """
        Fetch 2m temperature for a single forecast hour.
        Models supported by Herbie: 'gfs', 'gefs', 'ifs' (ECMWF), 'aifs' (AI)

        Herbie uses the GRIB index (.idx) to do a byte-range download of only
        the matching parameter, not the full GRIB file.
        """
        if date is None:
            date = (
                pd.Timestamp.now('UTC') - pd.Timedelta(hours=6)
            ).floor('6h').strftime("%Y-%m-%d %H:00")

        product = 'pgrb2.0p25' if model in ('gfs', 'gefs') else 'oper'
        H = Herbie(date, model=model, product=product, fxx=fxx)
        ds = H.xarray(search_string)
        return ds

    def calc_degree_days(self, ds):
        """Calculates HDD and CDD from Kelvin temperature data."""
        temp_f = (ds.t2m - 273.15) * 9 / 5 + 32
        hdd = np.maximum(0, self.base_temp - temp_f)
        cdd = np.maximum(0, temp_f - self.base_temp)
        return hdd, cdd

    def apply_weights(self, dd_array, lat, lon):
        """
        Applies gas/pop weights to the degree day grid.
        Interpolates weight points onto the forecast grid using nearest-neighbor,
        then computes sum(DD * weight) / sum(weight).
        """
        if self.weights is None:
            return float(dd_array.mean())

        weight_da = xr.DataArray(
            data=self.weights['weight'].values,
            dims='points',
            coords={
                'lat': ('points', self.weights['lat'].values),
                'lon': ('points', self.weights['lon'].values),
            },
        )
        weight_grid = weight_da.groupby('lat').mean().interp(
            lat=lat, lon=lon, method='nearest',
        ).fillna(0)

        weighted_value = float((dd_array * weight_grid).sum() / weight_grid.sum())
        return weighted_value

    def check_availability(self, model='gfs', date=None):
        """Check if a model run is available by probing the first forecast hour."""
        if date is None:
            date = (
                pd.Timestamp.now('UTC') - pd.Timedelta(hours=6)
            ).floor('6h').strftime("%Y-%m-%d %H:00")
        product = 'pgrb2.0p25' if model in ('gfs', 'gefs') else 'oper'
        try:
            H = Herbie(date, model=model, product=product, fxx=6)
            inv = H.inventory("TMP:2 m above ground")
            return len(inv) > 0
        except Exception:
            return False

    def get_full_forecast(self, model='gfs', date=None):
        """
        Fetch the full GFS forecast (up to 384h) and return a daily DataFrame
        with columns: valid_date, HDD, CDD.

        GFS/GEFS: 6-hourly to 120h, then 12-hourly to 384h.
        Other models: 6-hourly to 168h (7 days).

        Only extracts TMP:2m via GRIB index byte-range requests (not full files).
        """
        if date is None:
            date = (
                pd.Timestamp.now('UTC') - pd.Timedelta(hours=6)
            ).floor('6h').strftime("%Y-%m-%d %H:00")

        # Check availability before starting the long download loop
        print(f"Checking {model.upper()} run availability for {date}...")
        if not self.check_availability(model, date):
            print(f"ERROR: {model.upper()} run {date} is not yet available.")
            return pd.DataFrame(columns=['valid_date', 'HDD', 'CDD'])
        print(f"Run available. Extracting TMP:2m from GRIB index (byte-range only).")

        if model in ('gfs', 'gefs'):
            fxx_hours = list(range(6, 126, 6)) + list(range(132, 390, 12))
        else:
            fxx_hours = list(range(6, 174, 6))

        total = len(fxx_hours)
        rows = []
        consecutive_failures = 0
        for i, fxx in enumerate(fxx_hours, 1):
            print(f"  [{i}/{total}] Downloading F{fxx:03d}...", end=" ", flush=True)
            try:
                ds = self.get_forecast(model=model, date=date, fxx=fxx)
            except Exception as e:
                consecutive_failures += 1
                print(f"FAILED ({e})")
                if consecutive_failures >= 3:
                    print("Too many consecutive failures, stopping.")
                    break
                continue
            consecutive_failures = 0
            hdd, cdd = self.calc_degree_days(ds)
            valid = pd.Timestamp(ds.valid_time.values)
            rows.append({
                'valid_time': valid,
                'valid_date': valid.strftime('%Y-%m-%d'),
                'HDD': float(hdd.mean()),
                'CDD': float(cdd.mean()),
            })
            print(f"OK (valid {valid.strftime('%Y-%m-%d %H:%M')})")

        if not rows:
            print("No data retrieved.")
            return pd.DataFrame(columns=['valid_date', 'HDD', 'CDD'])

        print(f"Downloaded {len(rows)}/{total} forecast hours successfully.")
        df = pd.DataFrame(rows)
        daily = df.groupby('valid_date')[['HDD', 'CDD']].mean().round(2).reset_index()
        return daily
