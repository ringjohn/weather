"""EIA API v2 client for weekly natural gas storage data."""

import os

import pandas as pd
import requests

EIA_API_BASE = "https://api.eia.gov/v2/natural-gas/stor/wkly/data/"


class EIAStorageClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('EIA_API_KEY')
        if not self.api_key:
            raise ValueError(
                "EIA API key required. Set EIA_API_KEY env var or pass api_key=. "
                "Get a free key at https://www.eia.gov/opendata/"
            )

    def fetch_storage(self, start_date=None, end_date=None):
        """
        Fetch weekly Lower 48 working gas storage from EIA API v2.
        Returns DataFrame with columns: period (YYYY-MM-DD), storage_bcf.
        """
        params = {
            'api_key': self.api_key,
            'frequency': 'weekly',
            'data[]': 'value',
            'facets[duoarea][]': 'R48',
            'facets[process][]': 'SWO',
            'sort[0][column]': 'period',
            'sort[0][direction]': 'asc',
            'length': 5000,
            'offset': 0,
        }
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date

        all_rows = []
        while True:
            resp = requests.get(EIA_API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            rows = data.get('response', {}).get('data', [])
            if not rows:
                break
            all_rows.extend(rows)

            total = int(data['response'].get('total', 0))
            params['offset'] += len(rows)
            if params['offset'] >= total:
                break

        if not all_rows:
            return pd.DataFrame(columns=['period', 'storage_bcf'])

        df = pd.DataFrame(all_rows)
        df = df[['period', 'value']].copy()
        df.columns = ['period', 'storage_bcf']
        df['storage_bcf'] = pd.to_numeric(df['storage_bcf'], errors='coerce')
        df = df.dropna(subset=['storage_bcf'])
        df = df.sort_values('period').reset_index(drop=True)
        return df

    def fetch_all_history(self):
        """Fetch full storage history (1993-present)."""
        return self.fetch_storage(start_date='1993-01-01')
