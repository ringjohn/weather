"""NOAA CPC weekly degree day downloader (population-weighted national totals)."""

import re
import time
from datetime import date, timedelta

import pandas as pd
import requests

CPC_LIVE_HDD = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/wsahddy.txt"
CPC_LIVE_CDD = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/wsacddy.txt"
CPC_ARCHIVE_URL = (
    "https://ftp.cpc.ncep.noaa.gov/htdocs/degree_days/weighted/"
    "legacy_files/{dtype}/statesCONUS/{year}/weekly-{date}.txt"
)


class NOAACPCClient:
    def parse_weekly_file(self, text):
        """
        Parse a CPC fixed-width weekly txt file.
        Returns (week_end_date_str, us_weekly_total) or (None, None) on failure.

        File format:
          Header: "LAST DATE OF DATA COLLECTION PERIOD IS FEB  7, 2026"
          Data:   "UNITED STATES     217   19   57    2699  -155   115    -5     4"
          The UNITED STATES row fields[2] = weekly total (after splitting
          ['UNITED', 'STATES', '217', ...]).
        """
        week_end = None
        us_total = None

        for line in text.splitlines():
            # Extract end date from header
            m = re.search(
                r'LAST DATE OF DATA COLLECTION PERIOD IS\s+(.+)',
                line,
            )
            if m:
                date_str = re.sub(r'\s+', ' ', m.group(1).strip())
                try:
                    week_end = pd.Timestamp(date_str).strftime('%Y-%m-%d')
                except Exception:
                    pass
                continue

            # Find first UNITED STATES row (population-weighted national total)
            stripped = line.lstrip()
            if stripped.startswith('UNITED STATES') and us_total is None:
                parts = stripped.split()
                # ['UNITED', 'STATES', weekly_total, dev_norm, dev_lyear, ...]
                if len(parts) >= 3:
                    try:
                        us_total = int(parts[2])
                    except ValueError:
                        pass

        return week_end, us_total

    def fetch_live(self):
        """
        Fetch the current live HDD and CDD files.
        Returns DataFrame with one row: week_end_date, HDD, CDD.
        """
        hdd_resp = requests.get(CPC_LIVE_HDD, timeout=15)
        hdd_resp.raise_for_status()
        hdd_date, hdd_val = self.parse_weekly_file(hdd_resp.text)

        cdd_resp = requests.get(CPC_LIVE_CDD, timeout=15)
        cdd_resp.raise_for_status()
        cdd_date, cdd_val = self.parse_weekly_file(cdd_resp.text)

        if hdd_date is None or cdd_date is None:
            raise ValueError("Failed to parse live CPC degree day files")

        # Both should have the same week end date
        if hdd_date != cdd_date:
            print(f"Warning: HDD date {hdd_date} != CDD date {cdd_date}, using HDD date")

        return pd.DataFrame([{
            'week_end_date': hdd_date,
            'HDD': float(hdd_val or 0),
            'CDD': float(cdd_val or 0),
        }])

    def fetch_archive_week(self, week_end_date, dd_type):
        """
        Download one archived weekly file.
        dd_type: 'heating' or 'cooling'
        Returns the US weekly total (int), or None if unavailable.
        """
        d = week_end_date if isinstance(week_end_date, date) else date.fromisoformat(str(week_end_date))
        url = CPC_ARCHIVE_URL.format(
            dtype=dd_type,
            year=d.year,
            date=d.strftime('%Y%m%d'),
        )
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            _, val = self.parse_weekly_file(resp.text)
            return val
        except requests.RequestException:
            return None

    def fetch_history_range(self, start_date, end_date, cache=None, rate_limit=0.2):
        """
        Download all archived weekly files in [start_date, end_date].
        Iterates through Thursdays. Returns DataFrame: week_end_date, HDD, CDD.

        If cache is provided (GasDataCache), skips weeks already in cache.
        """
        start = start_date if isinstance(start_date, date) else date.fromisoformat(str(start_date))
        end = end_date if isinstance(end_date, date) else date.fromisoformat(str(end_date))

        # Find all Thursdays in range
        thursdays = list(self._all_thursdays(start, end))
        total = len(thursdays)

        # Check what's already cached
        cached_dates = set()
        if cache:
            existing = cache.get_degree_days()
            if not existing.empty:
                cached_dates = set(existing['week_end_date'].tolist())

        rows = []
        for i, thu in enumerate(thursdays, 1):
            date_str = thu.strftime('%Y-%m-%d')
            if date_str in cached_dates:
                continue

            print(f"  [{i}/{total}] Fetching CPC {date_str}...", end=" ", flush=True)
            hdd = self.fetch_archive_week(thu, 'heating')
            cdd = self.fetch_archive_week(thu, 'cooling')

            if hdd is not None:
                rows.append({
                    'week_end_date': date_str,
                    'HDD': float(hdd),
                    'CDD': float(cdd or 0),
                })
                print(f"HDD={hdd}, CDD={cdd or 0}")

                # Save incrementally if cache provided
                if cache:
                    cache.save_degree_days(pd.DataFrame([rows[-1]]))
            else:
                print("not found")

            if rate_limit > 0:
                time.sleep(rate_limit)

        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['week_end_date', 'HDD', 'CDD'])

    def _all_thursdays(self, start, end):
        """Generate all Thursdays between start and end inclusive."""
        # Find first Thursday on or after start
        d = start
        while d.weekday() != 3:  # Thursday = 3
            d += timedelta(days=1)
        while d <= end:
            yield d
            d += timedelta(days=7)
