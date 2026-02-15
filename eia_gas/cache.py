"""SQLite cache for EIA gas storage and NOAA CPC degree day data."""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path.home() / ".weather" / "forecasts.db"


class GasDataCache:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eia_storage (
                    period TEXT PRIMARY KEY,
                    storage_bcf REAL NOT NULL,
                    implied_flow REAL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS noaa_cpc_degree_days (
                    week_end_date TEXT PRIMARY KEY,
                    hdd REAL NOT NULL,
                    cdd REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

    def save_storage(self, df):
        """Save EIA storage data. df must have columns: period, storage_bcf.
        Implied flow is computed automatically from week-over-week changes."""
        df = df.sort_values('period').copy()
        # Compute implied flow as diff, but we need existing data for context
        with self._conn() as conn:
            for _, row in df.iterrows():
                # Get prior week's storage to compute implied flow
                prior = conn.execute(
                    "SELECT storage_bcf FROM eia_storage WHERE period < ? ORDER BY period DESC LIMIT 1",
                    (row['period'],),
                ).fetchone()
                implied = row['storage_bcf'] - prior[0] if prior else None
                conn.execute(
                    """INSERT OR REPLACE INTO eia_storage (period, storage_bcf, implied_flow)
                       VALUES (?, ?, ?)""",
                    (row['period'], row['storage_bcf'], implied),
                )

    def recompute_implied_flows(self):
        """Recompute all implied flows from storage levels."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT period, storage_bcf FROM eia_storage ORDER BY period"
            ).fetchall()
            prev = None
            for period, storage in rows:
                flow = storage - prev if prev is not None else None
                conn.execute(
                    "UPDATE eia_storage SET implied_flow = ? WHERE period = ?",
                    (flow, period),
                )
                prev = storage

    def get_storage(self, start_date=None, end_date=None):
        """Retrieve storage data as DataFrame."""
        query = "SELECT period, storage_bcf, implied_flow FROM eia_storage"
        params = []
        clauses = []
        if start_date:
            clauses.append("period >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("period <= ?")
            params.append(end_date)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY period"
        with self._conn() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def get_latest_storage_date(self):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MAX(period) FROM eia_storage"
            ).fetchone()
            return row[0] if row and row[0] else None

    def save_degree_days(self, df):
        """Save NOAA CPC degree day data. df: week_end_date, HDD, CDD."""
        with self._conn() as conn:
            for _, row in df.iterrows():
                conn.execute(
                    """INSERT OR REPLACE INTO noaa_cpc_degree_days
                       (week_end_date, hdd, cdd) VALUES (?, ?, ?)""",
                    (row['week_end_date'], row['HDD'], row['CDD']),
                )

    def get_degree_days(self, start_date=None, end_date=None):
        query = "SELECT week_end_date, hdd AS HDD, cdd AS CDD FROM noaa_cpc_degree_days"
        params = []
        clauses = []
        if start_date:
            clauses.append("week_end_date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("week_end_date <= ?")
            params.append(end_date)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY week_end_date"
        with self._conn() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def get_latest_dd_date(self):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MAX(week_end_date) FROM noaa_cpc_degree_days"
            ).fetchone()
            return row[0] if row and row[0] else None

    def get_regression_dataset(self, lookback_weeks=156):
        """JOIN storage + degree days. EIA periods are Fridays, CPC weeks end
        on Thursdays. The CPC week ending Thursday corresponds to the EIA
        storage report dated the next day (Friday), so we join on
        CPC week_end_date + 1 day = EIA period."""
        query = """
            SELECT s.period AS week_end_date,
                   s.storage_bcf, s.implied_flow,
                   d.hdd AS HDD, d.cdd AS CDD
            FROM eia_storage s
            INNER JOIN noaa_cpc_degree_days d
                ON s.period = date(d.week_end_date, '+1 day')
            WHERE s.implied_flow IS NOT NULL
            ORDER BY s.period DESC
            LIMIT ?
        """
        with self._conn() as conn:
            df = pd.read_sql_query(query, conn, params=(lookback_weeks,))
        return df.sort_values('week_end_date').reset_index(drop=True)
