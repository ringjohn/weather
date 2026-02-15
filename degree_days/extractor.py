import numpy as np
import pandas as pd
import xarray as xr
from herbie import Herbie


# Model configuration: Herbie model name, product, forecast hours, search string, cycle info
# fxx_hours: list of forecast hours to download
# For models with mixed intervals (e.g. GFS: 6h to 120, then 12h to 384), use a tuple of ranges.
MODEL_CONFIG = {
    'gfs': {
        'herbie_model': 'gfs',
        'product': 'pgrb2.0p25',
        'search': 'TMP:2 m above ground',
        'fxx_hours': list(range(6, 126, 6)) + list(range(132, 390, 12)),  # 16 days
        'cycle_hours': 6,
        'delay_hours': 4,
        'description': 'GFS Operational',
    },
    'gefs': {
        'herbie_model': 'gefs',
        'product': 'atmos.25',
        'herbie_kwargs': {'member': 'mean'},
        'search': 'TMP:2 m above ground',
        'fxx_hours': list(range(6, 126, 6)) + list(range(132, 390, 12)),  # 16 days
        'cycle_hours': 6,
        'delay_hours': 5,
        'description': 'GEFS Ensemble Mean',
    },
    'ecmwf': {
        'herbie_model': 'ecmwf',
        'product': 'oper',
        'search': ':2t:',
        'fxx_hours': list(range(6, 246, 6)),  # 10 days
        'cycle_hours': 12,
        'delay_hours': 6,
        'description': 'ECMWF IFS Operational',
    },
    'ecmwf-ens': {
        'herbie_model': 'ecmwf',
        'product': 'enfo',
        'search': ':2t:',
        'fxx_hours': list(range(6, 366, 6)),  # 15 days
        'cycle_hours': 12,
        'delay_hours': 7,
        'description': 'ECMWF IFS Ensemble',
    },
    'aifs': {
        'herbie_model': 'aifs',
        'product': 'oper',
        'search': ':2t:',
        'fxx_hours': list(range(6, 366, 6)),  # 15 days
        'cycle_hours': 12,
        'delay_hours': 5,
        'description': 'ECMWF AIFS (AI)',
    },
    # Aliases for convenience
    'ifs': {
        'herbie_model': 'ecmwf',
        'product': 'oper',
        'search': ':2t:',
        'fxx_hours': list(range(6, 246, 6)),
        'cycle_hours': 12,
        'delay_hours': 6,
        'description': 'ECMWF IFS Operational',
    },
}


def list_models():
    """Return list of (name, description) for all available models."""
    seen = set()
    result = []
    for name, cfg in MODEL_CONFIG.items():
        key = (cfg['herbie_model'], cfg['product'])
        if key not in seen:
            seen.add(key)
            result.append((name, cfg['description']))
    return result


class DegreeDayExtractor:
    def __init__(self, weights_path=None):
        """
        weights_path: Path to a CSV/NetCDF containing 'lat', 'lon', and 'weight'
        (Gas or Pop) for CONUS.
        """
        self.base_temp = 65.0
        self.weights = pd.read_csv(weights_path) if weights_path else None

    def _get_config(self, model):
        cfg = MODEL_CONFIG.get(model)
        if cfg is None:
            raise ValueError(
                f"Unknown model '{model}'. Available: {', '.join(MODEL_CONFIG.keys())}"
            )
        return cfg

    def get_forecast(self, model='gfs', date=None, fxx=24):
        """
        Fetch 2m temperature for a single forecast hour.
        Herbie uses the GRIB index (.idx) to do a byte-range download of only
        the matching parameter, not the full GRIB file.
        """
        if date is None:
            date = (
                pd.Timestamp.now('UTC') - pd.Timedelta(hours=6)
            ).floor('6h').strftime("%Y-%m-%d %H:00")

        cfg = self._get_config(model)
        extra = cfg.get('herbie_kwargs', {})
        H = Herbie(date, model=cfg['herbie_model'], product=cfg['product'], fxx=fxx, **extra)
        ds = H.xarray(cfg['search'])
        # Ensemble products can return a list of Datasets (multiple hypercubes).
        # Take the first one which contains the 2m temp field.
        if isinstance(ds, list):
            ds = ds[0]
        return ds

    def calc_degree_days(self, ds):
        """Calculates HDD and CDD from Kelvin temperature data."""
        # Find the 2m temp variable — named 't2m' in GFS, '2t' in ECMWF
        if hasattr(ds, 't2m'):
            temp_k = ds.t2m
        elif hasattr(ds, 't'):
            temp_k = ds.t
        else:
            # Fall back to first data variable
            temp_k = ds[list(ds.data_vars)[0]]

        temp_f = (temp_k - 273.15) * 9 / 5 + 32
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
        cfg = self._get_config(model)
        extra = cfg.get('herbie_kwargs', {})
        try:
            H = Herbie(date, model=cfg['herbie_model'], product=cfg['product'], fxx=6, **extra)
            inv = H.inventory(cfg['search'])
            return len(inv) > 0
        except Exception:
            return False

    def get_full_forecast(self, model='gfs', date=None):
        """
        Fetch the full forecast and return a daily DataFrame
        with columns: valid_date, HDD, CDD.

        Forecast range depends on model (see MODEL_CONFIG).
        Only extracts 2m temp via GRIB index byte-range requests (not full files).
        """
        if date is None:
            date = (
                pd.Timestamp.now('UTC') - pd.Timedelta(hours=6)
            ).floor('6h').strftime("%Y-%m-%d %H:00")

        cfg = self._get_config(model)

        # Check availability before starting the long download loop
        print(f"Checking {cfg['description']} run availability for {date}...")
        if not self.check_availability(model, date):
            print(f"ERROR: {cfg['description']} run {date} is not yet available.")
            return pd.DataFrame(columns=['valid_date', 'HDD', 'CDD'])
        print(f"Run available. Extracting 2m temp from GRIB index (byte-range only).")

        fxx_hours = cfg['fxx_hours']
        total = len(fxx_hours)
        # Require at least 75% of forecast hours to consider the run complete.
        min_required = int(total * 0.75)
        rows = []
        consecutive_failures = 0
        aborted = False
        for i, fxx in enumerate(fxx_hours, 1):
            print(f"  [{i}/{total}] Downloading F{fxx:03d}...", end=" ", flush=True)
            try:
                ds = self.get_forecast(model=model, date=date, fxx=fxx)
            except Exception as e:
                consecutive_failures += 1
                print(f"FAILED ({e})")
                if consecutive_failures >= 3:
                    print("Too many consecutive failures — run likely not fully published yet.")
                    aborted = True
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

        if aborted and len(rows) < min_required:
            print(f"Run incomplete: got {len(rows)}/{total} hours "
                  f"(need {min_required}). Discarding — will retry later.")
            return pd.DataFrame(columns=['valid_date', 'HDD', 'CDD'])

        if aborted:
            print(f"Run partially complete: {len(rows)}/{total} hours "
                  f"(above {min_required} threshold). Keeping partial data.")
        else:
            print(f"Downloaded {len(rows)}/{total} forecast hours successfully.")

        df = pd.DataFrame(rows)
        daily = df.groupby('valid_date')[['HDD', 'CDD']].mean().round(2).reset_index()
        return daily
