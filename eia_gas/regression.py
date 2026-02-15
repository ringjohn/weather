"""Rolling 3-year OLS regression of gas implied flows vs HDD/CDD changes."""

from datetime import date, timedelta

import numpy as np
import pandas as pd


class GasFlowRegression:
    WINDOW = 156  # 3 years of weekly observations

    def fit_current(self, df):
        """
        Fit OLS on the most recent WINDOW rows.
        df: output of GasDataCache.get_regression_dataset() with columns:
            week_end_date, storage_bcf, implied_flow, HDD, CDD.

        Model: implied_flow ~ beta_hdd * HDD + beta_cdd * CDD + intercept
        Flows are driven by absolute degree day levels: high HDD = withdrawals,
        low HDD + high CDD = injections (power gen cooling load).

        Returns dict: beta_hdd, beta_cdd, intercept, r_squared, n_obs,
                      start_date, end_date.
        """
        df = df.sort_values('week_end_date').tail(self.WINDOW).copy()
        df = df.dropna(subset=['HDD', 'CDD', 'implied_flow'])

        if len(df) < 10:
            raise ValueError(f"Insufficient data: {len(df)} rows (need >= 10)")

        return self._fit_ols(df)

    def fit_rolling(self, df):
        """
        Fit rolling OLS across all available data.
        Returns DataFrame with: week_end_date, beta_hdd, beta_cdd, intercept,
                                r_squared, n_obs.
        """
        df = df.sort_values('week_end_date').copy()
        df = df.dropna(subset=['HDD', 'CDD', 'implied_flow']).reset_index(drop=True)

        results = []
        for i in range(self.WINDOW, len(df)):
            window = df.iloc[i - self.WINDOW:i]
            try:
                coefs = self._fit_ols(window)
                coefs['week_end_date'] = window.iloc[-1]['week_end_date']
                results.append(coefs)
            except Exception:
                continue

        return pd.DataFrame(results) if results else pd.DataFrame()

    def predict_from_forecast(self, coefficients, daily_df,
                              latest_storage_bcf):
        """
        Apply calibrated coefficients to forward HDD/CDD forecasts.

        coefficients: dict from fit_current()
        daily_df: forecast DataFrame with valid_date, HDD, CDD
        latest_storage_bcf: float — most recent actual storage level

        Returns DataFrame with:
            week_end_date, forecast_HDD, forecast_CDD,
            implied_flow_bcf, forecast_storage_bcf, days_in_week
        """
        # Aggregate daily forecast into Fri-Thu gas weeks
        weekly = self._aggregate_to_gas_weeks(daily_df)
        if weekly.empty:
            return weekly

        beta_hdd = coefficients['beta_hdd']
        beta_cdd = coefficients['beta_cdd']
        intercept = coefficients['intercept']

        rows = []
        cum_storage = latest_storage_bcf

        for _, wk in weekly.iterrows():
            flow = intercept + beta_hdd * wk['HDD'] + beta_cdd * wk['CDD']
            cum_storage += flow

            rows.append({
                'week_end_date': wk['week_end_date'],
                'forecast_HDD': round(wk['HDD'], 1),
                'forecast_CDD': round(wk['CDD'], 1),
                'implied_flow_bcf': round(flow, 1),
                'forecast_storage_bcf': round(cum_storage, 1),
                'days_in_week': wk['days_in_week'],
            })

        return pd.DataFrame(rows)

    def _fit_ols(self, df):
        """Fit OLS: implied_flow ~ intercept + beta_hdd*HDD + beta_cdd*CDD."""
        X = np.column_stack([
            np.ones(len(df)),
            df['HDD'].values,
            df['CDD'].values,
        ])
        y = df['implied_flow'].values

        result, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        intercept, beta_hdd, beta_cdd = result

        y_pred = X @ result
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        return {
            'beta_hdd': float(beta_hdd),
            'beta_cdd': float(beta_cdd),
            'intercept': float(intercept),
            'r_squared': float(r_squared),
            'n_obs': len(df),
            'start_date': df['week_end_date'].iloc[0],
            'end_date': df['week_end_date'].iloc[-1],
        }

    def _aggregate_to_gas_weeks(self, daily_df):
        """
        Group daily HDD/CDD into Friday-Thursday gas weeks.
        Returns DataFrame: week_end_date (Thursday), HDD, CDD, days_in_week.
        """
        df = daily_df.copy()
        df['date'] = pd.to_datetime(df['valid_date'])
        df = df.sort_values('date')

        # Assign each day to its gas week ending Thursday.
        # Friday (weekday=4) starts a new week, ending the following Thursday (weekday=3).
        # For a given date, the gas week end Thursday is:
        #   if weekday <= 3 (Mon-Thu): the Thursday of the same week
        #   if weekday >= 4 (Fri-Sun): the Thursday of the next week
        def gas_week_end(d):
            wd = d.weekday()
            if wd <= 3:  # Mon=0 .. Thu=3
                return d + timedelta(days=(3 - wd))
            else:  # Fri=4, Sat=5, Sun=6
                return d + timedelta(days=(10 - wd))

        df['week_end'] = df['date'].apply(lambda x: gas_week_end(x.date()))

        grouped = df.groupby('week_end').agg(
            HDD=('HDD', 'sum'),
            CDD=('CDD', 'sum'),
            days_in_week=('HDD', 'count'),
        ).reset_index()

        grouped['week_end_date'] = grouped['week_end'].apply(
            lambda d: d.strftime('%Y-%m-%d')
        )
        return grouped[['week_end_date', 'HDD', 'CDD', 'days_in_week']]
