import sqlite3
from pathlib import Path

import pandas as pd


DB_PATH = Path.home() / ".weather" / "forecasts.db"


class ForecastCache:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forecasts (
                    model TEXT NOT NULL,
                    run_date TEXT NOT NULL,
                    run_hour INTEGER NOT NULL,
                    valid_date TEXT NOT NULL,
                    hdd REAL NOT NULL,
                    cdd REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(model, run_date, run_hour, valid_date)
                )
            """)

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def save_run(self, model, run_date, run_hour, daily_df):
        """Store a forecast run. daily_df must have columns: valid_date, HDD, CDD."""
        with self._conn() as conn:
            for _, row in daily_df.iterrows():
                conn.execute(
                    """INSERT OR REPLACE INTO forecasts
                       (model, run_date, run_hour, valid_date, hdd, cdd)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (model, run_date, run_hour, row['valid_date'], row['HDD'], row['CDD']),
                )

    def get_run(self, model, run_date, run_hour):
        """Retrieve a cached run as a DataFrame, or None if not found."""
        with self._conn() as conn:
            df = pd.read_sql_query(
                """SELECT valid_date, hdd AS HDD, cdd AS CDD
                   FROM forecasts
                   WHERE model=? AND run_date=? AND run_hour=?
                   ORDER BY valid_date""",
                conn,
                params=(model, run_date, run_hour),
            )
        return df if len(df) > 0 else None

    def get_recent_runs(self, model, n=10):
        """Return a list of (run_date, run_hour, DataFrame) for the last N runs."""
        with self._conn() as conn:
            runs = conn.execute(
                """SELECT DISTINCT run_date, run_hour
                   FROM forecasts
                   WHERE model=?
                   ORDER BY run_date DESC, run_hour DESC
                   LIMIT ?""",
                (model, n),
            ).fetchall()

        results = []
        for run_date, run_hour in runs:
            df = self.get_run(model, run_date, run_hour)
            if df is not None:
                results.append((run_date, run_hour, df))
        return results
